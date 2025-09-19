import os, time, hashlib, tempfile, shutil
from typing import Dict, Any
from pipeline.ingest import sniff_ext, pdf_to_images
from pipeline.ocr import ocr_images
from pipeline.metadata import read_metadata_exiftool
from pipeline.features import summarize_text, reasons_from_metadata, reasons_from_text, reasons_from_images
from models.loader import get_versions
from pipeline.ingest import sniff_ext, pdf_to_images, html_to_text

def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024*1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()

def map_label(score01: float, low: float, high: float) -> str:
    if score01 < low: return "low"
    if score01 >= high: return "high"
    return "medium"

def analyze_document(local_path: str, document_type: str, language: str, options: dict, config: dict) -> Dict[str, Any]:
    t0 = time.time()
    workdir = config["paths"]["workdir"]
    pdf_dpi = config["ocr"]["pdf_render_dpi"]
    thresholds = config["thresholds"]

    file_hash = file_sha256(local_path)
    ext = sniff_ext(local_path)

    # 1) Convertir a imágenes por página / o leer HTML como texto
    per_page_images = []
    temp_pages_dir = None
    is_html = ext in [".html", ".htm"]

    if ext == ".pdf":
        temp_pages_dir = tempfile.mkdtemp(dir=workdir)
        per_page_images = pdf_to_images(local_path, temp_pages_dir, dpi=pdf_dpi)
    elif is_html:
        per_page_images = []  # no hay imágenes
    else:
        # imágenes (incluye .webp)
        per_page_images = [local_path]

    # 2) OCR o texto HTML
    ocr = {"texts": [], "stats": {"pages": 0, "total_chars": 0, "time_ms": 0}}
    if is_html:
        text = html_to_text(local_path)
        ocr["texts"] = [text]
        ocr["stats"] = {"pages": 1, "total_chars": len(text), "time_ms": 0}
    elif options.get("ocr_enabled", True):
        ocr = ocr_images(per_page_images, lang=language)

    # 3) Metadatos
    meta = {}
    if config["features"]["enable_metadata"]:
        meta = read_metadata_exiftool(local_path)

    # 4) Razones / señales
    reasons = []
    if config["features"]["enable_metadata"]:
        reasons += reasons_from_metadata(meta)
    if config["features"]["enable_text"]:
        summary = summarize_text(ocr["texts"])
        reasons += reasons_from_text(document_type, summary)
    if config["features"]["enable_visual"]:
        reasons += reasons_from_images(per_page_images)

    # 5) Scoring heurístico (sumatoria de pesos, cap en 1.0)
    raw_score = sum(w for _, _, w in reasons)
    score01 = min(max(raw_score, 0.0), 1.0)
    score100 = max(1, min(100, round(score01 * 100)))  # 1..100

    label = map_label(score01, thresholds["low"], thresholds["high"])

    # 6) Respuesta
    reasons_out = [{"code": c, "message": m, "weight": w} for (c, m, w) in reasons]
    per_page = [{"page": i+1, "score": score01, "reasons": []} for i in range(len(per_page_images))]  # placeholder
    res = {
        "risk_score01": round(score01, 4),
        "risk_score100": int(score100),
        "risk_label": label,
        "reasons": reasons_out,
        "per_page": per_page,
        "model_version": get_versions()["model_version"],
        "debug": {
            "file_hash": file_hash,
            "metadata_summary": {k: meta.get(k) for k in ["Producer", "Creator", "ModifyDate", "CreateDate"]},
            "ocr_stats": ocr["stats"],
        },
        "validadoIA": True,
        "warnings": []
    }

    # limpiar páginas temporales si corresponde
    if temp_pages_dir and not config["paths"].get("keep_temp", False):
        shutil.rmtree(temp_pages_dir, ignore_errors=True)

    return res
