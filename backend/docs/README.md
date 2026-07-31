# Documentación — Gestión de Citas Médicas Analyzer (HU-015)

API en FastAPI que ingiere solicitudes de reprogramación/cancelación de citas
médicas desde archivos Excel y evalúa la tokenización ES vs EN.

## Contenido

- [Instalación y configuración](Instalacion.md)
- [Referencia de la API](API.md)
- [Arquitectura](Arquitectura.md)
- [Ejemplos de uso](Ejemplos.md)

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/analyze` | Analizar un mensaje individual de cita médica |
| `POST` | `/api/analyze/upload` | Subir un archivo `.xlsx` con solicitudes de pacientes |
| `POST` | `/api/analyze/upload/stream` | Upload con progreso SSE (envía `details` en lotes) |
| `POST` | `/api/analyze/folder` | Escaneo de carpeta con múltiples `.xlsx` |
| `POST` | `/api/analyze/export` | Exportar `.xlsx` con una fila por mensaje (recibe `details`) |
| `GET` | `/api/analyze/cost-estimate` | Proyección económica (default 15,000 msgs/día) |

## Flujo de tokenización

```
optimizar_tokens=True:  ES → limpieza → deep_translator → EN → conteo de tokens
optimizar_tokens=False: ES → limpieza → conteo de tokens directo
```

## Esquema de intención extraída

```json
{"accion": "reprogramar", "especialidad": "cardiologia", "preferencia_horario": "manana"}
```

## Requisitos previos

- Python 3.12+
- `pip install -r requirements.txt` desde la carpeta `backend/`
