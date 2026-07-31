# Resumen de implementación — HU-015

**Ingesta flexible y evaluación de costo/tokenización para gestión de citas médicas vía Excel**

Fecha de finalización: 30/07/2026

---

## Flujo de procesamiento

```
optimizar_tokens=False:  Mensaje ES → limpieza → Clustering (TF-IDF + KMeans por especialidad) → intención en lote (HashingVectorizer + LinearSVC) → tokens ES
optimizar_tokens=True:   Mensaje ES → limpieza → deep_translator → EN → Clustering → intención en lote → tokens EN (representativos)
```

- `deep_translator` usa Google Translate como backend (sin API key). Solo se activa cuando `optimizar_tokens=True`.
- `scikit-learn` (3× LinearSVC) extrae `accion`, `especialidad`, `preferencia_horario` — **sin Ollama ni LLM local**.
- La limpieza (`_limpiar_texto`) aplica strip, colapsa espacios y quita emojis.
- Clustering por especialidad reduce 50k solicitudes a ~60 grupos representativos.
- `fragmentacion_ratio = tokens_es / tokens_en` cuantifica la fragmentación del vocabulario médico.
- `_predecir_intencion_lote` predice la intención de todos los mensajes en una sola vectorización.

---

## Endpoints implementados

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/analyze` | Analizar un mensaje de cita individual (JSON + `optimizar_tokens`) |
| `POST` | `/api/analyze/upload` | Subir un archivo `.xlsx` y procesar todas las solicitudes (JSON) |
| `POST` | `/api/analyze/upload/stream` | Subir `.xlsx` con progreso en tiempo real (SSE, `details` en lotes de 500) |
| `POST` | `/api/analyze/folder` | Indicar ruta de carpeta y procesar todos los `.xlsx` |
| `POST` | `/api/analyze/export` | Generar `.xlsx` con una fila por mensaje (recibe `details`) |
| `GET` | `/api/analyze/cost-estimate` | Estimación de costo para N mensajes/día (default 15,000) |
| `GET` | `/` | Frontend HTML (servido por StaticFiles) |

---

## Archivos creados

| Archivo | Descripción |
|---|---|
| `scripts/generate_citas.py` | Genera `data/citas_medicas_solicitudes.xlsx` (10,000 solicitudes) |
| `scripts/train_pipeline.py` | Entrena 3 LinearSVC + HashingVectorizer con pseudo-labels |
| `scripts/procesar_excel_async.py` | Cliente batch asíncrono (asyncio + httpx) |
| `app/models/__init__.py` | Paquete de modelos |
| `app/models/vectorizer.joblib` | HashingVectorizer entrenado (2^20 features) |
| `app/models/accion_model.joblib` | LinearSVC para `accion` (4 clases) |
| `app/models/horario_model.joblib` | LinearSVC para `preferencia_horario` (4 clases) |
| `app/models/especialidad_model.joblib` | LinearSVC para `especialidad` (13 clases) |
| `app/models/schemas.py` | `CitaRequest`, `CitaIntent`, `ExtractedCitaData`, `TokenMetrics`, `AnalysisResponse`, `MessageDetail`, `BatchAnalysisResponse`, `ExportRequest` |
| `app/core/config.py` | Constantes médicas, precio, 15,000 msgs/día, banner GEOXOR (fuente ANSI Shadow) |
| `app/services/analysis_service.py` | Pipeline médico (limpieza, intención en lote, clustering, tokens, `details`, timings, SSE) |
| `app/routers/analyze.py` | 6 endpoints bajo `/api/analyze/*` |
| `app/main.py` | App FastAPI + banner GEOXOR + frontend estático |
| `frontend/index.html` | UI médica (modo archivo/carpeta, SSE, métricas, tiempos por etapa, gráficas Chart.js, tabla, export `.xlsx`) |
| `README.md` (raíz) | Documentación principal del proyecto |
| `backend/README.md` | Documentación del backend médico |
| `backend/docs/*.md` | Instalación, API, Arquitectura y Ejemplos |
| `documentacion/Plan_Implementacion_HU-015.md` | Plan de implementación |
| `documentacion/Resumen_HU-015.md` | Este archivo |

---

## Verificación

| Prueba | Resultado |
|---|---|
| `POST /api/analyze` con el ejemplo de la HU-015 | `{"accion": "reprogramar", "especialidad": "cardiologia", "preferencia_horario": "manana"}` |
| Tokens ES vs EN (mensaje HU-015, `optimizar_tokens=true`) | 28 ES / 23 EN, `fragmentacion_ratio` 1.2174 |
| `POST /api/analyze/upload` (50k solicitudes) | HTTP 200, `total` = 60 grupos y `details` ≈ 45,000 filas (una por mensaje) |
| `POST /api/analyze/export` | Genera `.xlsx` con 45,000 filas y 14 columnas |
| `GET /api/analyze/cost-estimate` | Responde con ahorro diario/mensual/anual |
| Entrenamiento (3 clasificadores) | Accuracy 1.0000 |

---

## Dependencias nuevas

| Paquete | Versión | Propósito |
|---|---|---|
| `faker` | 37.0.0 | Generación de datos de prueba (es_ES) |
| `scikit-learn`, `joblib`, `tiktoken`, `deep-translator`, `pyfiglet` | — | Reutilizadas del proyecto HU-012 |

---

## Notas técnicas

- **scikit-learn**: 3 × `LinearSVC` sobre `HashingVectorizer(2^20)`. Inferencia <1ms por mensaje.
- **deep_translator**: Google Translate como backend (sin API key). Considerar rate limiting para volúmenes altos.
- **Tokenización**: `tiktoken` con `o200k_base`; `fragmentacion_ratio` = ES/EN.
- **Precio**: `$2.50 USD por millón de tokens`; default 15,000 mensajes/día.
- **Detección de columnas**: heurística (`mensaje_texto`, `especialidad_medica`, `id_paciente` con fallbacks).
- **Clustering**: `MiniBatchKMeans` por especialidad (k=5, máx 10), `ThreadPoolExecutor` paralelo.
- **Timings por etapa**: se agregan con `max` entre especialidades (≈ tiempo de pared real) — `agrupacion`, `clustering`, `traduccion`, `tokenizacion`, `analisis`.
- **Export**: `details` (una fila por mensaje) viajan en el JSON/SSE y se vuelcan a `.xlsx` por `POST /api/analyze/export`.
- **Gráficas**: Chart.js v4 (CDN) en el frontend (tiempos, tokens ES/EN, acción, horario, especialidad, fragmentación).
- **Compatibilidad**: el flag `optimizar_tokens` acepta `optent_tokens` como alias.
- **SSE**: etapas `lectura`, `clustering`, `clasificacion`, `detalle` (lotes de 500), `completo`.
- **Entorno**: `venv` con Python 3.12 (Python 3.14 no soportado por los pins de `pydantic`/`tiktoken`).
