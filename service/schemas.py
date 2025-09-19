from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict, Any

class ScoreOptions(BaseModel):
    ocr_enabled: bool = True
    pdf_use_poppler: bool = True
    debug: bool = False

class ScoreRequestJSON(BaseModel):
    document_path: str = Field(..., description="Ruta local o URL http(s) del documento")
    document_type: Literal["TITULO", "CEDULA", "VTV", "SEGURO", "INFORME", "OTRO"] = "OTRO"
    language: str = "spa"
    options: ScoreOptions = ScoreOptions()
    request_id: Optional[str] = None

class PageScore(BaseModel):
    page: int
    score: float
    reasons: List[str] = []

class Reason(BaseModel):
    code: str
    message: str
    weight: float

class ScoreResponse(BaseModel):
    risk_score01: float
    risk_score100: int
    risk_label: Literal["low", "medium", "high"]
    reasons: List[Reason]
    per_page: List[PageScore] = []
    model_version: str
    pipeline_version: str
    config_version: str
    processing_time_ms: int
    validadoIA: bool = True
    debug: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
