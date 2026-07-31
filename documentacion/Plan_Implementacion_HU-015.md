# Plan Implementación — HU-015

**Ingesta flexible y evaluación de costo/tokenización para gestión de citas médicas vía Excel**

---

## Flujo de procesamiento

```
optimizar_tokens=False:  Mensaje ES → Clustering (TF-IDF + KMeans por especialidad) → HashingVectorizer + LinearSVC → intención
optimizar_tokens=True:   Mensaje ES → deep_translator → EN → Clustering → HashingVectorizer + LinearSVC → intención
```

- `deep_translator` maneja ES→EN (Google Translate backend). Solo se usa cuando `optimizar_tokens=True`.
- `scikit-learn` (3× LinearSVC) extrae `accion`, `especialidad`, `preferencia_horario` — **sin Ollama ni LLM local**.
- Clustering por especialidad médica reduce 10k solicitudes a ~60 grupos representativos.
- `fragmentacion_ratio = tokens_es / tokens_en` mide la fragmentación del vocabulario médico.

---

## Requisitos previos

- Python 3.12+ (NO 3.14: sin wheels para `pydantic`/`tiktoken`)
- `pip install -r requirements.txt` desde `backend/`
- Primera vez: `python scripts/generate_citas.py` y `python scripts/train_pipeline.py`

---

## Fase 1 — Reutilización y adaptación del backend HU-012

**Objetivo:** Copiar la arquitectura probada de reseñas y adaptarla al dominio de citas médicas.

### Cambios

- `robocopy` de `backend/` + `frontend/` desde `29-IA-FOR-DEVS` (excluyendo `venv`, `__pycache__`, `*.xlsx`, `*.joblib`).
- Eliminados restos del dominio reseñas (`generar_excel.py`, etc.).
- Nombre del servicio: **Gestión de Citas Médicas Analyzer**.
- Se mantiene el banner GEOXOR (pyfiglet) y la estructura de capas (core/models/routers/services).

---

## Fase 2 — Generador de datos de citas médicas

**Objetivo:** Dataset realista de solicitudes de reprogramación/cancelación.

### `backend/scripts/generate_citas.py`

- 10,000 solicitudes con `faker` (es_ES).
- Columnas: `id_paciente`, `paciente`, `ciudad`, `especialidad_medica`, `fecha_solicitada`, `mensaje_texto`.
- 12 especialidades (cardiología, pediatría, dermatología, ...).
- 8 plantillas de mensaje (reprogramar/cancelar/consultar) con horarios (mañana/tarde/noche).
- 10% mensajes vacíos (dato sucio intencional).
- Salida: `backend/data/citas_medicas_solicitudes.xlsx`.

---

## Fase 3 — Entrenamiento de modelos médicos

**Objetivo:** Reentrenar los clasificadores para el dominio médico.

### `backend/scripts/train_pipeline.py`

- Pseudo-labels vía keywords para 3 objetivos:
  - `accion` (4 clases): reprogramar, cancelar, consultar, otra
  - `preferencia_horario` (4 clases): manana, tarde, noche, sin_preferencia
  - `especialidad` (13 clases): 12 especialidades + otra
- `HashingVectorizer(n_features=2^20, ngram_range=(1,2))`
- `LinearSVC` por objetivo; `_aumentar_balanceado()` sintetiza ejemplos hasta MIN_SAMPLES=250 por clase.
- Modelos guardados en `app/models/`:
  - `vectorizer.joblib`, `accion_model.joblib`, `horario_model.joblib`, `especialidad_model.joblib`
- Resultado de entrenamiento: accuracy 1.0000 en los 3 clasificadores.

---

## Fase 4 — Schemas Pydantic (dominio médico)

### `backend/app/models/schemas.py`

- `CitaRequest`: `text`, `optimizar_tokens` (con alias `optent_tokens`, `populate_by_name=True`).
- `CitaIntent`: `accion`, `especialidad`, `preferencia_horario`.
- `ExtractedCitaData`: `intent`, `summary_es`, `summary_en`, `id_paciente`, `especialidad_medica`, `cluster_id`, `messages_in_cluster`.
- `TokenMetrics`: `original_tokens`, `translated_tokens`, `tokens_saved_per_request`, `fragmentacion_ratio`.
- `AnalysisResponse`, `BatchAnalysisResponse`.

---

## Fase 5 — Servicio de análisis médico

### `backend/app/services/analysis_service.py`

- Carga de 4 modelos con `joblib`.
- `_validar_columnas()`: detecta columna de mensaje (`mensaje_texto`, `mensaje`, `texto`...), especialidad (`especialidad_medica`, `especialidad`...), paciente (`id_paciente`, `paciente_id`, `id`...).
- `_extraer_especialidad_texto()`: matcheo por keywords (`cardiologo` → `cardiologia`) antes del modelo.
- `_predecir_intencion()`: HashingVectorizer + LinearSVC para accion/horario; keywords + modelo para especialidad.
- Clustering por especialidad: `TfidfVectorizer(max_features=500, ngram_range=(1,2))` + `MiniBatchKMeans(k=5)`, máx 10 clusters/especialidad, mínimo 50 mensajes.
- Tokens con `tiktoken` (o200k_base) sobre todo el cluster; `fragmentacion_ratio` si `optimizar_tokens=True`.
- `procesar_archivo_excel()`, `procesar_carpeta()`, `procesar_archivo_excel_stream()` (SSE), `analizar_cita()`.

