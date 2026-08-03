# Pitch Técnico — Gestión de Citas Médicas Analyzer (HU-015)

**Versión para perfiles técnicos (desarrolladores, data engineers, arquitectos).**

API en FastAPI que ingiere solicitudes de reprogramación/cancelación de citas médicas desde archivos Excel, evalúa el costo de tokenización ES vs EN (`tiktoken` / `o200k_base`), mide la fragmentación del vocabulario médico y extrae la intención estructurada de cada mensaje con **ML clásico (sin LLM local ni Ollama)**.

---

## 1. Resumen ejecutivo

- **Problema:** un centro de salud procesa ~15,000 mensajes/día de pacientes ("quiero reprogramar con el cardiólogo en la mañana"). El vocabulario médico/formal en español ("reprogramación", "cardiología") se fragmenta en múltiples subpalabras en BPE, encareciendo el consumo de modelos de lenguaje.
- **Solución:** pipeline que carga masivamente desde `.xlsx` (archivo único o carpeta), agrupa mensajes similares por especialidad, extrae intención estructurada y mide el impacto económico de procesar en español vs. traducir a inglés primero.
- **Pregunta de negocio que responde:** ¿me conviene `optimizar_tokens=True` (traducir a EN) o procesar directo en ES?

```
optimizar_tokens=False:  ES → limpieza → clustering → intención (lote) → tokens ES
optimizar_tokens=True:   ES → deep_translator → EN → clustering → intención (lote) → tokens EN
```

---

## 2. Paso a paso de cómo funciona

### Paso 0 — Entorno

```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows PowerShell
pip install -r requirements.txt
```

> **Python 3.12+** (con 3.14 no hay wheels para `pydantic`/`tiktoken`).

### Paso 1 — Generar datos de prueba

```bash
python scripts/generate_citas.py 50000
```

- Genera `data/citas_medicas_solicitudes.xlsx` con `faker` (es_ES).
- 50,000 filas: `id_paciente`, `paciente`, `ciudad`, `especialidad_medica`, `fecha_solicitada`, `mensaje_texto`.
- **10% de mensajes vacíos** (dato sucio intencional para probar tolerancia).

### Paso 2 — Entrenar los modelos (solo la primera vez)

```bash
python scripts/train_pipeline.py
```

Lo que hace internamente:

1. **Pseudo-labels por keywords** — `_pseudo_label_accion/horario/especialidad` (`train_pipeline.py:159-168`).
2. **Aumentación balanceada** — `_aumentar_balanceado()` (`train_pipeline.py:171`) sintetiza ejemplos hasta `MIN_SAMPLES=250` por clase.
3. **Vectorización** — `HashingVectorizer(n_features=2**20, ngram_range=(1,2))` (`train_pipeline.py:249-255`). No guarda vocabulario en memoria → escalable y liviano.
4. **Entrenamiento** — 3 × `LinearSVC` (`train_pipeline.py:262-266`), uno por target:
   - `accion` (4 clases): reprogramar, cancelar, confirmar, otro
   - `preferencia_horario` (4): manana, tarde, noche, sin_preferencia
   - `especialidad` (13): 12 especialidades + sin_especificar
5. **Guardado** — 4 archivos en `app/models/`: `vectorizer.joblib`, `accion_model.joblib`, `horario_model.joblib`, `especialidad_model.joblib`.

> Resultado verificado: **accuracy 1.0000** en los 3 clasificadores.

> Los `.joblib` **no se suben al repo** (el de especialidad supera el límite de 100 MB de GitHub). Se regeneran con este script.

### Paso 3 — Levantar el backend

```bash
uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000` | Swagger: `/docs` | ReDoc: `/redoc` | Frontend: `/` (HTML estático servido por `StaticFiles`, `app/main.py:58-60`).

### Paso 4 — Análisis individual (`POST /api/analyze`)

Flujo en `analizar_cita()` (`analysis_service.py:538`):

