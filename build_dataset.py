# build_dataset.py
import os, sys, csv, glob, hashlib, argparse, shutil, tempfile
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append(".")

from pipeline.ingest import sniff_ext, pdf_to_images, html_to_text
from pipeline.ocr import ocr_images
from pipeline.metadata import read_metadata_exiftool
from pipeline.features import summarize_text, reasons_from_metadata, reasons_from_text, reasons_from_images
from service.main import get_config

CFG = get_config()
TH_LOW  = CFG["thresholds"]["low"]
TH_HIGH = CFG["thresholds"]["high"]

DEFAULT_RAW = "data/raw"
DEFAULT_OUT = "data/dataset_autenticarIA.csv"

# ---------------- COLUMNS (actualizado) ----------------
COLUMNS = [
    "doc_id","tipo_doc","file_ext","document_language","num_pages","file_size_bytes",
    "meta_producer","meta_creator","meta_createdate","meta_modifydate","has_metadata",
    "producer_suspicious",
    "ocr_total_chars","ocr_pages_with_text","ocr_chars_per_page_mean",
    "has_date","has_patente","has_vin","has_cuit","has_vencimiento","has_entidad_emisora",
    "same_patente_all_pages",
    "min_resolution_px","low_res_flag","dpi_used",
    # reglas originales
    "rule_META_PRODUCER_SUSPICIOUS","rule_OCR_FIELD_MISSING_DATE","rule_OCR_TEXT_TOO_SHORT","rule_IMAGE_LOW_RES",
    # nuevas reglas (metadata)
    "rule_META_PRODUCER_UNKNOWN","rule_META_PRODUCER_MISSING","rule_META_CREATOR_PERSON_NAME",
    "rule_META_DATE_MISMATCH","rule_META_DATE_LARGE_GAP",
    # nuevas reglas (texto)
    "rule_OCR_INVALID_CUIT","rule_OCR_VIN_FORMAT_SUSPECT","rule_OCR_MISSING_VIGENCIA","rule_OCR_MISSING_EMISOR",
    # nuevas reglas (imagen)
    "rule_IMAGE_OVERCOMPRESSED","rule_IMAGE_BLURRY",
    # resumen
    "reasons_count",
    # salida
    "y_score_1_100","y_label"
]

def file_sha(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]

def map_label(score01: float) -> str:
    if score01 < TH_LOW: return "low"
    if score01 < TH_HIGH: return "medium"
    return "high"

