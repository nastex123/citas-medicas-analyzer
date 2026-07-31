"""
Configuración central del backend HU-015.
Aquí se concentran las constantes que otros módulos necesitan,
para no tener valores "quemados" (hardcodeados) repartidos por el código.
"""
from pyfiglet import Figlet

# Nombre y metadatos de la API (se usan al crear la app FastAPI)
APP_TITLE = "Gestión de Citas Médicas Analyzer"
APP_DESCRIPTION = (
    "API que ingiere solicitudes de reprogramación/cancelación de citas médicas "
    "desde archivos Excel, cuenta tokens con tiktoken (o200k_base), mide la "
    "fragmentación del vocabulario médico ES vs EN y extrae la intención "
    "estructurada del mensaje (accion, especialidad, preferencia_horario)."
)
APP_VERSION = "1.0.0"

# Codificador de tokens usado por tiktoken (el mismo que usan modelos tipo GPT-4o)
TOKEN_ENCODING = "o200k_base"

# Precio de referencia usado para la proyección económica (USD por 1M tokens)
PRICE_PER_MILLION_TOKENS_USD = 2.50

# Volumen hipotético del centro de salud (mensajes/día) usado en cost-estimate
MENSAJES_POR_DIA_DEFAULT = 15000

# Host/puerto por defecto cuando se levanta con uvicorn
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000

# ─── GEOXOR Rainbow Banner ───
RAINBOW_COLORS = [
    "\033[91m",  # Red
    "\033[93m",  # Yellow
    "\033[92m",  # Green
    "\033[96m",  # Cyan
    "\033[94m",  # Blue
    "\033[95m",  # Magenta
]

BANNER_RESET = "\033[0m"

_fig = Figlet(font="big")
GEOXOR_BANNER_LINES = _fig.renderText("Geoxor").splitlines()
