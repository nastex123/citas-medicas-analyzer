# Guía de Instalación — HU-015

## Prerrequisitos

| Requisito | Versión mínima |
|---|---|
| Python | 3.12+ |
| Windows | 10+ |

> **Importante:** el backend NO requiere Ollama ni ningún LLM local. Todo el
> procesamiento (extracción de intención y tokenización) usa scikit-learn y tiktoken.

## Paso 1: Ubicar el proyecto

```powershell
cd C:\Users\Usuario\Documents\riwi\IA for Devs\HU-015
```

## Paso 2: Crear el entorno virtual e instalar dependencias

### 2.1 Crear el venv

Desde la carpeta `backend/`:

```powershell
cd backend
python -m venv venv
```

> **Importante:** usa Python 3.12+. Con Python 3.14 los paquetes `pydantic` y `tiktoken`
> (versiones fijadas en `requirements.txt`) fallan al compilar, porque no existen wheels
> para esa versión.

### 2.2 Activar el venv

**PowerShell (Windows):**

```powershell
venv\Scripts\activate
```

**CMD (Windows):**

```bat
venv\Scripts\activate.bat
```

**Linux/Mac:**

```bash
source venv/bin/activate
```

Notarás el prefijo `(venv)` en la terminal.

### 2.3 Instalar dependencias

```powershell
pip install -r requirements.txt
```

Esto instala:
- `fastapi` — framework web
- `uvicorn` — servidor ASGI
- `tiktoken` — contador de tokens (o200k_base)
- `pandas` + `openpyxl` — lectura de Excel
- `deep-translator` — traducción ES→EN (opcional, con `optimizar_tokens=True`)
- `scikit-learn` + `joblib` — clasificadores LinearSVC
- `python-multipart` — soporte para upload de archivos
- `pyfiglet` — banner de arranque
- `faker`, `httpx`, `tqdm` — herramientas de prueba

## Paso 3: Generar datos y modelos (solo la primera vez)

Con el venv activado, desde la carpeta `backend/`:

```powershell
python scripts/generate_citas.py
python scripts/train_pipeline.py
```

1. `generate_citas.py` genera `data/citas_medicas_solicitudes.xlsx` (10,000 solicitudes de pacientes).
2. `train_pipeline.py` entrena y guarda los 3 clasificadores + vectorizer en `app/models/`.

### Regenerar el archivo `.xlsx` (`generate_citas.py`)

```powershell
python scripts/generate_citas.py             # 10,000 solicitudes (default)
python scripts/generate_citas.py 20000       # volumen personalizado (ej. 20,000)
```

- **Salida**: `backend/data/citas_medicas_solicitudes.xlsx` (sobrescribe el archivo si ya existe).
- **Requiere**: `faker` y `pandas` (ya incluidos en `requirements.txt`).
- **Columnas**: `id_paciente`, `paciente`, `ciudad`, `especialidad_medica`, `fecha_solicitada`, `mensaje_texto`.
- El 10% de los mensajes se genera vacío (dato sucio intencional para probar tolerancia).

## Paso 4: Levantar el backend

Con el venv activado, desde la carpeta `backend/`:

```powershell
python -m uvicorn app.main:app --reload
```

La API estará disponible en:

- **Frontend**: `http://127.0.0.1:8000`
- **Documentación interactiva (Swagger)**: `http://127.0.0.1:8000/docs`
- **Documentación alternativa (ReDoc)**: `http://127.0.0.1:8000/redoc`

## Paso 5: Probar el backend

Abre `http://127.0.0.1:8000/docs` en el navegador y ejecuta un mensaje de ejemplo
en el endpoint `POST /api/analyze`:

```json
{
  "text": "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana.",
  "optimizar_tokens": true
}
```

Respuesta esperada (intención extraída):

```json
{
  "accion": "reprogramar",
  "especialidad": "cardiologia",
  "preferencia_horario": "manana"
}
```

## Pasos opcionales

### Enviar datos masivos al backend

Con el backend corriendo en otra terminal:

```powershell
python scripts/procesar_excel_async.py
```

Esto envía todos los mensajes del Excel al endpoint `/api/analyze` en paralelo
e imprime métricas agregadas de tokenización (ES vs EN) y fragmentación media.

### Proyección económica

```powershell
curl "http://127.0.0.1:8000/api/analyze/cost-estimate?messages_per_day=15000&optimizar_tokens=true"
```

Calcula el costo diario/mensual/anual a $2.50 USD por millón de tokens de entrada.