---

## Fase 6 — Endpoints

### `backend/app/routers/analyze.py`

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/analyze` | Análisis individual (JSON) |
| `POST` | `/api/analyze/upload` | Upload `.xlsx` → `BatchAnalysisResponse` |
| `POST` | `/api/analyze/upload/stream` | Upload con progreso SSE |
| `POST` | `/api/analyze/folder` | Escanear carpeta de `.xlsx` |
| `GET` | `/api/analyze/export` | Exportar JSON o Excel |
| `GET` | `/api/analyze/cost-estimate` | Proyección económica |

- `_flag()` resuelve el flag desde form `optimizar_tokens` o `optent_tokens`.

---

## Fase 7 — Análisis de impacto económico

**Objetivo:** Medir la fragmentación ES vs EN y su costo a $2.50 USD/M tokens.

```
costo_directo = (tokens_es_total / 1_000_000) * 2.50
costo_optimizado = (tokens_en_total / 1_000_000) * 2.50
ahorro_diario = costo_directo - costo_optimizado
```

### Endpoint

- `GET /api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true|false`
- Default: 15,000 mensajes/día (volumen hipotético de la HU-015).
- Tokens de referencia por mensaje: 46 ES / 38 EN (medidos con `o200k_base`).

---

## Fase 8 — Frontend HTML (dominio médico)

### `frontend/index.html`

1. Modo Archivo / Carpeta con drag-and-drop
2. Toggle `optimizar_tokens` (default `true`)
3. SSE streaming con barra de progreso (lectura, clustering, clasificacion, completo)
4. Tarjetas de métricas: tokens ES, tokens EN, costo, ahorro, fragmentación
5. Tabla de resultados: especialidad, accion, horario, mensaje representativo, id_paciente, mensajes en cluster, fragmentación, costo
6. Botones de export (JSON / Excel)

---

## Fase 9 — Cliente batch

### `backend/scripts/procesar_excel_async.py`

- `asyncio` + `httpx` (paralelo).
- Envía cada mensaje del Excel a `/api/analyze` con `optimizar_tokens=True`.
- Agrega tokens ES/EN y calcula fragmentación media y costos.

---

## Fase 10 — Documentación

| Archivo | Contenido |
|---|---|
| `README.md` (raíz) | Descripción, endpoints, instalación, schema |
| `backend/README.md` | Estructura, flujo, instalación, schema médico |
| `backend/docs/README.md` | Índice de documentación |
| `backend/docs/Instalacion.md` | Setup con venv (Python 3.12+, sin Ollama) |
| `backend/docs/API.md` | Referencia de los 6 endpoints |
| `backend/docs/Arquitectura.md` | Capas, modelos, pipeline médico |
| `backend/docs/Ejemplos.md` | Ejemplos curl/Python/batch |
| `documentacion/Plan_Implementacion_HU-015.md` | Este archivo |
| `documentacion/Resumen_HU-015.md` | Resumen de cambios |

---

## Orden de ejecución recomendado

| Fase | Descripción | Estado |
|---|---|---|
| 1 | Reutilización y adaptación del backend | ✅ Completado |
| 2 | Generador de datos de citas médicas | ✅ Completado |
| 3 | Entrenamiento de modelos médicos | ✅ Completado |
| 4 | Schemas Pydantic | ✅ Completado |
| 5 | Servicio de análisis médico | ✅ Completado |
| 6 | Endpoints | ✅ Completado |
| 7 | Análisis de impacto económico | ✅ Completado |
| 8 | Frontend HTML | ✅ Completado |
| 9 | Cliente batch | ✅ Completado |
| 10 | Documentación | ✅ Completado |

---

## Notas técnicas

- **scikit-learn**: 3 × `LinearSVC` sobre `HashingVectorizer(2^20)`. Inferencia <1ms por mensaje.
- **deep_translator**: Google Translate como backend (sin API key). Considerar rate limiting para volúmenes altos.
- **Tokenización**: `tiktoken` con `o200k_base`; `fragmentacion_ratio` = ES/EN.
- **Precio**: `$2.50 USD por millón de tokens`; default 15,000 mensajes/día.
- **Detección de columnas**: heurística (`mensaje_texto`, `especialidad_medica`, `id_paciente` con fallbacks).
- **Clustering**: `MiniBatchKMeans` por especialidad (k=5, máx 10), `ThreadPoolExecutor` paralelo.
- **CPU tuning**: `OMP_NUM_THREADS=12`, `MKL_NUM_THREADS=12`, `OPENBLAS_NUM_THREADS=12`.
- **Compatibilidad**: el flag `optimizar_tokens` acepta `optent_tokens` como alias.
- **SSE**: etapas `lectura`, `clustering`, `clasificacion`, `completo`.
