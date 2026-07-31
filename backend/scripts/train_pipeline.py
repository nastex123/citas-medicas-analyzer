"""
Entrena los clasificadores para HU-015 (citas medicas):
  - accion: reprogramar | cancelar | confirmar | otro
  - especialidad: cardiologia, dermatologia, ... | sin_especificar
  - preferencia_horario: manana | tarde | noche | sin_preferencia

Usa pseudo-labels generadas por keywords sobre el dataset de citas y
aumenta clases subrepresentadas con variantes sinteticas.

Uso (desde la carpeta backend/):
    venv\\Scripts\\activate
    python scripts/train_pipeline.py
"""

import os
import random
import time
from pathlib import Path

os.environ["OMP_NUM_THREADS"] = "12"
os.environ["MKL_NUM_THREADS"] = "12"
os.environ["OPENBLAS_NUM_THREADS"] = "12"

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.svm import LinearSVC

TIMINGS = {}

BASE = Path(__file__).resolve().parent.parent
DATA_PATH = BASE / "data" / "citas_medicas_solicitudes.xlsx"
MODELS_DIR = BASE / "app" / "models"

ACCION_KEYWORDS = {
    "reprogramar": [
        "reprogramac", "reagend", "postergar", "postergarla", "adelantar",
        "modificar la fecha", "modificar mi cita", "cambiar el horario",
        "cambiar la fecha", "cambio de fecha", "cambio de horario", "reagendar",
    ],
    "cancelar": [
        "cancelar", "cancelaci", "cancela", "anular", "dar de baja mi cita",
    ],
    "confirmar": [
        "confirmar", "confirmaci", "confirm",
    ],
}

HORARIO_KEYWORDS = {
    "manana": [
        "mañana", "manana", "primeras horas", "de la mañana", "por la mañana",
        "temprano", "madrugada",
    ],
    "tarde": [
        "de la tarde", "por la tarde", "turno de la tarde", "tarde",
    ],
    "noche": [
        "de la noche", "por la noche", "nocturn", "vespertino",
    ],
}

ESPECIALIDAD_KEYWORDS = {
    "cardiologia": ["cardio"],
    "dermatologia": ["dermat", "piel"],
    "ginecologia": ["ginec", "obstetric"],
    "neurologia": ["neuro", "cerebro"],
    "oftalmologia": ["oftalm", "ojos", "vista", "ocular"],
    "ortopedia": ["ortoped", "traumatolog", "hueso", "articulaciones"],
    "pediatria": ["pediatr", "niños", "ninos", "niño", "nino"],
    "otorrinolaringologia": ["otorrinolaringolog", "otorrino", "oído", "oido", "oídos"],
    "gastroenterologia": ["gastroenterolog", "digestivo", "estómago", "estomago", "intestino"],
    "urologia": ["urolog"],
    "medicina_general": ["medicina general", "médico general", "medico general", "medicina familiar"],
    "endocrinologia": ["endocrinolog", "hormona", "tiroides"],
}

ACCION_CLASSES = ["reprogramar", "cancelar", "confirmar", "otro"]
HORARIO_CLASSES = ["manana", "tarde", "noche", "sin_preferencia"]
ESPECIALIDAD_CLASSES = list(ESPECIALIDAD_KEYWORDS.keys()) + ["sin_especificar"]

MIN_SAMPLES = 250

_SYNTHETIC_ACCION = {
    "reprogramar": [
        "Deseo reprogramar mi cita médica para la próxima semana",
        "Necesito modificar la fecha de mi consulta asignada",
        "Solicito reagendar mi control periódico para el próximo mes",
        "Quiero postergar mi atención especializada",
        "Requiero adelantar mi turno médico por motivos de urgencia",
        "Deseo cambiar el horario de mi cita con el especialista",
        "Es posible modificar la fecha de mi revisión médica",
        "Agradecería reagendar mi cita a otra fecha disponible",
        "Necesito postergar mi consulta por inconvenientes personales",
        "Solicito cambiar la fecha de mi turno médico asignado",
    ],
    "cancelar": [
        "Deseo cancelar mi cita médica programada",
        "Solicito la cancelación de mi consulta de esta semana",
        "No podré asistir, requiero cancelar el turno asignado",
        "Por favor cancelar mi cita con el especialista",
        "Necesito anular mi turno médico del próximo lunes",
    ],
    "confirmar": [
        "Deseo confirmar mi cita médica del viernes",
        "Solicito la confirmación de mi turno programado",
        "Confirmo mi asistencia a la consulta asignada",
        "Por favor confirmar la disponibilidad de mi cita",
    ],
}

