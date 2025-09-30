import os, re
from typing import Dict, Any, List, Tuple

# -------------------------
# Regex útiles
# -------------------------
DATE_RE = re.compile(r"\b(\d{2}[/-]\d{2}[/-]\d{4}|\d{4}[/-]\d{2}[/-]\d{2})\b")

# Patentes AR (formatos comunes AA999AA / AAA999)
PLATE_RE = re.compile(r"\b([A-Z]{2}\d{3}[A-Z]{2}|[A-Z]{3}\s?\d{3})\b")

# VIN básico (17 chars, sin I/O/Q)
VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")

# CUIT/CUIL con o sin guiones
CUIT_RE = re.compile(r"\b(20|23|24|27|30|33|34)-?\d{8}-?\d\b")

# Palabras que suelen marcar fechas de vigencia/vencimiento
VTO_RE = re.compile(r"\b(venc(?:imiento)?|vto\.?|expira|vigencia|validez)\b", re.I)

# Palabras típicas de emisores/entidades
EMISOR_RE = re.compile(r"\b(aseguradora|compañ[ií]a|provincia seguros|sancor|zurich|seguro|registro|ministerio|entidad|dnrpa|vtv|verificaci[oó]n)\b", re.I)

# Nombre y apellido (para Creator "persona")
PERSON_LIKE = re.compile(r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+$")

# Listas de software
SUSP_SOFTWARE = ["photoshop", "gimp", "illustrator", "corel", "paint.net", "canva", "inkscape"]
TRUSTABLE_PRODUCERS = ["adobe pdf library", "microsoft word", "libreoffice", "pdf-xchange", "foxit"]

# -------------------------
# Helpers
# -------------------------
def _parse_exif_dt(s: str):
    """Acepta 'YYYY:MM:DD HH:MM:SS' o ISO 'YYYY-MM-DDTHH:MM:SS' y devuelve tupla (YYYY,MM,DD,HH,MM,SS) o None."""
    if not s:
        return None
    s = s.strip()
    try:
        # EXIF clásico
        if ":" in s[4:5]:
            parts = re.split(r"[:\s]", s[:19])
        else:
            # ISO
            parts = re.split(r"[-T:]", s[:19])
        nums = list(map(int, parts[:6]))
        if len(nums) == 6:
            return tuple(nums)
    except Exception:
        return None
    return None

def _cuit_is_valid(raw: str) -> bool:
    """Valida dígito verificador CUIT/CUIL."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) != 11:
        return False
    coefs = [5,4,3,2,7,6,5,4,3,2]
    s = sum(int(d)*c for d, c in zip(digits[:10], coefs))
    check = 11 - (s % 11)
    check = 0 if check == 11 else (9 if check == 10 else check)
    return check == int(digits[-1])

# -------------------------
# Resumen de texto
# -------------------------
def summarize_text(texts: List[str]) -> Dict[str, Any]:
    joined = "\n".join(t or "" for t in texts)
    has_date = bool(DATE_RE.search(joined))
    length = len(joined)

    # señales adicionales (para que reasons_from_text tenga más opciones)
    has_patente = bool(PLATE_RE.search(joined))
    has_vin = bool(VIN_RE.search(joined))
    has_cuit = bool(CUIT_RE.search(joined))
    has_vencimiento = bool(VTO_RE.search(joined))
    has_entidad_emisora = bool(EMISOR_RE.search(joined))

    return {
        "has_date": has_date,
        "length": length,
        "has_patente": has_patente,
        "has_vin": has_vin,
        "has_cuit": has_cuit,
        "has_vencimiento": has_vencimiento,
        "has_entidad_emisora": has_entidad_emisora,
        "raw_text": joined  # por si querés usarlo en más reglas
    }

# -------------------------
# Reglas basadas en metadatos
# -------------------------
def reasons_from_metadata(meta: dict) -> List[Tuple[str, str, float]]:
    reasons: List[Tuple[str, str, float]] = []
    prod = (meta.get("Producer") or "").strip()
    creator = (meta.get("Creator") or "").strip()

    combo = f"{prod} {creator}".lower()
    if any(w in combo for w in SUSP_SOFTWARE):
        reasons.append(("META_PRODUCER_SUSPICIOUS", "Metadatos sugieren edición con software gráfico", 0.15))

    # Producer desconocido o faltante (señales suaves)
    if not prod:
        reasons.append(("META_PRODUCER_MISSING", "El PDF/imagen no expone Producer", 0.03))
    else:
        prod_low = prod.lower()
        if all(w not in prod_low for w in TRUSTABLE_PRODUCERS) and all(w not in prod_low for w in SUSP_SOFTWARE):
            reasons.append(("META_PRODUCER_UNKNOWN", f"Producer inusual: {prod}", 0.03))

    # Creator parece nombre y apellido (débil)
    if creator and PERSON_LIKE.match(creator):
        reasons.append(("META_CREATOR_PERSON_NAME", f"Creator parece un nombre propio: {creator}", 0.05))

    # Inconsistencias de fechas
    c = meta.get("CreateDate") or meta.get("CreationDate") or ""
    m = meta.get("ModifyDate") or ""
    cdt = _parse_exif_dt(c)
    mdt = _parse_exif_dt(m)
    if cdt and mdt:
        # ModifyDate < CreateDate
        if mdt < cdt:
            reasons.append(("META_DATE_MISMATCH", "ModifyDate anterior a CreateDate", 0.05))
        # Modificación muy posterior (> 2 años)
        year_gap = (mdt[0] - cdt[0])
        if year_gap > 2:
            reasons.append(("META_DATE_LARGE_GAP", "Modificación muy posterior a la creación", 0.03))

    return reasons

# -------------------------
# Reglas basadas en texto
# -------------------------
def reasons_from_text(doc_type: str, text_summary: Dict[str, Any]) -> List[Tuple[str, str, float]]:
    r: List[Tuple[str, str, float]] = []

    # 1) Fecha obligatoria para ciertos tipos
    if doc_type in ["VTV", "SEGURO", "TITULO", "INFORME", "CEDULA", "SERVICIO"] and not text_summary["has_date"]:
        r.append(("OCR_FIELD_MISSING_DATE", "No se detectó una fecha válida en el texto", 0.20))

    # 2) Texto corto (umbral más alto para tener más recall)
    if text_summary["length"] < 120:
        r.append(("OCR_TEXT_TOO_SHORT", "Muy poco texto reconocido (posible baja calidad)", 0.10))

    # 3) CUIT detectado pero inválido (fuerte)
    m_cuit = CUIT_RE.search(text_summary["raw_text"])
    if m_cuit:
        if not _cuit_is_valid(m_cuit.group(0)):
            r.append(("OCR_INVALID_CUIT", "CUIT/CUIL detectado con dígito verificador inválido", 0.10))

    # 4) VIN con formato sospechoso (por ahora chequeo básico de 17 chars sin I/O/Q)
    #    Si aparece algo que "parece" VIN pero no cumple, agregá señal.
    #    Implementación simple: si hay un bloque alfanumérico largo con I/O/Q, marcar.
    long_alnum = re.findall(r"\b[A-Z0-9]{15,20}\b", text_summary["raw_text"])
    for token in long_alnum:
        if len(token) == 17 and not VIN_RE.fullmatch(token) and any(ch in token for ch in "IOQ"):
            r.append(("OCR_VIN_FORMAT_SUSPECT", "Secuencia tipo VIN con caracteres inválidos (I/O/Q)", 0.08))
            break

    # 5) Señal de vigencia/vencimiento ausente cuando se esperan (SEGURO/VTV)
    if doc_type in ["SEGURO", "VTV"] and not text_summary.get("has_vencimiento", False):
        r.append(("OCR_MISSING_VIGENCIA", "No se detecta campo de vigencia/vencimiento esperado", 0.06))

    # 6) Emisor detectado (débil si no aparece ninguna entidad)
    if doc_type in ["SEGURO", "VTV", "INFORME"] and not text_summary.get("has_entidad_emisora", False):
        r.append(("OCR_MISSING_EMISOR", "No se detecta entidad emisora/compañía en el texto", 0.04))

    return r

# -------------------------
# Reglas basadas en imágenes
# -------------------------
def reasons_from_images(images: List[str]) -> List[Tuple[str, str, float]]:
    r: List[Tuple[str, str, float]] = []
    try:
        from PIL import Image
        import os

        for p in images:
            try:
                with Image.open(p) as im:
                    w, h = im.width, im.height
                    area = w * h
                    if area < 400 * 400:  # muy baja resolución
                        r.append(("IMAGE_LOW_RES", "Resolución de página muy baja", 0.10))
                        break

                    # Heurística de sobre-compresión (bytes por píxel muy bajo en JPEG)
                    try:
                        file_size = os.path.getsize(p)
                        bpp = file_size / float(max(1, area))
                        if (im.format or "").upper() in ("JPG", "JPEG") and bpp < 0.08:
                            r.append(("IMAGE_OVERCOMPRESSED", "Imagen JPEG con compresión agresiva", 0.05))
                    except Exception:
                        pass
            except Exception:
                # si no se puede abrir, saltear ese frame
                continue

        # Desenfoque (si tenés OpenCV disponible)
        try:
            import cv2
            import numpy as np
            for p in images:
                img = cv2.imdecode(np.fromfile(p, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                fm = cv2.Laplacian(img, cv2.CV_64F).var()
                if fm < 20.0:  # umbral conservador; ajustá mirando tus datos
                    r.append(("IMAGE_BLURRY", "Imagen borrosa (baja nitidez)", 0.08))
                    break
        except Exception:
            pass

    except Exception:
        # PIL no disponible: devolvemos lo que tengamos
        pass

    return r