1. `_limpiar_texto()` (`:136`) — strip, colapsa espacios, elimina emojis.
2. `_predecir_intencion()` (`:243`) — un `transform` + `predict` por clasificador.
3. Traducción ES→EN con caché (`:119`) — solo si `optimizar_tokens=True`.
4. Conteo de tokens con `tiktoken` (`o200k_base`) ES vs EN (`:548-549`).

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Deseo reprogramar mi cita con el cardiólogo en la mañana", "optimizar_tokens": false}'
```

### Paso 5 — Análisis batch (`POST /api/analyze/upload`)

Flujo en `procesar_archivo_excel()` (`:493`):

1. `pd.read_excel(io.BytesIO(contents))` + `_validar_columnas()` (`:206`) — detección heurística de columnas con fallbacks (`mensaje_texto`, `especialidad_medica`, `id_paciente`).
2. `_procesar_por_especialidad()` (`:446`) — `groupby(especialidad)` y **procesamiento paralelo** de cada grupo con `ThreadPoolExecutor(max_workers=len(grupos))` (`:474`).
3. `_procesar_especialidad_grupo()` (`:336`):
   - **Clustering semántico** `_cluster_mensajes()` (`:300`): `TfidfVectorizer(max_features=500, ngram_range=(1,2))` + `MiniBatchKMeans(k=5, batch_size=2048)`. Representante = mensaje más cercano al centroide. Reduce **50k solicitudes → ~60 grupos representativos** (mín. 50 mensajes para clusterear, máx. 10 clusters/especialidad).
   - **Traducción solo de representantes** (`:355-358`) con pool de 6 workers + caché en disco (`translation_cache.json`, gitignored). El resto del clúster reutiliza esa traducción.
   - **Intención en lote** `_predecir_intencion_lote()` (`:262`) — **un solo `transform` + `predict`** para todos los mensajes del grupo.
   - **Métricas por mensaje** (`:415-438`): tokens ES/EN, `fragmentacion_ratio = tokens_es / tokens_en`.
4. **Timings por etapa** (`agrupacion`, `clustering`, `traduccion`, `tokenizacion`, `analisis`) agregados con `max` entre especialidades ≈ tiempo de pared real (`:484`).

### Paso 6 — Streaming SSE (`POST /api/analyze/upload/stream`)

`procesar_archivo_excel_stream()` (`:577`):

- Emite eventos con `stage` y `progress`: `lectura` → `clustering` → `clasificacion` → `detalle` (lotes de 500 en `details_batch`) → `completo`.
- El trabajo pesado se descarga del event loop con `asyncio.get_event_loop().run_in_executor()` (`:644`).
- Headers SSE con `Cache-Control: no-cache` y `X-Accel-Buffering: no` (`analyze.py:83-87`).

### Paso 7 — Proyección económica (`GET /api/analyze/cost-estimate`)

`cost_estimate()` (`analyze.py:190`):

```
costo_directo     = (tokens_es * msgs/día / 1_000_000) * $2.50
costo_optimizado  = (tokens_en * msgs/día / 1_000_000) * $2.50
ahorro_diario     = costo_directo - costo_optimizado
```

- Default: **15,000 msgs/día** (`config.py:25`), **$2.50 USD por millón de tokens** (`config.py:22`).
- Tokens de referencia por mensaje: 46 ES / 38 EN (medidos con `o200k_base`).

### Paso 8 — Exportación (`POST /api/analyze/export`)

`_generar_excel_export()` (`analyze.py:114`) — vuelca los `details` a un `.xlsx` con **una fila por mensaje** y 14 columnas (especialidad, ID, cluster, texto ES/limpio/EN, acción, horario, tokens ES/EN, ahorro, ratio, costo).

---

## 3. Comandos paso a paso (hoja de ruta rápida)

```bash
# 1. Setup
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt

# 2. Datos y modelos (primera vez)
python scripts/generate_citas.py 50000
python scripts/train_pipeline.py

# 3. Servidor
uvicorn app.main:app --reload

# 4. Probar endpoints
curl -X POST http://127.0.0.1:8000/api/analyze -H "Content-Type: application/json" \
  -d '{"text": "Deseo reprogramar mi cita con el cardiólogo", "optimizar_tokens": false}'

curl -N -X POST http://127.0.0.1:8000/api/analyze/upload/stream \
  -F "file=@data/citas_medicas_solicitudes.xlsx" -F "optimizar_tokens=true"

curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true"

# 5. Cliente batch asíncrono (requiere backend corriendo)
python scripts/procesar_excel_async.py
```

---

## 4. Librerías y su rol

| Librería | Versión | Rol |
|---|---|---|
| `fastapi` | 0.115.6 | Framework web + validación Pydantic |
| `uvicorn[standard]` | 0.34.0 | Servidor ASGI |
| `pydantic` | 2.10.4 | Schemas request/response (`app/models/schemas.py`) |
| `tiktoken` | 0.8.0 | Tokenización `o200k_base` (mismo encoder de GPT-4o) |
| `pandas` / `openpyxl` | 2.2.3 / 3.1.5 | Lectura/escritura de Excel |
| `scikit-learn` | 1.9.0 | `HashingVectorizer`, `TfidfVectorizer`, `MiniBatchKMeans`, `LinearSVC` |
| `joblib` | 1.5.3 | Persistencia de modelos `.joblib` |
| `deep-translator` | 1.11.4 | Traducción ES→EN (backend Google Translate, sin API key) |
| `httpx` | 0.28.1 | Cliente async para el batch (`procesar_excel_async.py`) |
| `tqdm` | 4.67.1 | Barra de progreso en el cliente batch |
| `python-multipart` | 0.0.18 | Parseo de `multipart/form-data` (uploads) |
| `pyfiglet` | 1.0.2 | Banner GEOXOR de arranque (`app/core/config.py:43`) |
| `faker` | 37.0.0 | Generador de datos de prueba (es_ES) |

---

## 5. Optimización máxima del hardware

### 5.1 Usar todos los núcleos CPU (BLAS)

Se fijan las variables de hilos de las librerías numéricas al inicio, **antes de importar** numpy/sklearn:

```python
# analysis_service.py:21-23  y  train_pipeline.py:20-22
os.environ["OMP_NUM_THREADS"] = "12"
os.environ["MKL_NUM_THREADS"] = "12"
os.environ["OPENBLAS_NUM_THREADS"] = "12"
```

**Cómo ajustarlo a tu máquina:** reemplaza el 12 por tu número de núcleos físicos. En Linux se detecta con `nproc`; en Python, con `os.cpu_count()`. Ejemplo dinámico:

```python
import os
os.environ["OMP_NUM_THREADS"] = str(os.cpu_count())
os.environ["MKL_NUM_THREADS"] = str(os.cpu_count())
os.environ["OPENBLAS_NUM_THREADS"] = str(os.cpu_count())
```

> Ojo: en CPU *hyper-threaded*, a veces rinde más usar solo los núcleos físicos para evitar contención de caché.

### 5.2 Paralelismo a nivel de especialidad

Cada especialidad médica se procesa como una tarea independiente en un pool de hilos:

```python
# analysis_service.py:474
with ThreadPoolExecutor(max_workers=max(1, len(items))) as pool:
    futures = [pool.submit(_procesar_especialidad_grupo, ...) for ...]
```

Como los grupos son independientes, `len(items)` hilos satura todos los núcleos. La agregación de `timings` usa `max` entre grupos (proxy del tiempo de pared real).

### 5.3 Pool de traducción paralela

```python
# analysis_service.py:78
_translator_pool = ThreadPoolExecutor(max_workers=6)
```

Las traducciones de los representantes se disparan en paralelo con `pool.map()` (`:159`), más una **caché en disco** (`translation_cache.json`) que evita retraducir textos repetidos entre ejecuciones.

### 5.4 Memoria controlada para 50k mensajes

- `MiniBatchKMeans(batch_size=2048)` — procesa por lotes, no en memoria completa.
- `TfidfVectorizer(max_features=500)` — solo 500 features por especialidad.
- `HashingVectorizer(2**20)` — sin vocabulario almacenado; vectoriza en streaming.
- La vectorización del clustering se hace **por especialidad**, no sobre el dataset completo.

### 5.5 Inferencia en lote (amortiza overhead)

`_predecir_intencion_lote()` (`:262`) hace **un solo `transform` + `predict`** para todos los mensajes del grupo, en vez de una llamada por mensaje. El path individual (`:243`) también comparte el mismo `X` para los 3 clasificadores.

### 5.6 Cliente batch con concurrencia alta

```python
# procesar_excel_async.py:27-58
MAX_CONCURRENT_REQUESTS = 50
semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
limits = httpx.Limits(max_keepalive_connections=50, max_connections=50)
async with httpx.AsyncClient(limits=limits) as client:
    results = await tqdm.gather(*tasks, desc="Procesando")
