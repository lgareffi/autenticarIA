import os, tempfile, shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from models.infer_ml import analyze_document_ml
from pathlib import Path

router = APIRouter()

@router.post("/risk-ml")
async def risk_ml(file: UploadFile = File(...), language: str = "spa"):
    suffix = Path(file.filename).suffix
    if not suffix and file.content_type == "application/pdf":
        suffix = ".pdf"

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"No se pudo guardar el archivo: {e}")

    try:
        result = analyze_document_ml(tmp_path, language=language)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error en análisis ML: {e}")
    finally:
        os.unlink(tmp_path)