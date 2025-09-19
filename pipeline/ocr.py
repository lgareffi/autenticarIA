from typing import List, Dict, Any
import pytesseract
from PIL import Image
import os, time

def ocr_images(images: List[str], lang: str = "spa") -> Dict[str, Any]:
    texts, per_page = [], []
    t0 = time.time()
    for i, img_path in enumerate(images, start=1):
        text = pytesseract.image_to_string(Image.open(img_path), lang=lang)
        texts.append(text)
        per_page.append({"page": i, "chars": len(text)})
    total = int(sum(p["chars"] for p in per_page))
    return {
        "texts": texts,
        "stats": {"pages": len(images), "total_chars": total, "time_ms": int((time.time()-t0)*1000)}
    }
