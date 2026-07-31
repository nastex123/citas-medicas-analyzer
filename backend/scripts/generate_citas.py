"""
Script utilitario: genera un Excel con solicitudes de citas médicas ficticias
(datos de prueba para HU-015). No forma parte del backend en sí; es una
herramienta de apoyo para probar el endpoint /api/analyze de forma masiva.

Uso (desde la carpeta backend/):
    python scripts/generate_citas.py            # 10.000 filas por defecto
    python scripts/generate_citas.py 20000      # filas personalizadas
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def generar_citas_excel(
    nombre_archivo="citas_medicas_solicitudes.xlsx", num_filas=10000
):
    print(f"Generando {num_filas} solicitudes de citas médicas en español...")

    fake = Faker("es_ES")

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

    for _ in range(num_filas):
        id_paciente = fake.uuid4()[:8].upper()
        paciente = fake.name()
        ciudad = fake.city()
        especialidad = random.choice(especialidades)

        fecha_deseada = (datetime.now() + timedelta(days=random.randint(2, 30))).strftime("%Y-%m-%d")

        if random.random() < 0.10:
            mensaje_texto = ""
        else:
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

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ruta_salida = DATA_DIR / nombre_archivo
    print(f"Guardando archivo Excel: {ruta_salida}...")
    df.to_excel(ruta_salida, index=False, engine="openpyxl")

    print(f"¡Proceso completado con éxito! Archivo creado: {ruta_salida}")


if __name__ == "__main__":
    num_filas = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
    generar_citas_excel(num_filas=num_filas)