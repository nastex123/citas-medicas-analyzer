"""
Schemas (modelos Pydantic) que definen la forma de los datos
que entran y salen de la API. FastAPI los usa para:
  1) Validar automáticamente lo que envía el cliente.
  2) Documentar la API en /docs (Swagger) sin esfuerzo extra.
"""

from pydantic import BaseModel, ConfigDict, Field


class CitaRequest(BaseModel):
    """Lo que el cliente envía: el texto del mensaje de la cita en español.

    `optimizar_tokens` es el nombre canónico de la HU-015; se acepta también
    `optent_tokens` como alias para mantener compatibilidad con HU-012.
    """
    text: str
    optimizar_tokens: bool = Field(default=False, alias="optent_tokens")

    model_config = ConfigDict(populate_by_name=True)


class TokenMetrics(BaseModel):
    """Métricas de tokens, para comparar el costo ES vs EN."""
    original_tokens: int
    translated_tokens: int
    tokens_saved_per_request: int
    fragmentacion_ratio: float = 1.0


class CitaIntent(BaseModel):
    """Intención extraída del mensaje del paciente."""
    accion: str = "otro"
    especialidad: str = "sin_especificar"
    preferencia_horario: str = "sin_preferencia"


class ExtractedCitaData(BaseModel):
    """Datos estructurados que se extraen del mensaje de cita."""
    intent: CitaIntent
    summary_es: str
    summary_en: str
    id_paciente: str = ""
    paciente: str = ""
    especialidad_medica: str = ""
    cluster_id: int = -1
    messages_in_cluster: int = 0
    texto_original: str = ""
    texto_limpio: str = ""
    texto_en: str = ""


class AnalysisResponse(BaseModel):
    """Respuesta completa que devuelve el endpoint /api/analyze."""
    metrics: TokenMetrics
    extracted_data: ExtractedCitaData


class MessageDetail(BaseModel):
    """Detalle por mensaje individual (una fila por mensaje en el export)."""
    id_paciente: str = ""
    paciente: str = ""
    especialidad_medica: str = ""
    cluster_id: int = -1
    messages_in_cluster: int = 0
    accion: str = "otro"
    preferencia_horario: str = "sin_preferencia"
    texto_original: str = ""
    texto_limpio: str = ""
    texto_en: str = ""
    tokens_es: int = 0
    tokens_en: int = 0
    fragmentacion_ratio: float = 1.0


class BatchAnalysisResponse(BaseModel):
    """Respuesta para procesamiento por lotes (upload / folder)."""
    total: int
    results: list[AnalysisResponse]
    timings: dict[str, float] = Field(default_factory=dict)
    details: list[MessageDetail] = Field(default_factory=list)


class ExportRequest(BaseModel):
    """Cuerpo de la petición de exportación a .xlsx."""
    details: list[MessageDetail] = Field(default_factory=list)
    results: list[AnalysisResponse] = Field(default_factory=list)