def detect_signals_from_text(txt: str):
    import re
    has_patente      = bool(re.search(r"\b([A-Z]{3}\s?\d{3}|[A-Z]{2}\d{3}[A-Z]{2})\b", txt))
    has_vin          = bool(re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", txt))
    has_cuit         = bool(re.search(r"\b(20|23|24|27|30|33|34)-?\d{8}-?\d\b", txt))
    has_vencimiento  = bool(re.search(r"\b(venc(?:imiento)?|expira|vigencia|validez)\b", txt, re.I))
    has_emisora      = bool(re.search(r"\b(aseguradora|registro|ministerio|entidad|dnrpa|compañ[ií]a|provincia seguros|sancor|zurich|vtv)\b", txt, re.I))
    return has_patente, has_vin, has_cuit, has_vencimiento, has_emisora

def same_patente_across_pages(texts):
    import re, collections
    plate_re = re.compile(r"\b([A-Z]{3}\s?\d{3}|[A-Z]{2}\d{3}[A-Z]{2})\b")
    per_page = [plate_re.findall(t or "") for t in texts]
    if not per_page or any(len(p)==0 for p in per_page): return False
    cnt = collections.Counter(per_page[0])
    if not cnt: return False
    top, _ = cnt.most_common(1)[0]
    return all(top in p for p in per_page[1:])

def min_resolution(images):
    try:
        from PIL import Image
        areas = []
        for p in images:
            with Image.open(p) as im:
                areas.append(im.width * im.height)
        return min(areas) if areas else None
    except Exception:
        return None

def process_one(path: str) -> dict:
    ext = sniff_ext(path)
    doc_id = f"DOC_{file_sha(path)}"
    size_bytes = os.path.getsize(path)
    lang = CFG["ocr"]["default_lang"]
    pdf_dpi = CFG["ocr"]["pdf_render_dpi"]
    workdir = CFG["paths"]["workdir"]

    tipo_doc = (os.path.basename(os.path.dirname(path)) or "OTRO").upper()
    if tipo_doc == "RAW": tipo_doc = "OTRO"

    images, texts, dpi_used = [], [], 0
    temp_pages_dir = None

    # 1) Render / ingest
    if ext == ".pdf":
        temp_pages_dir = tempfile.mkdtemp(dir=workdir)
        images = pdf_to_images(path, temp_pages_dir, dpi=pdf_dpi)
        dpi_used = pdf_dpi
    elif ext in [".jpg",".jpeg",".png",".webp",".tif",".tiff"]:
        images = [path]
    elif ext in [".html",".htm"]:
        texts = [html_to_text(path)]
    else:
        return {"_skip": True, "doc_id": doc_id, "_reason": f"ext {ext} no soportada"}

    # 2) OCR
    if images:
        ocr = ocr_images(images, lang=lang)
        texts = ocr["texts"]

    # 3) Metadatos
    meta = read_metadata_exiftool(path) or {}
    meta_producer = meta.get("Producer") or ""
    meta_creator  = meta.get("Creator") or ""
    meta_create   = meta.get("CreateDate") or meta.get("CreationDate") or ""
    meta_modify   = meta.get("ModifyDate") or ""
    has_metadata  = len(meta) > 0

    # 4) Señales / reglas
    text_summary = summarize_text(texts)
    reasons  = reasons_from_metadata(meta)
    reasons += reasons_from_text(tipo_doc, text_summary)
    reasons += reasons_from_images(images)

    # ---- mapear a flags por código ----
    codes = {code for (code, _, _) in reasons}

    rule_META_PRODUCER_SUSPICIOUS = "META_PRODUCER_SUSPICIOUS" in codes
    rule_IMAGE_LOW_RES            = "IMAGE_LOW_RES" in codes
    rule_OCR_FIELD_MISSING_DATE   = "OCR_FIELD_MISSING_DATE" in codes
    rule_OCR_TEXT_TOO_SHORT       = "OCR_TEXT_TOO_SHORT" in codes

    rule_META_PRODUCER_UNKNOWN        = "META_PRODUCER_UNKNOWN" in codes
    rule_META_PRODUCER_MISSING        = "META_PRODUCER_MISSING" in codes
    rule_META_CREATOR_PERSON_NAME     = "META_CREATOR_PERSON_NAME" in codes
    rule_META_DATE_MISMATCH           = "META_DATE_MISMATCH" in codes
    rule_META_DATE_LARGE_GAP          = "META_DATE_LARGE_GAP" in codes
    rule_OCR_INVALID_CUIT             = "OCR_INVALID_CUIT" in codes
    rule_OCR_VIN_FORMAT_SUSPECT       = "OCR_VIN_FORMAT_SUSPECT" in codes
    rule_OCR_MISSING_VIGENCIA         = "OCR_MISSING_VIGENCIA" in codes
    rule_OCR_MISSING_EMISOR           = "OCR_MISSING_EMISOR" in codes
    rule_IMAGE_OVERCOMPRESSED         = "IMAGE_OVERCOMPRESSED" in codes
    rule_IMAGE_BLURRY                 = "IMAGE_BLURRY" in codes

    # Sumarizados
    ocr_total_chars = int(text_summary.get("length", 0))
    ocr_pages_with_text = sum(1 for t in texts if (t or "").strip())
    ocr_chars_per_page_mean = (ocr_total_chars / max(1, len(texts))) if texts else 0.0

    joined = "\n".join(t or "" for t in texts)
    has_patente, has_vin, has_cuit, has_venc, has_emisora = detect_signals_from_text(joined)
    same_plate = same_patente_across_pages(texts)

    min_res = min_resolution(images) if images else None
    low_res_flag = bool(min_res and min_res < 400*400)

    producer_suspicious = any(s in (meta_producer or "").lower()
                              for s in ["photoshop","gimp","illustrator","corel","paint.net","canva","inkscape"])

    # score
    score01 = min(1.0, sum((w or 0.0) for _,_,w in reasons))
    y_score_1_100 = round(100*score01, 1)
    y_label = map_label(score01)

    # limpiar temporales
    if temp_pages_dir and not CFG["paths"].get("keep_temp", False):
        shutil.rmtree(temp_pages_dir, ignore_errors=True)

    return {
        "doc_id": doc_id,
        "tipo_doc": tipo_doc,
        "file_ext": ext.strip("."),
        "document_language": lang,
        "num_pages": len(texts) if texts else (len(images) if images else 0),
        "file_size_bytes": size_bytes,
        "meta_producer": meta_producer,
        "meta_creator": meta_creator,
        "meta_createdate": meta_create,
        "meta_modifydate": meta_modify,
        "has_metadata": has_metadata,
        "producer_suspicious": producer_suspicious,
        "ocr_total_chars": ocr_total_chars,
        "ocr_pages_with_text": ocr_pages_with_text,
        "ocr_chars_per_page_mean": ocr_chars_per_page_mean,
        "has_date": bool(text_summary.get("has_date", False)),
        "has_patente": has_patente,
        "has_vin": has_vin,
        "has_cuit": has_cuit,
        "has_vencimiento": has_venc,
        "has_entidad_emisora": has_emisora,
        "same_patente_all_pages": same_plate,
        "min_resolution_px": float(min_res) if min_res else None,
        "low_res_flag": low_res_flag,
        "dpi_used": pdf_dpi if ext==".pdf" else 0,
        "rule_META_PRODUCER_SUSPICIOUS": rule_META_PRODUCER_SUSPICIOUS,
        "rule_OCR_FIELD_MISSING_DATE": rule_OCR_FIELD_MISSING_DATE,
        "rule_OCR_TEXT_TOO_SHORT": rule_OCR_TEXT_TOO_SHORT,
        "rule_IMAGE_LOW_RES": rule_IMAGE_LOW_RES,
        "rule_META_PRODUCER_UNKNOWN": rule_META_PRODUCER_UNKNOWN,
        "rule_META_PRODUCER_MISSING": rule_META_PRODUCER_MISSING,
        "rule_META_CREATOR_PERSON_NAME": rule_META_CREATOR_PERSON_NAME,
        "rule_META_DATE_MISMATCH": rule_META_DATE_MISMATCH,
        "rule_META_DATE_LARGE_GAP": rule_META_DATE_LARGE_GAP,
        "rule_OCR_INVALID_CUIT": rule_OCR_INVALID_CUIT,
        "rule_OCR_VIN_FORMAT_SUSPECT": rule_OCR_VIN_FORMAT_SUSPECT,
        "rule_OCR_MISSING_VIGENCIA": rule_OCR_MISSING_VIGENCIA,
        "rule_OCR_MISSING_EMISOR": rule_OCR_MISSING_EMISOR,
        "rule_IMAGE_OVERCOMPRESSED": rule_IMAGE_OVERCOMPRESSED,
        "rule_IMAGE_BLURRY": rule_IMAGE_BLURRY,
        "reasons_count": len(codes),
        "y_score_1_100": y_score_1_100,
        "y_label": y_label,
    }

def load_existing_ids(csv_path):
    if not os.path.exists(csv_path): return set()
    ids = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ids.add(row["doc_id"])
    return ids

def append_rows(csv_path, rows, write_header=False):
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if (not file_exists) or write_header:
            w.writeheader()
        for r in rows:
            if not r or r.get("_skip"): continue
            w.writerow({k: r.get(k) for k in COLUMNS})

def iter_paths(raw_root):
    patterns = ("*.pdf","*.jpg","*.jpeg","*.png","*.webp","*.tif","*.tiff","*.html","*.htm")
    for pat in patterns:
        for p in glob.glob(os.path.join(raw_root, "**", pat), recursive=True):
            if os.path.isdir(p): continue
            if os.sep + "work" + os.sep in p: continue
            yield p

def main():
    ap = argparse.ArgumentParser(description="Construir dataset AutenticarIA desde data/raw/**")
    ap.add_argument("--in", dest="raw_dir", default=DEFAULT_RAW)
    ap.add_argument("--out", dest="out_csv", default=DEFAULT_OUT)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rebuild", action="store_true", help="Ignorar CSV previo y reconstruir con header nuevo")
    args = ap.parse_args()

    paths = sorted(iter_paths(args.raw_dir))
    seen = set() if args.rebuild else load_existing_ids(args.out_csv)
    to_do = [p for p in paths if f"DOC_{file_sha(p)}" not in seen]

    if args.rebuild and os.path.exists(args.out_csv):
        os.remove(args.out_csv)

    print(f"Encontrados: {len(paths)} | Nuevos a procesar: {len(to_do)}")

    results, errors = [], 0
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_one, p): p for p in to_do}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                res = fut.result()
                results.append(res)
                if len(results) >= 20:
                    append_rows(args.out_csv, results); results = []
            except Exception as e:
                errors += 1
                print(f"[ERROR] {p}: {e}")

    if results:
        append_rows(args.out_csv, results)

    print(f"Listo. Errores: {errors}. CSV: {args.out_csv}")

if __name__ == "__main__":
    main()
