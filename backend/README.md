# Gestión de Citas Médicas Analyzer — Backend (HU-015)

API en FastAPI que ingiere solicitudes de reprogramación/cancelación de citas
médicas desde archivos Excel: agrupa por especialidad médica mediante clustering
semántico (TF-IDF + MiniBatchKMeans), cuenta tokens ES vs EN con `tiktoken`
(o200k_base), mide la fragmentación del vocabulario médico y extrae la intención
estructurada (`accion`, `especialidad`, `preferencia_horario`) con scikit-learn
(LinearSVC).

## 1. Estructura de carpetas

```
backend/
├── app/                        # Backend (API)
│   ├── main.py                 # Punto de entrada: banner + app + routers
│   ├── core/
│   │   └── config.py           # Constantes / configuración
│   ├── models/
│   │   ├── __init__.py         # Paquete de modelos
│   │   ├── schemas.py          # Modelos Pydantic (request/response)
│   │   ├── vectorizer.joblib   # HashingVectorizer entrenado (2^20 features)
│   │   ├── accion_model.joblib        # LinearSVC para accion (4 clases)
│   │   ├── horario_model.joblib       # LinearSVC para preferencia_horario (4 clases)
│   │   └── especialidad_model.joblib  # LinearSVC para especialidad (13 clases)
│   ├── routers/
│   │   └── analyze.py          # Endpoints /api/analyze/*
│   └── services/
│       └── analysis_service.py # Lógica de negocio (tokens, clustering, intención)
├── scripts/                    # Herramientas externas
│   ├── generate_citas.py       # Genera datos de prueba (Excel de citas médicas)
│   ├── procesar_excel_async.py # Cliente que consume el backend en paralelo
│   └── train_pipeline.py       # Entrena modelos scikit-learn con pseudo-labels
├── data/
│   └── citas_medicas_solicitudes.xlsx
├── requirements.txt
└── README.md
```

## 2. Flujo de datos

```
scripts/generate_citas.py
        │  genera
        ▼
data/citas_medicas_solicitudes.xlsx
        │  lee
        ▼
scripts/procesar_excel_async.py  ──HTTP POST──►  app/main.py (FastAPI)
                                                         │ include_router
                                                         ▼
                                                  app/routers/analyze.py
                                                         │ llama a
                                                         ▼
                                              app/services/analysis_service.py
                                                         │ usa
                                                         ▼
                                              app/models/schemas.py (valida datos)
                                              app/models/*.joblib (modelos ML)
```

### Pipeline de análisis (por especialidad médica)

1. **Lectura Excel** — `pandas` + `openpyxl`, validación de columnas
2. **Agrupación** — `groupby('especialidad_medica')` → grupos por especialidad
3. **Clustering semántico** (por especialidad):
   - `TfidfVectorizer(max_features=500, ngram_range=(1,2))`
   - `MiniBatchKMeans(k=5, random_state=42)`
   - Selecciona representante: mensaje más cercano al centroide
4. **Extracción de intención** (sobre representantes):
   - `HashingVectorizer(n_features=2^20)` → `LinearSVC` para `accion`, `preferencia_horario`
   - Keywords + modelo → `especialidad`
5. **Tokens** — `tiktoken` (o200k_base) sobre todo el cluster, ratio de fragmentación ES/EN

## 3. Instalación

```powershell
cd backend
python -m venv venv
venv\Scripts\activate        # Windows PowerShell
pip install -r requirements.txt
```

> Usa Python 3.12+. Con 3.14 no hay wheels para `pydantic`/`tiktoken`.

## 4. Generar datos y modelos (solo la primera vez)

Con el venv activo, desde la carpeta `backend/`:

```powershell
python scripts/generate_citas.py        # Genera data/citas_medicas_solicitudes.xlsx
python scripts/train_pipeline.py        # Entrena y guarda los 3 modelos + vectorizer
```

### Regenerar el archivo `.xlsx` (`generate_citas.py`)

