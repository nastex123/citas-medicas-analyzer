"""
Punto de entrada del backend HU-015.

Este es el archivo que arranca todo. Aquí se "conectan" las piezas:
  routers (endpoints)  --->  app FastAPI  --->  servidor uvicorn

Cómo se levanta el servidor (desde la carpeta backend/):
    uvicorn app.main:app --reload

Documentación interactiva generada automáticamente:
    http://127.0.0.1:8000/docs      (Swagger UI)
    http://127.0.0.1:8000/redoc     (ReDoc)
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    BANNER_RESET,
    GEOXOR_BANNER_LINES,
    RAINBOW_COLORS,
)
from app.routers import analyze


def _imprimir_banner() -> None:
    """Imprime el banner rainbow Geoxor en el arranque."""
    for i, line in enumerate(GEOXOR_BANNER_LINES):
        color = RAINBOW_COLORS[i % len(RAINBOW_COLORS)]
        print(f"{color}{line}{BANNER_RESET}")


app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
)

_imprimir_banner()
print(f"{APP_TITLE} v{APP_VERSION}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router)

_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
