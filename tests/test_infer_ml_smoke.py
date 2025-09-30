import pathlib
from models.infer_ml import analyze_document_ml

def test_infer_ml_importable():
    # smoke: solo carga el modelo y ejecuta con un HTML simple (evita OCR)
    root = pathlib.Path(__file__).resolve().parents[1]
    sample = root / "samples" / "dummy.html"
    sample.parent.mkdir(exist_ok=True)
    sample.write_text("<html><body>Prueba CUIT 20-12345678-3 Emisor X</body></html>", encoding="utf-8")

    res = analyze_document_ml(str(sample))
    assert "risk_score" in res and "risk_label" in res
