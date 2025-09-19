import os, re
from typing import Dict, Any, List, Tuple

DATE_RE = re.compile(r"\b(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})\b")

SUSP_SOFTWARE = ["photoshop", "gimp", "illustrator", "corel", "paint.net", "canva"]

def summarize_text(texts: List[str]) -> Dict[str, Any]:
    joined = "\n".join(texts)
    has_date = bool(DATE_RE.search(joined))
    length = len(joined)
    return {"has_date": has_date, "length": length}

def reasons_from_metadata(meta: dict) -> List[Tuple[str, str, float]]:
    reasons = []
    prod = (meta.get("Producer") or meta.get("PDFVersion") or "")
    creator = (meta.get("Creator") or "")
    combo = f"{prod} {creator}".lower()
    if any(w in combo for w in SUSP_SOFTWARE):
        reasons.append(("META_PRODUCER_SUSPICIOUS", "Metadatos sugieren edición con software gráfico", 0.25))
    return reasons

def reasons_from_text(doc_type: str, text_summary: Dict[str, Any]) -> List[Tuple[str, str, float]]:
    r = []
    if doc_type in ["VTV", "SEGURO", "TITULO", "INFORME"] and not text_summary["has_date"]:
        r.append(("OCR_FIELD_MISSING_DATE", "No se detectó una fecha válida en el texto", 0.20))
    if text_summary["length"] < 50:
        r.append(("OCR_TEXT_TOO_SHORT", "Muy poco texto reconocido (posible baja calidad)", 0.10))
    return r

def reasons_from_images(images: List[str]) -> List[Tuple[str, str, float]]:
    # Heurística muy simple: archivos muy pequeños (resolución) son sospechosos
    r = []
    try:
        from PIL import Image
        for p in images:
            with Image.open(p) as im:
                if im.width * im.height < 400*400:  # menor a 400x400 px
                    r.append(("IMAGE_LOW_RES", "Resolución de página muy baja", 0.10))
                    break
    except Exception:
        pass
    return r
