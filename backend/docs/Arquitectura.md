# Arquitectura — HU-015

## Visión general

El backend se construye sobre **FastAPI** y se estructura en capas separadas.
**No usa LLM local ni Ollama**: la extracción de intención se resuelve con
scikit-learn (LinearSVC) y keywords, y la tokenización con `tiktoken`.

```
┌──────────────────┐
│   Frontend        │  ← HTML estático servido por FastAPI
│  (index.html)     │
└───────┬───────────┘
        │ HTTP
        ▼
┌──────────────────┐
│  FastAPI (main)   │  ← Punto de entrada, CORS, rutas estáticas, banner
└────┬─────────────┘
     │ include_router
     ▼
┌──────────────────┐
│  Routers          │  ← APIRouter con endpoints
│  (analyze.py)     │
└────┬─────────────┘
     │ delega a
     ▼
┌────────────────────────┐
│  Servicios              │  ← Lógica de negocio
│  (analysis_service.py)  │
└────┬───────────────────┘
     │ usa
     ├─────▶ pandas + openpyxl (lectura Excel)
     ├─────▶ TfidfVectorizer + MiniBatchKMeans (clustering por especialidad)
     ├─────▶ HashingVectorizer + LinearSVC (accion, preferencia_horario, especialidad)
     ├─────▶ tiktoken (conteo de tokens ES/EN)
     └─────▶ deep_translator (ES→EN, solo con optimizar_tokens=True)
```

## Estructura de carpetas

```
backend/
├── app/
│   ├── main.py                    ← Punto de entrada, banner GEOXOR, app FastAPI
│   ├── core/
│   │   └── config.py              ← Constantes, precio, mensajes/día, banner
│   ├── models/
│   │   ├── schemas.py             ← Modelos Pydantic (request/response)
│   │   ├── vectorizer.joblib      ← HashingVectorizer entrenado (2^20)
│   │   ├── accion_model.joblib    ← LinearSVC: reprogramar/cancelar/consultar/otra
│   │   ├── horario_model.joblib   ← LinearSVC: manana/tarde/noche/sin_preferencia
│   │   └── especialidad_model.joblib ← LinearSVC: 13 especialidades
│   ├── routers/
│   │   └── analyze.py             ← Endpoints de análisis
│   └── services/
│       └── analysis_service.py    ← Lógica de negocio
├── data/
│   └── citas_medicas_solicitudes.xlsx ← Dataset de ejemplo (50,000 solicitudes)
├── docs/                          ← Documentación en español
├── scripts/
│   ├── generate_citas.py          ← Genera datos de prueba
│   ├── train_pipeline.py          ← Entrena modelos con pseudo-labels
│   └── procesar_excel_async.py    ← Cliente batch para el API
├── requirements.txt               ← Dependencias
└── README.md                      ← Documentación del backend
```

## Modelos Pydantic

### `CitaRequest`

```json
{
  "text": "string (mensaje del paciente en español)",
  "optimizar_tokens": false
}
```

- `text`: el mensaje de la solicitud a analizar.
- `optimizar_tokens`: si es `true`, el texto se traduce ES→EN antes de contar
  tokens y medir fragmentación. Acepta `optent_tokens` como alias
  (`Field(alias=..., populate_by_name=True)`).

### `AnalysisResponse`

```json
{
  "metrics": {
    "original_tokens": 28,
    "translated_tokens": 23,
    "tokens_saved_per_request": 0,
    "fragmentacion_ratio": 1.2174
  },
  "extracted_data": {
    "intent": {
      "accion": "reprogramar | cancelar | consultar | otra",
      "especialidad": "cardiologia | pediatria | ... (13 clases)",
      "preferencia_horario": "manana | tarde | noche | sin_preferencia"
    },
    "summary_es": "string (resumen en español)",
    "summary_en": "string (resumen en inglés)",
    "id_paciente": "string (opcional, del Excel)",
    "especialidad_medica": "string (columna del Excel)",
    "cluster_id": -1,
    "messages_in_cluster": 1,
    "texto_original": "string (mensaje tal como llegó)",
    "texto_limpio": "string (mensaje limpio)",
    "texto_en": "string (traducción ES→EN del limpio)"
  }
}
```

