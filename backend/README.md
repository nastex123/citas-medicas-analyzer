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
2. **Limpieza** — `_limpiar_texto`: strip, colapsa espacios, quita emojis
3. **Agrupación** — `groupby('especialidad_medica')` → grupos por especialidad
4. **Clustering semántico** (por especialidad):
   - `TfidfVectorizer(max_features=500, ngram_range=(1,2))`
   - `MiniBatchKMeans(k=5, random_state=42)`
   - Selecciona representante: mensaje más cercano al centroide
5. **Extracción de intención** — en lote (`_predecir_intencion_lote`): un solo
   `transform` + `predict` para todos los mensajes del grupo
6. **Detalle por mensaje** — una fila por mensaje con intención, tokens ES
   (tiktoken o200k_base) y tokens EN del representativo de su clúster
7. **Tokens** — ratio de fragmentación ES/EN por grupo representativo

Los tiempos por etapa (`agrupacion`, `clustering`, `traduccion`, `tokenizacion`,
`analisis`) se agregan con el **máximo entre especialidades** (se procesan en
paralelo), como proxy del tiempo de pared real de cada fase.

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
python scripts/generate_citas.py 50000       # volumen del dataset de prueba actual
```

- **Salida**: `backend/data/citas_medicas_solicitudes.xlsx` (sobrescribe el archivo si ya existe).
- **Requiere**: `faker` y `pandas` (ya incluidos en `requirements.txt`).
- **Columnas**: `id_paciente`, `paciente`, `ciudad`, `especialidad_medica`, `fecha_solicitada`, `mensaje_texto`.
- El 10% de los mensajes se genera vacío (dato sucio intencional para probar tolerancia).
- El dataset de prueba actual tiene **50,000 filas** (≈45,000 mensajes no vacíos).

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

El campo `clusterizar` (default `true`) controla el método de análisis: con
`true` se agrupa por similitud (clustering) y se analizan los representativos;
con `false` se analiza **cada mensaje individualmente** (texto limpio +
traducción + intención por mensaje).

### POST `/api/analyze/upload/stream` — Subir archivo (progreso en tiempo real, SSE)

```bash
curl -N -X POST http://127.0.0.1:8000/api/analyze/upload/stream \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=false"
```

Acepta también `clusterizar`. Devuelve eventos SSE con `stage` (lectura,
clustering, clasificacion, detalle, completo) y progreso porcentual. Los
`details` (una fila por mensaje) se envían en lotes de 500 por evento
(`details_batch`).

### POST `/api/analyze/folder` — Escanear carpeta

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/folder \
  -F "folder_path=/ruta/a/carpeta" \
  -F "optimizar_tokens=false"
```

Acepta también `clusterizar`. Devuelve `total`, `results` (representativos),
`timings` y `details` (una fila por mensaje).

### GET `/api/analyze/cost-estimate` — Proyección económica

```bash
curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true"
```

Usa la tarifa de $2.50 USD por millón de tokens de entrada (15,000 msgs/día por defecto).

### POST `/api/analyze/export` — Exportar Excel (.xlsx)

Genera un `.xlsx` con **una fila por mensaje** (los `details` del análisis). Con
50,000 mensajes se exportan ~45,000 filas no vacías.

```python
import httpx
r = httpx.post("http://127.0.0.1:8000/api/analyze/folder",
               data={"folder_path": "/ruta/a/carpeta", "optimizar_tokens": "true"})
xr = httpx.post("http://127.0.0.1:8000/api/analyze/export", json={"details": r.json()["details"]})
open("citas_analysis.xlsx", "wb").write(xr.content)
```

Columnas: `Especialidad médica`, `ID paciente`, `Cluster ID`, `Mensajes en clúster`,
`Texto original`, `Texto limpio`, `Texto en inglés`, `Acción`, `Preferencia horario`,
`Tokens ES`, `Tokens EN`, `Tokens ahorrados/request`, `Ratio fragmentación ES/EN`,
`Costo USD (EN)`.

## 7. Esquema de respuesta

```json
{
  "total": 60,
  "timings": {
    "agrupacion": 0.008,
    "clustering": 2.791,
    "traduccion": 0.0,
    "tokenizacion": 3.648,
    "analisis": 0.467
  },
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
        "messages_in_cluster": 369,
        "texto_original": "Deseo solicitar la reprogramación de mi cita médica...",
        "texto_limpio": "Deseo solicitar la reprogramación de mi cita médica...",
        "texto_en": "I would like to request the rescheduling of my medical appointment..."
      }
    }
  ],
  "details": [
    {
      "id_paciente": "84F1EFF0",
      "especialidad_medica": "Cardiología",
      "cluster_id": 0,
      "messages_in_cluster": 369,
      "accion": "reprogramar",
      "preferencia_horario": "manana",
      "texto_original": "Deseo solicitar la reprogramación de mi cita médica...",
      "texto_limpio": "Deseo solicitar la reprogramación de mi cita médica...",
      "texto_en": "I would like to request the rescheduling of...",
      "tokens_es": 32,
      "tokens_en": 24,
      "fragmentacion_ratio": 1.3333
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
- **Paralelismo**: clustering por especialidad usa `ThreadPoolExecutor`; los
  `timings` por etapa se agregan con `max` entre grupos (≈ tiempo de pared real).
- **CPU tuning**: `OMP_NUM_THREADS=12`, `MKL_NUM_THREADS=12`, `OPENBLAS_NUM_THREADS=12`.
- **CORS**: abierto (`allow_origins=["*"]`).
- **Traducción**: `deep_translator` (Google Translate) solo cuando `optimizar_tokens=True`
  y únicamente para los mensajes representativos (el resto del clúster reutiliza esa
  traducción). Hay caché en disco (`translation_cache.json`, gitignored).
- **Compatibilidad**: el flag `optimizar_tokens` acepta `optent_tokens` como alias.
- **Streaming**: el endpoint `/upload/stream` usa SSE; los `details` se envían en lotes
  de 500 por evento.
- **Frontend**: el `index.html` usa **Chart.js v4** (CDN) para las gráficas de tiempos,
  tokens, acción, horario, especialidad y fragmentación.
