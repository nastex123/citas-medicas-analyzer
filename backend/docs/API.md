# Referencia de la API — HU-015

Todos los endpoints están bajo el prefijo `/api`.

---

## `POST /api/analyze`

Analiza un mensaje individual de solicitud de cita médica.

### Cuerpo de la petición

```json
{
  "text": "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana.",
  "optimizar_tokens": true
}
```

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `text` | `string` | Sí | Mensaje del paciente en español |
| `optimizar_tokens` | `boolean` | No (default: `false`) | Si `true`, traduce ES→EN antes de contar tokens. Acepta `optent_tokens` como alias |

### Respuesta exitosa (200)

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
      "accion": "reprogramar",
      "especialidad": "cardiologia",
      "preferencia_horario": "manana"
    },
    "summary_es": "Deseo solicitar la reprogramación de mi cita médica...",
    "summary_en": "I would like to request the rescheduling of my medical appointment...",
    "id_paciente": "",
    "especialidad_medica": "cardiologia",
    "cluster_id": -1,
    "messages_in_cluster": 1,
    "texto_original": "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo...",
    "texto_limpio": "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo...",
    "texto_en": "I would like to request the rescheduling of my medical appointment..."
  }
}
```

`fragmentacion_ratio` = tokens ES / tokens EN. >1 significa que el español
fragmenta más (más tokens) que el inglés.

> `texto_limpio` es el mensaje tras la limpieza (strip, espacios colapsados y sin
> emojis). Cuando `optimizar_tokens=True`, `texto_en` es la traducción ES→EN del
> texto limpio y los tokens se cuentan sobre ese texto.

### Errores

| Código | Descripción |
|---|---|
| `400` | El texto está vacío |

---

## `POST /api/analyze/upload`

Sube un archivo `.xlsx` y analiza todas las solicitudes que contiene.

### Formato de la petición

Multipart form-data:

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `file` | archivo `.xlsx` | Sí | Archivo Excel con columnas tipo `id_paciente`, `mensaje_texto`, `especialidad_medica` |
| `optimizar_tokens` | boolean | No (default: `false`) | Activar traducción previa |

### Ejemplo con curl

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/upload \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=false"
```

### Respuesta exitosa (200)

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
        "translated_tokens": 142190,
        "tokens_saved_per_request": 142175,
        "fragmentacion_ratio": 1.0
      },
      "extracted_data": {
        "intent": { "accion": "reprogramar", "especialidad": "cardiologia", "preferencia_horario": "manana" },
        "summary_es": "Deseo solicitar la reprogramación de mi cita...",
        "summary_en": "Deseo solicitar la reprogramación de mi cita...",
        "id_paciente": "84F1EFF0",
        "especialidad_medica": "Cardiología",
        "cluster_id": 0,
        "messages_in_cluster": 369,
        "texto_original": "Deseo solicitar la reprogramación de mi cita médica...",
        "texto_limpio": "Deseo solicitar la reprogramación de mi cita médica...",
        "texto_en": "Deseo solicitar la reprogramación de mi cita médica..."
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
      "texto_en": "I would like to request the rescheduling of my medical appointment...",
      "tokens_es": 32,
      "tokens_en": 24,
      "fragmentacion_ratio": 1.3333
    }
  ]
}
```

- `results`: un elemento por **grupo representativo** (clúster) con métricas agregadas.
- `details`: una entrada por **mensaje individual** (misma estructura de columnas que
  el export). Con un archivo de 50,000 mensajes, `details` contiene ~45,000 filas
  (los mensajes vacíos se descartan).
- `timings`: tiempo por etapa (segundos), agregado como **máximo entre las
  especialidades** que se procesan en paralelo (≈ tiempo de pared real de la fase):
  `agrupacion`, `clustering`, `traduccion`, `tokenizacion`, `analisis`.

> El endpoint valida automáticamente que exista una columna de mensaje
> (`mensaje_texto` o similar); si no la encuentra responde `400`.

### Errores

| Código | Descripción |
|---|---|
| `400` | No se proporcionó archivo, el archivo no es `.xlsx`, o faltan columnas requeridas |

---

## `POST /api/analyze/upload/stream`

Igual que `/upload` pero con progreso en tiempo real mediante Server-Sent Events (SSE).

```bash
curl -N -X POST http://127.0.0.1:8000/api/analyze/upload/stream \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=false"
```

Eventos emitidos:

```
event: progress
data: {"stage": "lectura", "message": "Archivo leído: 50000 mensajes", "progress": 3, "total": 50000, "processed": 0}

event: progress
data: {"stage": "clustering", "message": "Agrupando por especialidad médica (12 especialidades)...", "progress": 8}

event: progress
data: {"stage": "clasificacion", "message": "Extrayendo intención de 60 representantes...", "progress": 90}

event: progress
data: {"stage": "detalle", "message": "Preparando detalle por mensaje (500/45024)...", "progress": 90.1, "details_batch": [ { ...MessageDetail... } ]}