`generate_citas.py` genera solicitudes de citas médicas ficticias para pruebas:

```powershell
python scripts/generate_citas.py             # 10,000 solicitudes (default)
python scripts/generate_citas.py 20000       # volumen personalizado (ej. 20,000)
```

- **Salida**: `backend/data/citas_medicas_solicitudes.xlsx` (sobrescribe el archivo si ya existe).
- **Requiere**: `faker` y `pandas` (ya incluidos en `requirements.txt`).
- **Columnas**: `id_paciente`, `paciente`, `ciudad`, `especialidad_medica`, `fecha_solicitada`, `mensaje_texto`.
- El 10% de los mensajes se genera vacío (dato sucio intencional para probar tolerancia).

## 5. Levantar el backend

```powershell
cd backend
uvicorn app.main:app --reload
```

- API: `http://127.0.0.1:8000`
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Frontend: `http://127.0.0.1:8000/` (HTML estático)

## 6. Endpoints

### POST `/api/analyze` — Análisis individual

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Deseo reprogramar mi cita con el cardiólogo en la mañana", "optimizar_tokens": false}'
```

### POST `/api/analyze/upload` — Subir archivo (respuesta JSON)

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/upload \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=false"
```

### POST `/api/analyze/upload/stream` — Subir archivo (progreso en tiempo real, SSE)

```bash
curl -N -X POST http://127.0.0.1:8000/api/analyze/upload/stream \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=false"
```

Devuelve eventos SSE con `stage` (lectura, clustering, clasificacion, completo) y progreso porcentual.

### POST `/api/analyze/folder` — Escanear carpeta

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/folder \
  -F "folder_path=/ruta/a/carpeta" \
  -F "optimizar_tokens=false"
```

### GET `/api/analyze/cost-estimate` — Proyección económica

```bash
curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true"
```

Usa la tarifa de $2.50 USD por millón de tokens de entrada (15,000 msgs/día por defecto).

### GET `/api/analyze/export` — Exportar resultados

```bash
curl "http://127.0.0.1:8000/api/analyze/export?format=json"
```

## 7. Esquema de respuesta

```json
{
  "total": 60,
  "results": [
    {
      "metrics": {
        "original_tokens": 142190,
        "translated_tokens": 116800,
        "tokens_saved_per_request": 142175,
        "fragmentacion_ratio": 1.2174
      },
      "extracted_data": {
        "intent": {
          "accion": "reprogramar",
          "especialidad": "cardiologia",
          "preferencia_horario": "manana"
        },
        "summary_es": "Deseo solicitar la reprogramación de mi cita...",
        "summary_en": "I would like to request the rescheduling of...",
        "id_paciente": "84F1EFF0",
        "especialidad_medica": "Cardiología",
        "cluster_id": 0,
        "messages_in_cluster": 369
      }
    }
  ]
}
```

## 8. Datos de prueba

Para regenerar el archivo de datos, ver [Sección 4](#4-generar-datos-y-modelos-solo-la-primera-vez).

```bash
python scripts/generate_citas.py         # Genera data/citas_medicas_solicitudes.xlsx
python scripts/procesar_excel_async.py   # Cliente batch (requiere backend corriendo)
```

## 9. Notas técnicas

- **Sin LLM local**: todo el procesamiento usa scikit-learn y keywords.
- **Paralelismo**: clustering por especialidad usa `ThreadPoolExecutor`.
- **CPU tuning**: `OMP_NUM_THREADS=12`, `MKL_NUM_THREADS=12`, `OPENBLAS_NUM_THREADS=12`.
- **CORS**: abierto (`allow_origins=["*"]`).
- **Traducción**: `deep_translator` (Google Translate) solo cuando `optimizar_tokens=True`.
- **Compatibilidad**: el flag `optimizar_tokens` acepta `optent_tokens` como alias.
- **Streaming**: el endpoint `/upload/stream` usa SSE para progreso en tiempo real.
