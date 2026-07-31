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
    "messages_in_cluster": 1
  }
}
```

`fragmentacion_ratio` = tokens ES / tokens EN. >1 significa que el español
fragmenta más (más tokens) que el inglés.

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
        "messages_in_cluster": 369
      }
    }
  ]
}
```

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
data: {"stage": "lectura", "message": "Archivo leído: 10000 mensajes", "progress": 3, "total": 10000, "processed": 0}

event: progress
data: {"stage": "clustering", "message": "Agrupando por especialidad médica (12 especialidades)...", "progress": 8}

event: progress
data: {"stage": "completo", "message": "Completado: 10000 mensajes → 60 grupos representativos", "progress": 100, "results": [...], "timings": {...}}
```

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

### Errores

| Código | Descripción |
|---|---|
| `400` | La carpeta no existe o no contiene archivos `.xlsx` |

---

## `GET /api/analyze/export`

Exporta resultados en formato JSON o Excel.

### Parámetros de consulta

| Parámetro | Tipo | Requerido | Descripción |
|---|---|---|---|
| `format` | `string` | Sí | `json` o `excel` |
| `optimizar_tokens` | boolean | No | Filtro por modo de procesamiento |

### Ejemplo

```bash
curl "http://127.0.0.1:8000/api/analyze/export?format=json"
```

---

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