event: progress
data: {"stage": "detalle", "message": "Preparando detalle por mensaje (45024/45024)...", "progress": 99.0, "details_batch": [...]}

event: progress
data: {"stage": "completo", "message": "Completado: 50000 mensajes → 60 grupos representativos", "progress": 100, "results": [...], "timings": {...}}
```

- Los `details` se envían en **lotes de 500 por evento** (`details_batch`) para no
  emitir una línea SSE gigante con todas las filas.
- El evento `completo` cierra el flujo con `results` (representativos) y `timings`.

---

## `POST /api/analyze/folder`

Escanea una carpeta y consolida todos los archivos `.xlsx` dentro.

### Formato de la petición

Multipart form-data:

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `folder_path` | `string` | Sí | Ruta absoluta o relativa a la carpeta |
| `optimizar_tokens` | boolean | No (default: `false`) | Activar traducción previa |

### Ejemplo con curl

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/folder \
  -F "folder_path=C:/Users/usuario/solicitudes" \
  -F "optimizar_tokens=true"
```

Respuesta con la misma estructura que `/api/analyze/upload` (`total`, `results`,
`timings` y `details`). Los archivos se procesan en secuencia y sus tiempos se acumulan.

### Errores

| Código | Descripción |
|---|---|
| `400` | La carpeta no existe o no contiene archivos `.xlsx` |

---

## `POST /api/analyze/export`

Genera un archivo **`.xlsx`** con **una fila por mensaje** (los mismos datos de
`details` devueltos por el análisis).

### Cuerpo de la petición

```json
{
  "details": [ { ...MessageDetail... } ]
}
```

Si `details` no se envía, acepta `results` (representativos) como alternativa.

### Ejemplo con Python

```python
import httpx

# 1) analizar la carpeta/archivo
r = httpx.post("http://127.0.0.1:8000/api/analyze/folder",
               data={"folder_path": "solicitudes", "optimizar_tokens": "true"})
details = r.json()["details"]

# 2) exportar todas las filas a .xlsx
xr = httpx.post("http://127.0.0.1:8000/api/analyze/export", json={"details": details})
open("citas_analysis.xlsx", "wb").write(xr.content)
```

### Columnas del Excel

| Columna | Descripción |
|---|---|
| `Especialidad médica` | Especialidad del mensaje |
| `ID paciente` | Identificador del paciente |
| `Cluster ID` | Clúster asignado |
| `Mensajes en clúster` | Tamaño del clúster |
| `Texto original` | Mensaje tal como llegó del Excel |
| `Texto limpio` | Mensaje tras la limpieza |
| `Texto en inglés` | Traducción del representativo del clúster (ES→EN) |
| `Acción` | `reprogramar` / `cancelar` / `confirmar` / `otro` |
| `Preferencia horario` | `manana` / `tarde` / `noche` / `sin_preferencia` |
| `Tokens ES` | Tokens del texto limpio (o200k_base) |
| `Tokens EN` | Tokens de la versión en inglés (representativo del clúster) |
| `Tokens ahorrados/request` | `max(0, tokens_es - tokens_en)` |
| `Ratio fragmentación ES/EN` | `tokens_es / tokens_en` |
| `Costo USD (EN)` | `(tokens_en / 1_000_000) * 2.50` |

> Con `optimizar_tokens=True` el texto en inglés es la traducción del mensaje
> **representativo** de cada clúster, que se aplica a todos sus miembros (evita
> traducir los 50,000 mensajes individuales).

### Errores

| Código | Descripción |
|---|---|
| `400` | No se enviaron `details` ni `results` |

## `GET /api/analyze/cost-estimate`

Estima el impacto económico para el volumen del centro de salud.

### Parámetros de consulta

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `messages_per_day` | `integer` | No (default: `15000`) | Mensajes procesados por día |
| `optimizar_tokens` | boolean | No (default: `false`) | Comparar modo optimizado vs directo |

### Ejemplo

```bash
curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true"
```

### Respuesta exitosa (200)

```json
{
  "messages_per_day": 15000,
  "estimated_tokens_es": 690000,
  "estimated_tokens_en": 570000,
  "costo_directo_usd": 1.7250,
  "costo_optimizado_usd": 1.4250,
  "ahorro_diario_usd": 0.3000,
  "ahorro_mensual_usd": 9.0000,
  "ahorro_anual_usd": 109.5000,
  "precio_por_millon_usd": 2.50,
  "optimizar_tokens": true
}
```

La tarifa de referencia es **$2.50 USD por millón de tokens de entrada**, tal como
indica la HU-015 para el volumen hipotético de 15,000 mensajes/día.

---

## `GET /`

Sirve el frontend HTML estático. En `http://127.0.0.1:8000` se muestra la interfaz
para subir archivos/carpetas, ver resultados y métricas.
