Caso 2:

## 🚀 Historia de Usuario (HU)

**ID:** HU-015

**Título:** Ingesta flexible y evaluación de costo/tokenización para gestión de citas médicas vía Excel

**Epic:** Infraestructura de Procesamiento de LLM & Automatización de Citas

**Estimación:** **3 Story Points**

---

### **Como:**

Desarrollador de Software / Diseñador de Prompts en el sector salud

### **Quiero:**

Un módulo de ingesta que procese mensajes de reprogramación de citas médicas desde archivos Excel (individuales o por carpeta local) y permita evaluar de forma opcional la tokenización en español vs. inglés vía `/api/analyze`

### **Para:**

Medir el impacto financiero del vocabulario médico/formal en la tokenización y decidir la arquitectura de procesamiento más rentable según la carga del centro de salud.

---

## 📄 Contexto de Negocio & Escenario

Un centro de salud procesa miles de solicitudes de pacientes para confirmar o cancelar turnos médicos. Los textos contienen terminología formal y nombres de especialidades ("reprogramación", "cardiólogo") que suelen fragmentarse en múltiples subpalabras en BPE. La pipeline debe permitir cargas masivas desde hojas de cálculo y la activación opcional del arbitraje de tokens.

* **Ejemplo de fila/mensaje a procesar (Español):**
> *"Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana."*



---

## ✅ Criterios de Aceptación (Definition of Done)

### **Criterio 1: Carga Flexible de Hojas de Cálculo (Excel)**

* [ ] El sistema debe permitir elegir la fuente de entrada de los mensajes:
* **Modo A (Archivo Único):** Cargar un archivo `.xlsx` específico con solicitudes de pacientes.
* **Modo B (Carpeta Local):** Escanear y consolidar automáticamente todos los archivos `.xlsx` dentro de una carpeta configurada.


* [ ] Se debe validar que las columnas del Excel (ej. `paciente_id`, `mensaje_texto`) sean parseadas correctamente antes del análisis.

### **Criterio 2: Evaluación Opcional de Tokenización y Términos Médicos**

* [ ] El flujo debe contar con un parámetro configurable (`optimizar_tokens: True/False`).
* [ ] **Si la opción está activa (`True`):** El texto se envía a `/api/analyze` para evaluar el costo antes de traducirlo e ingresarlo al LLM principal.


* [ ] **Si la opción está desactivada (`False`):** El mensaje en español se procesa directamente en el LLM principal.
* [ ] Se debe registrar la tasa de fragmentación de términos médicos formales en español vs. su equivalente en inglés mediante el codificador `o200k_base`.



### **Criterio 3: Proyección Económica y Salida Estructurada**

* [ ] Calcular la diferencia de costo diario y mensual para un volumen hipotético de **15,000 mensajes/día**, utilizando la tarifa de referencia de **$2.50 USD por millón de tokens de entrada**.
* [ ] El modelo debe exportar las solicitudes procesadas a un esquema estructurado (JSON o Excel) indicando la intención extraída (ejemplo: `{"accion": "reprogramar", "especialidad": "cardiologia", "preferencia_horario": "manana"}`).

---

## 🏷️ Notas Técnicas

* **Librerías de Ingesta:** `pandas` / `openpyxl` / `glob`.
* **Motor de Tokenización & Traducción:** `tiktoken` (`o200k_base`), `deep_translator`, FastAPI.









generate_citas.py

import random
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker


def generar_citas_excel(
    nombre_archivo="citas_medicas_solicitudes.xlsx", num_filas=10000
):
    print(f"Generando {num_filas} solicitudes de citas médicas en español...")

    # Inicializar Faker en español
    fake = Faker("es_ES")

    # Especialidades médicas habituales en el centro de salud
    especialidades = [
        "Cardiología",
        "Dermatología",
        "Ginecología y Obstetricia",
        "Neurología",
        "Oftalmología",
        "Ortopedia y Traumatología",
        "Pediatría",
        "Otorrinolaringología",
        "Gastroenterología",
        "Urología",
        "Medicina General",
        "Endocrinología",
    ]

    # Plantillas con vocabulario formal/médico propio del caso de uso
    plantillas_mensajes = [
        "Deseo solicitar la reprogramación de mi cita médica con el cardiólogo para la próxima semana en el horario de la mañana.",
        "Solicito modificar la fecha de mi consulta médica asignada debido a inconvenientes laborales imprevistos.",
        "Requiero cancelar la cita programada e identificar la disponibilidad de agenda para el turno de la tarde.",
        "Agradezco de antemano la gestión para reagendar mi control periódico para el próximo mes.",
        "Necesito cambiar el horario de mi turno médico, de preferencia en las primeras horas del día.",
        "Favor confirmar si es posible postergar mi atención especializada para el día viernes por la mañana.",
        "Por motivos personales me resulta imposible asistir a la cita asignada. Deseo postergarla para la siguiente semana.",
        "Quisiera saber si hay posibilidad de adelantar mi turno médico por motivos de urgencia no vital.",
    ]

    data = []

    # Generación eficiente de datos
    for _ in range(num_filas):
        id_paciente = fake.uuid4()[:8].upper()
        paciente = fake.name()
        ciudad = fake.city()
        especialidad = random.choice(especialidades)
        
        # Fecha futura deseada para la reasignación
        fecha_deseada = (datetime.now() + timedelta(days=random.randint(2, 30))).strftime("%Y-%m-%d")

        # Probabilidad del 10% de que el mensaje venga vacío o con datos incompletos
        if random.random() < 0.10:
            mensaje_texto = ""
        else:
            # Combina una plantilla formal con contexto adicional dinámico
            mensaje_texto = (
                f"{random.choice(plantillas_mensajes)} {fake.sentence(nb_words=8)}"
            )

        data.append(
            {
                "id_paciente": id_paciente,
                "paciente": paciente,
                "ciudad": ciudad,
                "especialidad_medica": especialidad,
                "fecha_solicitada": fecha_deseada,
                "mensaje_texto": mensaje_texto,
            }
        )

    print("Creando DataFrame de Pandas...")
    df = pd.DataFrame(data)

    print(f"Guardando archivo Excel: {nombre_archivo}...")
    # Exportar a Excel (requiere openpyxl)
    df.to_excel(nombre_archivo, index=False, engine="openpyxl")

    print(f"¡Proceso completado con éxito! Archivo creado: {nombre_archivo}")


if __name__ == "__main__":
    # Permite ejecutarlo directo o importar la función
    generar_citas_excel()