_SYNTHETIC_HORARIO = {
    "manana": [
        "de preferencia en el horario de la mañana",
        "en las primeras horas del día",
        "por la mañana temprano",
        "en el turno de la mañana",
        "a primera hora de la mañana",
    ],
    "tarde": [
        "en el turno de la tarde",
        "por la tarde después del trabajo",
        "en horario de la tarde",
        "por la tarde es mi preferencia",
    ],
    "noche": [
        "en el horario de la noche",
        "por la noche después del trabajo",
        "en turno nocturno",
        "de noche sería ideal",
    ],
}

_SYNTHETIC_ESPECIALIDAD = {
    "cardiologia": ["con el cardiólogo", "en cardiología", "para revisión cardiológica"],
    "dermatologia": ["con el dermatólogo", "en dermatología", "para mi piel"],
    "ginecologia": ["en ginecología", "con el ginecólogo", "en obstetricia"],
    "neurologia": ["con el neurólogo", "en neurología", "revisión neurológica"],
    "oftalmologia": ["con el oftalmólogo", "en oftalmología", "revisión de mis ojos"],
    "ortopedia": ["en ortopedia", "con el traumatólogo", "por mis huesos"],
    "pediatria": ["en pediatría", "consulta pediátrica", "para mi hijo en pediatría"],
    "otorrinolaringologia": ["en otorrinolaringología", "con el otorrino", "por mis oídos"],
    "gastroenterologia": ["en gastroenterología", "con el gastroenterólogo", "por mi estómago"],
    "urologia": ["en urología", "con el urólogo"],
    "medicina_general": ["en medicina general", "con el médico general"],
    "endocrinologia": ["en endocrinología", "con el endocrinólogo", "por mi tiroides"],
}


def _match_keywords(texto: str, keywords: dict) -> str:
    texto_lower = texto.lower()
    for label, kws in keywords.items():
        for kw in kws:
            if kw in texto_lower:
                return label
    return None


def _pseudo_label_accion(texto: str) -> str:
    return _match_keywords(texto, ACCION_KEYWORDS) or "otro"


def _pseudo_label_horario(texto: str) -> str:
    return _match_keywords(texto, HORARIO_KEYWORDS) or "sin_preferencia"


def _pseudo_label_especialidad(texto: str) -> str:
    return _match_keywords(texto, ESPECIALIDAD_KEYWORDS) or "sin_especificar"