### `MessageDetail`

Una fila por **mensaje individual** (lo que se exporta a Excel):

```json
{
  "id_paciente": "string",
  "especialidad_medica": "string",
  "cluster_id": 0,
  "messages_in_cluster": 369,
  "accion": "reprogramar",
  "preferencia_horario": "manana",
  "texto_original": "string",
  "texto_limpio": "string",
  "texto_en": "string",
  "tokens_es": 32,
  "tokens_en": 24,
  "fragmentacion_ratio": 1.3333
}
```

### `BatchAnalysisResponse`

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
  "results": [AnalysisResponse, ...],
  "details": [MessageDetail, ...]
}
```

`timings` se agrega con el **máximo entre las especialidades** que corren en
paralelo (≈ tiempo de pared real de cada fase), para que ninguna etapa supere al
tiempo total medido en el cliente.

## Flujo de análisis

### Modo archivo (`/upload` o `/upload/stream`)

```
1. Cliente sube .xlsx
2. pandas + openpyxl leen y validan columnas (_validar_columnas)
   → columna de mensaje (mensaje_texto), especialidad (especialidad_medica),
     id de paciente (id_paciente) [todas opcionales con heurística]
3. Limpieza de mensajes (_limpiar_texto): strip, colapsa espacios, quita emojis
4. groupby('especialidad_medica') → grupos por especialidad
5. Por cada especialidad (ThreadPoolExecutor paralelo):
   ├─ TfidfVectorizer(max_features=500, ngram_range=(1,2)) + MiniBatchKMeans(k=5)
   ├─ Representante = mensaje más cercano al centroide
   ├─ Extracción de intención en lote (_predecir_intencion_lote): un solo
   │  transform + predict para todos los mensajes del grupo
   ├─ Conteo de tokens de todo el cluster (tiktoken o200k_base)
   └─ Se generan los details: una fila por mensaje (intención + tokens ES reales
      y tokens EN del representativo del clúster)
6. optimizar_tokens=True → deep_translator ES→EN para summary_en y tokens EN
   (solo se traducen los representativos; el resto del clúster usa esa traducción)
7. Se devuelve BatchAnalysisResponse con metrics, timings y details
```

### Modo carpeta (`/folder`)

Igual que archivo pero consolida todos los `.xlsx` de la carpeta en un único
DataFrame antes del agrupado por especialidad. Los archivos se procesan en
secuencia y sus `timings` se acumulan (suma).

### Modo individual (`/analyze`)

1. `_limpiar_texto()` limpia el texto (strip, espacios colapsados, sin emojis).
2. `_predecir_intencion()`: extrae `accion`, `especialidad` (keywords primero,
   modelo como respaldo) y `preferencia_horario`.
3. Si `optimizar_tokens=True`: traduce el texto limpio ES→EN, cuenta tokens y
   calcula `fragmentacion_ratio = tokens_es / tokens_en`.

## Frontend (gráficas)

El frontend (`frontend/index.html`) usa **Chart.js v4** (CDN) para mostrar:
tiempos por etapa, tokens ES vs EN por especialidad, acción y horario (doughnut),
mensajes por especialidad y fragmentación por grupo. Los `timings` y `details`
se envían desde el backend para alimentar las tarjetas y el export `.xlsx`.

## Detección de columnas

La función `_validar_columnas()` busca automáticamente las columnas necesarias:

1. **Mensaje**: `mensaje_texto`, `mensaje`, `texto`, `review`, `text`, `comment`
2. **Especialidad**: `especialidad_medica`, `especialidad`, `medico`, `departamento`
3. **Paciente**: `id_paciente`, `paciente_id`, `id`, `cedula`

Fallback: primera columna no vacía con texto.

## Precio de referencia

La tarifa (según HU-015) es **$2.50 USD por millón de tokens de entrada**, con
15,000 mensajes/día por defecto:

```
costo = (tokens / 1_000_000) * 2.50 USD
ahorro = costo_es - costo_en  (fragmentación evitada al traducir a EN)
```

## Seguridad

El endpoint `/api/analyze/folder` acepta una ruta de carpeta directamente. En
producción, se debería restringir a un directorio permitido (lista blanca) para
evitar acceso a archivos fuera del sandbox.
