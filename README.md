# Gestión de Citas Médicas Analyzer — HU-015

API en FastAPI que ingiere solicitudes de reprogramación/cancelación de citas
médicas desde archivos Excel, evalúa la tokenización ES vs EN (o200k_base),
mide la fragmentación del vocabulario médico y extrae la intención estructurada
de cada mensaje.

Más información en [backend/docs/](backend/docs/) (instalación, API, arquitectura y ejemplos).

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/analyze` | Analizar un mensaje individual de cita médica |
| `POST` | `/api/analyze/upload` | Subir un archivo `.xlsx` con solicitudes de pacientes |
| `POST` | `/api/analyze/upload/stream` | Upload con progreso SSE |
| `POST` | `/api/analyze/folder` | Escaneo de carpeta con múltiples `.xlsx` |
| `GET` | `/api/analyze/export` | Exportar resultados en JSON o Excel |
| `GET` | `/api/analyze/cost-estimate` | Proyección económica (default 15,000 msgs/día) |

## Flujo de tokenización

```
optimizar_tokens=True:  ES → deep_translator → EN → extracción de intención
optimizar_tokens=False: ES → extracción de intención directa
```

## Esquema de salida

```json
{
  "accion": "reprogramar",
  "especialidad": "cardiologia",
  "preferencia_horario": "manana"
}
```

## Requisitos previos

- Python 3.12+
- `pip install -r requirements.txt` desde la carpeta `backend/`

## Modelos

Los archivos `*.joblib` **no se suben al repositorio** (el modelo de especialidad
supera el límite de 100 MB de GitHub). Para regenerarlos, desde la carpeta `backend/`:

```bash
python scripts/train_pipeline.py
```
