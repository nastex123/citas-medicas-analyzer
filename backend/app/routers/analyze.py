"""
Router (controlador) del recurso "analyze" para HU-015 (citas médicas).
Un router es un grupo de endpoints relacionados que luego se
"conecta" (include_router) a la app principal en app/main.py.

Aquí NO va lógica de negocio: solo se valida la petición
y se delega el trabajo real al servicio (app/services/analysis_service.py).
"""

import io
import time
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import MENSAJES_POR_DIA_DEFAULT, PRICE_PER_MILLION_TOKENS_USD
from app.models.schemas import (
    AnalysisResponse,
    BatchAnalysisResponse,
    CitaRequest,
    ExportRequest,
    MessageDetail,
)
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
    results, details, timings = procesar_archivo_excel(contents, optimizar_tokens=flag)
    return BatchAnalysisResponse(
        total=len(results),
        results=results,
        timings=timings,
        details=details,
    )


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
        results, details, timings = procesar_carpeta_excel(path, optimizar_tokens=flag)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return BatchAnalysisResponse(
        total=len(results),
        results=results,
        timings=timings,
        details=details,
    )


def _generar_excel_export(details: list) -> bytes:
    """Construye el .xlsx con una fila por mensaje: parámetros, mensajes ES/limpio/EN y tokens."""
    filas = []
    for d in details:
        costo_en = (d.tokens_en / 1_000_000) * PRICE_PER_MILLION_TOKENS_USD
        filas.append({
            "Especialidad médica": d.especialidad_medica,
            "ID paciente": d.id_paciente,
            "Paciente": d.paciente,
            "Cluster ID": d.cluster_id,
            "Mensajes en clúster": d.messages_in_cluster,
            "Texto original": d.texto_original,
            "Texto limpio": d.texto_limpio,
            "Texto en inglés": d.texto_en,
            "Acción": d.accion,
            "Preferencia horario": d.preferencia_horario,
            "Tokens ES": d.tokens_es,
            "Tokens EN": d.tokens_en,
            "Tokens ahorrados/request": max(0, d.tokens_es - d.tokens_en),
            "Ratio fragmentación ES/EN": d.fragmentacion_ratio,
            "Costo USD (EN)": round(costo_en, 4),
        })

    df = pd.DataFrame(filas)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Análisis")
    return buf.getvalue()


@router.post("/analyze/export")
async def export_results(payload: ExportRequest) -> StreamingResponse:
    if payload.details:
        detalle_export = payload.details
    elif payload.results:
        detalle_export = [
            MessageDetail(
                id_paciente=ed.id_paciente,
                paciente=ed.paciente,
                especialidad_medica=ed.especialidad_medica,
                cluster_id=ed.cluster_id,
                messages_in_cluster=ed.messages_in_cluster,
                accion=ed.intent.accion,
                preferencia_horario=ed.intent.preferencia_horario,
                texto_original=ed.texto_original,
                texto_limpio=ed.texto_limpio,
                texto_en=ed.texto_en,
                tokens_es=m.original_tokens,
                tokens_en=m.translated_tokens,
                fragmentacion_ratio=m.fragmentacion_ratio,
            )
            for r in payload.results
            for ed, m in [(r.extracted_data, r.metrics)]
        ]
    else:
        raise HTTPException(status_code=400, detail="No hay datos para exportar.")

    contenido = _generar_excel_export(detalle_export)
    nombre = f"citas_analysis_{int(time.time())}.xlsx"
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
        },
    )


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