def _aumentar_balanceado(
    textos: list[str],
    y_accion: list[str],
    y_horario: list[str],
    y_especialidad: list[str],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Aumenta las clases subrepresentadas de cada target en un solo paso
    para que textos y todas las etiquetas crezcan de forma consistente."""
    textos_aug = list(textos)
    y_accion_aug = list(y_accion)
    y_horario_aug = list(y_horario)
    y_esp_aug = list(y_especialidad)

    targets = [
        ("accion", y_accion, ACCION_CLASSES, _SYNTHETIC_ACCION),
        ("horario", y_horario, HORARIO_CLASSES, _SYNTHETIC_HORARIO),
        ("especialidad", y_especialidad, ESPECIALIDAD_CLASSES, _SYNTHETIC_ESPECIALIDAD),
    ]

    for t_name, y_target, clases, sintetico in targets:
        for clase in clases:
            actual = sum(1 for lbl in y_target if lbl == clase)
            faltantes = MIN_SAMPLES - actual
            if faltantes <= 0:
                continue
            variantes = sintetico.get(clase) or [clase.replace("_", " ")]
            for _ in range(faltantes):
                base = random.choice(variantes)
                textos_aug.append(base)
                y_accion_aug.append(clase if t_name == "accion" else _pseudo_label_accion(base))
                y_horario_aug.append(clase if t_name == "horario" else _pseudo_label_horario(base))
                y_esp_aug.append(clase if t_name == "especialidad" else _pseudo_label_especialidad(base))

    return textos_aug, y_accion_aug, y_horario_aug, y_esp_aug


def train():
    print("=" * 60)
    print("Entrenamiento del pipeline de clasificacion de citas medicas")
    print("=" * 60)

    models_dir = MODELS_DIR
    models_dir.mkdir(parents=True, exist_ok=True)

    t_read = time.time()
    df = pd.read_excel(DATA_PATH, engine="openpyxl")
    textos = df["mensaje_texto"].dropna().astype(str).str.strip()
    textos = textos[textos.ne("")].tolist()
    TIMINGS["lectura"] = time.time() - t_read
    print(f"\n[OK] Lectura: {TIMINGS['lectura']:.2f}s | {len(textos)} mensajes")

    t_label = time.time()
    y_accion = [_pseudo_label_accion(t) for t in textos]
    y_horario = [_pseudo_label_horario(t) for t in textos]
    y_especialidad = [_pseudo_label_especialidad(t) for t in textos]
    TIMINGS["pseudo_labels"] = time.time() - t_label
    print(f"[OK] Pseudo-labels: {TIMINGS['pseudo_labels']:.2f}s")

    def _distribucion(y):
        d = {}
        for lbl in y:
            d[lbl] = d.get(lbl, 0) + 1
        return d

    print(f"  accion distribucion: {_distribucion(y_accion)}")
    print(f"  horario distribucion: {_distribucion(y_horario)}")
    print(f"  especialidad distribucion: {_distribucion(y_especialidad)}")

    textos, y_accion, y_horario, y_especialidad = _aumentar_balanceado(
        textos, y_accion, y_horario, y_especialidad
    )
    print(f"[OK] Tras aumento: {len(textos)} muestras")

    y_accion_arr = np.array([ACCION_CLASSES.index(e) for e in y_accion])
    y_horario_arr = np.array([HORARIO_CLASSES.index(s) for s in y_horario])
    y_especialidad_arr = np.array([ESPECIALIDAD_CLASSES.index(s) for s in y_especialidad])

    t_vec = time.time()
    vectorizer = HashingVectorizer(
        n_features=2 ** 20,
        ngram_range=(1, 2),
        alternate_sign=False,
        analyzer="word",
        lowercase=True,
    )
    X = vectorizer.transform(textos)
    TIMINGS["vectorizacion"] = time.time() - t_vec
    print(f"[OK] Vectorizacion: {TIMINGS['vectorizacion']:.2f}s | matriz: {X.shape}")

    def _entrenar(nombre, X, y):
        t0 = time.time()
        clf = LinearSVC(
            random_state=42, max_iter=2000, dual="auto", tol=1e-4,
            C=1.0, multi_class="ovr",
        )
        clf.fit(X, y)
        acc = (clf.predict(X) == y).mean()
        TIMINGS[nombre] = time.time() - t0
        print(f"[OK] Entrenamiento {nombre}: {TIMINGS[nombre]:.2f}s | accuracy: {acc:.4f}")
        return clf

    clf_accion = _entrenar("accion", X, y_accion_arr)
    clf_horario = _entrenar("horario", X, y_horario_arr)
    clf_especialidad = _entrenar("especialidad", X, y_especialidad_arr)

    t_save = time.time()
    joblib.dump(vectorizer, models_dir / "vectorizer.joblib")
    joblib.dump(clf_accion, models_dir / "accion_model.joblib")
    joblib.dump(clf_horario, models_dir / "horario_model.joblib")
    joblib.dump(clf_especialidad, models_dir / "especialidad_model.joblib")
    TIMINGS["guardado"] = time.time() - t_save
    print(f"[OK] Modelos guardados en {models_dir}")

    total = sum(TIMINGS.values())
    print(f"\n{'=' * 60}")
    print(f"Tiempo total de entrenamiento: {total:.2f}s")
    for nombre in ("vectorizer.joblib", "accion_model.joblib", "horario_model.joblib", "especialidad_model.joblib"):
        print(f"  {models_dir / nombre}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    train()