```

50 conexiones HTTP simultáneas con keep-alive, limitadas por semáforo para no saturar el servidor.

### 5.7 Escalado del servidor

Para carga alta, levantar **un worker por núcleo físico**:

```bash
uvicorn app.main:app --workers N
```

> Recomendado: `N = núcleos físicos` (menos que los lógicos). En desarrollo seguir con `--reload` (que fuerza 1 worker).

### 5.8 Resumen de ajustes según hardware

| Recurso | Variable / Parámetro | Dónde |
|---|---|---|
| Núcleos BLAS | `OMP/MKL/OPENBLAS_NUM_THREADS` | `analysis_service.py:21-23` |
| Hilos por especialidad | `max_workers=len(grupos)` | `analysis_service.py:474` |
| Hilos de traducción | `_translator_pool = 6` | `analysis_service.py:78` |
| Batch de clustering | `batch_size=2048` | `analysis_service.py:315` |
| Conexiones cliente | `MAX_CONCURRENT_REQUESTS=50` | `procesar_excel_async.py:27` |
| Workers del servidor | `--workers N` | comando uvicorn |

---

## 6. Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/analyze` | Análisis individual (JSON + `optimizar_tokens`) |
| `POST` | `/api/analyze/upload` | Subir `.xlsx` → respuesta JSON batch |
| `POST` | `/api/analyze/upload/stream` | Upload con progreso en tiempo real (SSE, lotes de 500) |
| `POST` | `/api/analyze/folder` | Escaneo de carpeta con múltiples `.xlsx` |
| `POST` | `/api/analyze/export` | Genera `.xlsx` con una fila por mensaje |
| `GET` | `/api/analyze/cost-estimate` | Proyección económica (default 15,000 msgs/día) |

> Los endpoints batch (`upload`, `upload/stream`, `folder`) aceptan además el
> flag `clusterizar` (default `true`). Con `clusterizar=false` el clustering se
> desactiva y **cada mensaje se analiza individualmente** (texto limpio,
> traducción y métricas por mensaje, `results` = una fila por mensaje).

---

## 7. Resultados / verificación

| Prueba | Resultado |
|---|---|
| `POST /api/analyze` (ejemplo HU-015) | `{"accion": "reprogramar", "especialidad": "cardiologia", "preferencia_horario": "manana"}` |
| Tokens ES vs EN (`optimizar_tokens=true`) | 28 ES / 23 EN → `fragmentacion_ratio` 1.2174 |
| `POST /api/analyze/upload` (50k solicitudes) | HTTP 200, `total` = 60 grupos, `details` ≈ 45,000 filas |
| `POST /api/analyze/export` | `.xlsx` con 45,000 filas y 14 columnas |
| `GET /api/analyze/cost-estimate` | Ahorro diario/mensual/anual |
| Entrenamiento (3 clasificadores) | Accuracy 1.0000 |
| Inferencia | <1 ms por mensaje (LinearSVC sobre `HashingVectorizer`) |

---

## 8. Notas técnicas

- **Sin LLM local**: todo el procesamiento usa scikit-learn + keywords.
- **Traducción**: `deep_translator` (Google Translate, sin API key) solo cuando `optimizar_tokens=True` y únicamente sobre los representantes de clúster.
- **Compatibilidad**: el flag `optimizar_tokens` acepta `optent_tokens` como alias.
- **Streaming**: los `details` se envían en lotes de 500 por evento SSE.
- **Frontend**: `frontend/index.html` con **Chart.js v4** (CDN) para gráficas de tiempos, tokens, acción, horario, especialidad y fragmentación; drag-and-drop, toggle `optimizar_tokens` y export JSON/Excel.
- **CORS**: abierto (`allow_origins=["*"]`).
