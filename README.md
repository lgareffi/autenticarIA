propósito del repo, cómo correr, y roadmap.

Backend Java recibe el archivo y lo guarda (o su URL interna segura).

Llama a POST /score del microservicio IA con document_path y document_type.

Persiste risk_score, risk_label, reasons, model_version.

Expone al frontend un endpoint propio (ej. /document/{id}/risk) con esos datos.