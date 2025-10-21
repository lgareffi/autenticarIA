import os, time, tempfile, shutil
# from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
# from fastapi.responses import JSONResponse
# from service.main import get_config
# from service.schemas import ScoreRequestJSON, ScoreResponse
# from models.loader import get_versions
# from pipeline.ingest import ensure_local_file, sniff_ext
# from models.infer import analyze_document
from models.infer_ml import analyze_document_ml
from pathlib import Path

router = APIRouter()

# def require_key_if_enabled(cfg=Depends(get_config)):
#     if cfg["service"].get("require_api_key"):
#         # ejemplo simple, en prod: validar header X-API-Key con os.environ[cfg["security"]["api_key_env"]]
#         pass

# @router.post("/score", response_model=ScoreResponse, include_in_schema=False)
# def score_json(req: ScoreRequestJSON, _=Depends(require_key_if_enabled)):
#     cfg = get_config()
#     t0 = time.time()
#     workdir = cfg["paths"]["workdir"]
#     os.makedirs(workdir, exist_ok=True)

#     local_path, temp_dir = ensure_local_file(req.document_path, workdir)
#     try:
#         res = analyze_document(
#             local_path=local_path,
#             document_type=req.document_type,
#             language=req.language,
#             options=req.options.model_dump(),
#             config=cfg
#         )
#         res["processing_time_ms"] = int((time.time() - t0)*1000)
#         res["pipeline_version"] = cfg["service"]["version"]
#         res["config_version"] = time.strftime("%Y-%m-%d")
#         return JSONResponse(res)
#     finally:
#         if not cfg["paths"].get("keep_temp", False) and temp_dir and os.path.isdir(temp_dir):
#             shutil.rmtree(temp_dir, ignore_errors=True)

# @router.post("/score-multipart", response_model=ScoreResponse)
# def score_multipart(
#     file: UploadFile = File(...),
#     document_type: str = Form("OTRO"),
#     _=Depends(require_key_if_enabled)
# ):
#     cfg = get_config()
#     t0 = time.time()
#     workdir = cfg["paths"]["workdir"]
#     os.makedirs(workdir, exist_ok=True)

#     # Guardar el archivo subido a una carpeta temporal
#     temp_dir = tempfile.mkdtemp(dir=workdir)
#     ext = sniff_ext(file.filename or "file.bin")
#     local_path = os.path.join(temp_dir, f"upload{ext}")
#     with open(local_path, "wb") as f:
#         f.write(file.file.read())

#     try:
#         res = analyze_document(
#             local_path=local_path,
#             document_type=document_type,
#             language="spa",
#             options={"ocr_enabled": True, "pdf_use_poppler": True, "debug": False},
#             config=cfg
#         )
#         res["processing_time_ms"] = int((time.time() - t0)*1000)
#         res["pipeline_version"] = cfg["service"]["version"]
#         res["config_version"] = time.strftime("%Y-%m-%d")
#         return JSONResponse(res)
#     finally:
#         if not cfg["paths"].get("keep_temp", False) and temp_dir and os.path.isdir(temp_dir):
#             shutil.rmtree(temp_dir, ignore_errors=True)

@router.post("/risk-ml")
async def risk_ml(file: UploadFile = File(...), language: str = "spa"):
    # Preservar la extensión (ej.: .pdf, .jpg, .png)
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