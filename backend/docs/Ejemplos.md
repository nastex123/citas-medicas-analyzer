# Ejemplos de uso — HU-015

## 1. Analizar un mensaje individual de cita médica

### Con `curl`

```bash
curl -X POST http://127.0.0.1:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"text": "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana.", "optimizar_tokens": true}'
```

### Con Python

```python
import httpx

response = httpx.post(
    "http://127.0.0.1:8000/api/analyze",
    json={
        "text": "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana.",
        "optimizar_tokens": True,
    },
)
result = response.json()
intent = result["extracted_data"]["intent"]
print(intent["accion"])                 # reprogramar
print(intent["especialidad"])           # cardiologia
print(intent["preferencia_horario"])    # manana
print(result["metrics"]["original_tokens"])     # tokens en español
print(result["metrics"]["translated_tokens"])   # tokens en inglés
print(result["metrics"]["fragmentacion_ratio"]) # ratio ES/EN
```

## 2. Subir un archivo Excel de solicitudes

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/upload \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=false"
```

## 3. Subir con progreso en tiempo real (SSE)

```bash
curl -N -X POST http://127.0.0.1:8000/api/analyze/upload/stream \
  -F "file=@citas_medicas_solicitudes.xlsx" \
  -F "optimizar_tokens=true"
```

Verás líneas `event: progress` con la etapa (lectura, clustering, clasificacion,
completo) y el porcentaje.

## 4. Procesar una carpeta de archivos Excel

```bash
curl -X POST http://127.0.0.1:8000/api/analyze/folder \
  -F "folder_path=C:/Users/usuario/solicitudes" \
  -F "optimizar_tokens=true"
```

## 5. Estimar costo para 15,000 mensajes/día

### Con traducción (optimizado)

```bash
curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true"
```

### Sin traducción (directo)

```bash
curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=false"
```

## 6. Exportar resultados en JSON

```bash
curl "http://127.0.0.1:8000/api/analyze/export?format=json" > resultados.json
```

## 7. Exportar resultados en Excel

```bash
curl "http://127.0.0.1:8000/api/analyze/export?format=excel" > resultados.xlsx
```

## 8. Generar datos y modelos (primera vez)

```bash
cd backend
python scripts/generate_citas.py        # data/citas_medicas_solicitudes.xlsx
python scripts/train_pipeline.py        # app/models/*.joblib
```

### Regenerar el `.xlsx` con otro volumen

```bash
python scripts/generate_citas.py             # 10,000 solicitudes (default)
python scripts/generate_citas.py 20000       # volumen personalizado (ej. 20,000)
```

El script escribe en `data/citas_medicas_solicitudes.xlsx` (sobrescribe si existe).
Columnas generadas: `id_paciente`, `paciente`, `ciudad`, `especialidad_medica`,
`fecha_solicitada`, `mensaje_texto`. Requiere `faker` y `pandas`.

## 9. Cliente batch

Con el backend corriendo en otra terminal:

```bash
cd backend
python scripts/procesar_excel_async.py
```

Envía todos los mensajes del Excel al endpoint `/api/analyze` en paralelo y
agrega las métricas de tokenización ES vs EN.

## 10. Abrir la documentación interactiva (Swagger)

Visita `http://127.0.0.1:8000/docs` en tu navegador. Swagger UI permite probar
todos los endpoints directamente desde la interfaz web.

## 11. Ejemplo de respuesta completa

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
        "intent": {
          "accion": "reprogramar",
          "especialidad": "cardiologia",
          "preferencia_horario": "manana"
        },
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
