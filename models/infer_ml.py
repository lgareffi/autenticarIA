import json, pathlib
import joblib
import numpy as np
from typing import Dict, Any

# Reutilizamos tu pipeline actual
from pipeline.ingest import sniff_ext, pdf_to_images, html_to_text
from pipeline.ocr import ocr_images
from pipeline.metadata import read_metadata_exiftool
from pipeline.features import summarize_text, reasons_from_metadata, reasons_from_text, reasons_from_images

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

# carga artefactos
_model = joblib.load(MODELS / "rf_model.pkl")
_spec  = json.loads((MODELS / "feature_spec.json").read_text(encoding="utf-8"))
_FEATURES = _spec["features"]

def _build_feature_row(meta: dict, texts: list, images: list) -> Dict[str, Any]:
    # Basado en tu features.py y lo que está en el CSV
    # Derivamos las mismas señales que luego matchean columnas del dataset
    text_summary = summarize_text(texts)
    r_meta = reasons_from_metadata(meta)
    r_text = reasons_from_text(texts, text_summary)
    r_img  = reasons_from_images(images)

    # partir de los campos del CSV que ya existen:
    features: Dict[str, Any] = {
        "num_pages": text_summary.get("pages", len(texts) or len(images)),
        "file_size_bytes": int(meta.get("FileSize") or 0),
        "has_metadata": int(bool(meta)),
        "producer_suspicious": int(any(k == "META_PRODUCER_SUSPICIOUS" for k,_,_ in r_meta)),
        "ocr_total_chars": int(text_summary.get("total_chars", 0)),
        "ocr_pages_with_text": int(text_summary.get("pages_with_text", 0)),
        "ocr_chars_per_page_mean": float(text_summary.get("chars_per_page_mean", 0.0)),
        "has_date": int(text_summary.get("has_date", False)),
        "has_patente": int(text_summary.get("has_plate", False)),
        "has_vin": int(text_summary.get("has_vin", False)),
        "has_cuit": int(text_summary.get("has_cuit", False)),
        "has_vencimiento": int(text_summary.get("has_vigencia", False)),
        "has_entidad_emisora": int(text_summary.get("has_emisor", False)),
        "same_patente_all_pages": int(text_summary.get("same_plate_all_pages", False)),
        "min_resolution_px": int(text_summary.get("min_resolution_px", 0)),
        "low_res_flag": int(text_summary.get("low_res_flag", False)),
        "dpi_used": int(text_summary.get("dpi_used", 300)),
        # reglas → flags (coinciden con tus columnas rule_*)
        "rule_IMAGE_LOW_RES": int(any(k=="IMAGE_LOW_RES" for k,_,_ in r_img)),
        "rule_META_PRODUCER_UNKNOWN": int(any(k=="META_PRODUCER_UNKNOWN" for k,_,_ in r_meta)),
        "rule_META_PRODUCER_MISSING": int(any(k=="META_PRODUCER_MISSING" for k,_,_ in r_meta)),
        "rule_META_CREATOR_PERSON_NAME": int(any(k=="META_CREATOR_PERSON_NAME" for k,_,_ in r_meta)),
        "rule_META_DATE_MISMATCH": int(any(k=="META_DATE_MISMATCH" for k,_,_ in r_meta)),
        "rule_META_DATE_LARGE_GAP": int(any(k=="META_DATE_LARGE_GAP" for k,_,_ in r_meta)),
        "rule_OCR_INVALID_CUIT": int(any(k=="OCR_INVALID_CUIT" for k,_,_ in r_text)),
        "rule_OCR_VIN_FORMAT_SUSPECT": int(any(k=="OCR_VIN_FORMAT_SUSPECT" for k,_,_ in r_text)),
        "rule_OCR_MISSING_VIGENCIA": int(any(k=="OCR_MISSING_VIGENCIA" for k,_,_ in r_text)),
        "rule_OCR_MISSING_EMISOR": int(any(k=="OCR_MISSING_EMISOR" for k,_,_ in r_text)),
        "rule_IMAGE_OVERCOMPRESSED": int(any(k=="IMAGE_OVERCOMPRESSED" for k,_,_ in r_img)),
        "rule_IMAGE_BLURRY": int(any(k=="IMAGE_BLURRY" for k,_,_ in r_img)),
        "reasons_count": int(len(r_meta)+len(r_text)+len(r_img)),
    }

    # asegurar las columnas exactas del spec
    row = {c: 0 for c in _FEATURES}
    row.update({k: features.get(k, 0) for k in _FEATURES})
    return row, (r_meta + r_text + r_img), text_summary

def analyze_document_ml(local_path: str, language: str = "spa") -> Dict[str, Any]:
    # 1) Páginas/imágenes
    ext = sniff_ext(local_path)
    is_pdf = ext == ".pdf"
    is_html = ext in (".html", ".htm")

    per_page_images = []
    temp_dir = None
    if is_pdf:
        temp_dir = str(pathlib.Path(local_path).with_suffix("")) + "_pages"
        pathlib.Path(temp_dir).mkdir(exist_ok=True, parents=True)
        per_page_images = pdf_to_images(local_path, temp_dir, dpi=300)
    elif is_html:
        per_page_images = []
    else:
        per_page_images = [local_path]

    # 2) OCR o texto
    ocr = {"texts": [], "stats": {"pages": 0, "total_chars": 0, "time_ms": 0}}
    if is_html:
        text = html_to_text(local_path)
        ocr["texts"] = [text]
        ocr["stats"] = {"pages": 1, "total_chars": len(text), "time_ms": 0}
    else:
        ocr = ocr_images(per_page_images, lang=language)

    # 3) Metadatos
    meta = read_metadata_exiftool(local_path)

    # 4) Features y predicción
    row, reasons_all, text_summary = _build_feature_row(meta, ocr["texts"], per_page_images)
    X = np.array([[row[c] for c in _FEATURES]])
    y01 = float(_model.predict(X)[0])
    # revertir a escala 1–100 (misma convención del dataset)
    y_score_1_100 = max(0.0, min(100.0, y01 * 100.0))

    # mapeo simple a etiquetas (podés calibrar umbrales)
    label = "LOW" if y01 < 0.34 else "MEDIUM" if y01 < 0.67 else "HIGH"

    return {
        "risk_score": round(y_score_1_100, 2),
        "risk_label": label,
        "features_used": _FEATURES,
        "debug": {
            "ocr_stats": ocr["stats"],
            "metadata_summary": {k: meta.get(k) for k in ["Producer","Creator","ModifyDate","CreateDate"]},
            "text_summary": text_summary,
        },
        "reasons": [{"code": k, "msg": m, "w": w} for k,m,w in reasons_all],
        "validadoIA": True
    }
