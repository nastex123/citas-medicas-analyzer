"""
Router (controlador) del recurso "analyze" para HU-015 (citas médicas).
Un router es un grupo de endpoints relacionados que luego se
"conecta" (include_router) a la app principal en app/main.py.

Aquí NO va lógica de negocio: solo se valida la petición
y se delega el trabajo real al servicio (app/services/analysis_service.py).
"""

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import MENSAJES_POR_DIA_DEFAULT, PRICE_PER_MILLION_TOKENS_USD
from app.models.schemas import AnalysisResponse, BatchAnalysisResponse, CitaRequest
from app.services.analysis_service import (
    analizar_cita,
    procesar_archivo_excel,
    procesar_archivo_excel_stream,
    procesar_carpeta_excel,
)

router = APIRouter(prefix="/api", tags=["Análisis de citas médicas"])


def _flag(optimizar_tokens: bool, optent_tokens: bool) -> bool:
    """Resuelve el flag aceptando ambos nombres (HU-015 y alias HU-012)."""
    return bool(optimizar_tokens or optent_tokens)


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_cita(payload: CitaRequest) -> AnalysisResponse:
    texto_es = payload.text.strip()
    if not texto_es:
        raise HTTPException(status_code=400, detail="El texto no puede estar vacío.")

    return analizar_cita(texto_es, optimizar_tokens=payload.optimizar_tokens)


@router.post("/analyze/upload", response_model=BatchAnalysisResponse)
async def analyze_upload(
    file: UploadFile,
    optimizar_tokens: bool = Form(False),
    optent_tokens: bool = Form(False),
) -> BatchAnalysisResponse:
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .xlsx.")

    contents = await file.read()
    flag = _flag(optimizar_tokens, optent_tokens)
    results = procesar_archivo_excel(contents, optimizar_tokens=flag)
    return BatchAnalysisResponse(total=len(results), results=results)


@router.post("/analyze/upload/stream")
async def analyze_upload_stream(
    file: UploadFile,
    optimizar_tokens: bool = Form(False),
    optent_tokens: bool = Form(False),
):
    if not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .xlsx.")
    contents = await file.read()
    flag = _flag(optimizar_tokens, optent_tokens)
    return StreamingResponse(
        procesar_archivo_excel_stream(contents, optimizar_tokens=flag),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/analyze/folder", response_model=BatchAnalysisResponse)
async def analyze_folder(
    folder_path: str = Form(...),
    optimizar_tokens: bool = Form(False),
    optent_tokens: bool = Form(False),
) -> BatchAnalysisResponse:
    path = Path(folder_path)
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"La carpeta no existe: {folder_path}")

    flag = _flag(optimizar_tokens, optent_tokens)
    try:
        results = procesar_carpeta_excel(path, optimizar_tokens=flag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BatchAnalysisResponse(total=len(results), results=results)


@router.get("/analyze/export")
async def export_results(
    format: str = "json",
    optimizar_tokens: bool = False,
) -> dict:
    return {
        "format": format,
        "note": "Export endpoint requires prior batch processing via /api/analyze/upload or /api/analyze/folder",
        "supported_formats": ["json", "excel"],
        "schema": {"accion": "reprogramar", "especialidad": "cardiologia", "preferencia_horario": "manana"},
    }


def _estimar_tokens_por_mensaje(optimizar_tokens: bool) -> dict:
    texto_ejemplo = (
        "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo "
        "para la próxima semana en el horario de la mañana."
    )
    count_es = 46
    count_en = 38 if optimizar_tokens else count_es
    return {"es": count_es, "en": count_en}


@router.get("/analyze/cost-estimate")
async def cost_estimate(
    messages_per_day: int = MENSAJES_POR_DIA_DEFAULT,
    optimizar_tokens: bool = False,
) -> dict:
    tokens = _estimar_tokens_por_mensaje(optimizar_tokens)
    costo_directo = (tokens["es"] * messages_per_day / 1_000_000) * PRICE_PER_MILLION_TOKENS_USD
    costo_optimizado = (tokens["en"] * messages_per_day / 1_000_000) * PRICE_PER_MILLION_TOKENS_USD
    ahorro_diario = costo_directo - costo_optimizado
    return {
        "messages_per_day": messages_per_day,
        "estimated_tokens_es": tokens["es"] * messages_per_day,
        "estimated_tokens_en": tokens["en"] * messages_per_day,
        "costo_directo_usd": round(costo_directo, 4),
        "costo_optimizado_usd": round(costo_optimizado, 4),
        "ahorro_diario_usd": round(ahorro_diario, 4),
        "ahorro_mensual_usd": round(ahorro_diario * 30, 4),
        "ahorro_anual_usd": round(ahorro_diario * 365, 4),
        "precio_por_millon_usd": PRICE_PER_MILLION_TOKENS_USD,
        "optimizar_tokens": optimizar_tokens,
    }
