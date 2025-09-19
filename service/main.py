import os, time, yaml
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi.openapi.utils import get_openapi

APP_YAML = os.environ.get("APP_CONFIG", "configs/app.yaml")

with open(APP_YAML, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

app = FastAPI(title=CONFIG["service"]["name"], version=CONFIG["service"]["version"])

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    # Si existe /score-multipart, borramos la respuesta 422 para "limpiar" la vista
    try:
        schema["paths"]["/score-multipart"]["post"]["responses"].pop("422", None)
    except KeyError:
        pass
    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi

# CORS abierto en dev (ajustá en prod)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Exponer config a otros módulos
def get_config():
    return CONFIG

@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok", "version": CONFIG["service"]["version"], "time": int(time.time())}

# Registrar rutas del servicio
from service.routes import router as score_router  # noqa
app.include_router(score_router)
