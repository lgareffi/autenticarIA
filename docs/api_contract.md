contrato del endpoint /score 

Endpoint: POST /score
Descripción: recibe una referencia al documento, lo procesa y devuelve un risk_score y reasons.

Request (JSON)

- document_path (string): ruta local o URL interna segura donde está el archivo.
- document_type (string): tipo de documento (ej: “VTV”, “titulo”, “cedula”, “informe”).
- options (objeto opcional): flags como only_ocr, fast_mode, etc.
- request_id (string opcional): id para trazabilidad.

Response (JSON)

- risk_score (float 0.0–1.0)
- risk_label (string: “low” | “medium” | “high”)
- reasons (array de strings cortos)
- model_version (string, ej: “v0.1”)
- processing_time_ms (entero)
- debug (objeto opcional con detalles: metadatos clave, warnings)

Errores comunes

- 400: input inválido (falta document_path o no accesible)
- 415: formato de archivo no soportado
- 500: error interno de pipeline/OCR/modelo

SLA inicial
p95 < 3 s en imágenes/pdfs simples, en dev local.

Con esto, tu backend Java ya puede simular llamadas y preparar su cliente HTTP, aunque el servicio aún no tenga lógica.