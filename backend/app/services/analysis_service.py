"""
Servicio de análisis de solicitudes de citas médicas (HU-015).

Aquí vive la lógica de negocio: detección de columnas, agrupación por
especialidad, clustering semántico, extracción de intención con los modelos
entrenados (accion / especialidad / preferencia_horario), conteo de tokens
ES vs EN (o200k_base) y métrica de fragmentación del vocabulario médico.
"""

import asyncio
import io
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import AsyncGenerator

os.environ["OMP_NUM_THREADS"] = "12"
os.environ["MKL_NUM_THREADS"] = "12"
os.environ["OPENBLAS_NUM_THREADS"] = "12"

import joblib
import numpy as np
import pandas as pd
import tiktoken
from deep_translator import GoogleTranslator
from sklearn.cluster import MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from app.core.config import TOKEN_ENCODING
from app.models.schemas import (
    AnalysisResponse,
    CitaIntent,
    ExtractedCitaData,
    TokenMetrics,
)

_encoder = tiktoken.get_encoding(TOKEN_ENCODING)

_MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
_vectorizer = joblib.load(_MODELS_DIR / "vectorizer.joblib")
_clf_accion = joblib.load(_MODELS_DIR / "accion_model.joblib")
_clf_horario = joblib.load(_MODELS_DIR / "horario_model.joblib")
_clf_especialidad = joblib.load(_MODELS_DIR / "especialidad_model.joblib")

ACCION_CLASSES = ["reprogramar", "cancelar", "confirmar", "otro"]
HORARIO_CLASSES = ["manana", "tarde", "noche", "sin_preferencia"]
ESPECIALIDAD_CLASSES = [
    "cardiologia", "dermatologia", "ginecologia", "neurologia",
    "oftalmologia", "ortopedia", "pediatria", "otorrinolaringologia",
    "gastroenterologia", "urologia", "medicina_general", "endocrinologia",
    "sin_especificar",
]

_ESPECIALIDAD_KEYWORDS = {
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

MAX_CLUSTERS_PER_ESPECIALIDAD = 10
MIN_MESSAGES_FOR_CLUSTERING = 50
_K_FIXO = 5

_translator_pool = ThreadPoolExecutor(max_workers=6)

# ──────────────────────────────────────────────────────────────────────────
# Caché de traducciones ES→EN (mismo texto → mismo resultado, evita que la
# API de Google devuelva variaciones entre ejecuciones).
# ──────────────────────────────────────────────────────────────────────────
_translation_cache: dict[str, str] = {}
_translation_lock = threading.Lock()
_translation_version = 0
_translation_saved_version = 0
_CACHE_FILE = Path(__file__).resolve().parent / "translation_cache.json"


def _cargar_cache_traducciones() -> None:
    global _translation_cache
    try:
        if _CACHE_FILE.is_file():
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                _translation_cache = {str(k): str(v) for k, v in data.items()}
    except Exception:
        _translation_cache = {}


def _guardar_cache_traducciones() -> None:
    try:
        tmp = _CACHE_FILE.with_name(_CACHE_FILE.name + ".tmp")
        with _translation_lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_translation_cache, f, ensure_ascii=False, indent=1)
        tmp.replace(_CACHE_FILE)
    except Exception:
        pass


_cargar_cache_traducciones()

_translator_es_en = GoogleTranslator(source="es", target="en")


def _traducir_con_cache(texto: str) -> str:
    """Traduce ES→EN usando la caché; guarda el resultado para futuras llamadas."""
    global _translation_version
    with _translation_lock:
        if texto in _translation_cache:
            return _translation_cache[texto]
    try:
        traducido = _translator_es_en.translate(texto)
    except Exception:
        return texto
    with _translation_lock:
        if texto not in _translation_cache:
            _translation_cache[texto] = traducido
            _translation_version += 1
    return traducido


def _generar_summary(texto: str, max_chars: int = 100) -> str:
    texto = texto.strip()
    if not texto:
        return ""
    if len(texto) <= max_chars:
        return texto
    truncated = texto[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > 20:
        truncated = truncated[:last_space]
    return truncated + "..."


def _traducir_lote(textos: list[str]) -> list[str]:
    global _translation_saved_version
    resultados = list(_translator_pool.map(_traducir_con_cache, textos))
    with _translation_lock:
        hay_nuevos = _translation_version != _translation_saved_version
        if hay_nuevos:
            _translation_saved_version = _translation_version
    if hay_nuevos:
        _guardar_cache_traducciones()
    return resultados


# ──────────────────────────────────────────────────────────────────────────
# Detección y validación de columnas
# ──────────────────────────────────────────────────────────────────────────

def _detectar_columna_mensaje(df: pd.DataFrame) -> str | None:
    candidatas = [
        "mensaje_texto", "mensaje", "texto", "text", "solicitud",
        "mensaje_paciente", "request", "message",
    ]
    columnas = [c.lower().strip() for c in df.columns]
    for cand in candidatas:
        if cand in columnas:
            return df.columns[columnas.index(cand)]
    for c in df.columns:
        if any(kw in c.lower() for kw in ["mensaje", "texto", "text", "solicitud"]):
            return c
    return None


def _detectar_columna_especialidad(df: pd.DataFrame) -> str | None:
    candidatas = ["especialidad_medica", "especialidad", "specialty"]
    columnas = [c.lower().strip() for c in df.columns]
    for cand in candidatas:
        if cand in columnas:
            return df.columns[columnas.index(cand)]
    return None


def _detectar_columna_paciente(df: pd.DataFrame) -> str | None:
    candidatas = ["id_paciente", "paciente_id", "patient_id", "id_paciente"]
    columnas = [c.lower().strip() for c in df.columns]
    for cand in candidatas:
        if cand in columnas:
            return df.columns[columnas.index(cand)]
    return None


def _validar_columnas(df: pd.DataFrame) -> None:
    """Criterio 1 de la HU: validar que las columnas se parseen antes del análisis."""
    col_mensaje = _detectar_columna_mensaje(df)
    if col_mensaje is None:
        esperadas = ["mensaje_texto", "id_paciente", "especialidad_medica"]
        raise ValueError(
            f"No se encontró columna de mensaje. Se esperaban columnas como: {esperadas}. "
            f"Columnas detectadas: {list(df.columns)}"
        )
    for col in df.columns:
        if str(df[col].dtype).startswith("datetime"):
            df[col] = df[col].astype(str)


# ──────────────────────────────────────────────────────────────────────────
# Extracción de intención
# ──────────────────────────────────────────────────────────────────────────

def _normalizar_especialidad(valor: str) -> str:
    texto = valor.lower().strip()
    for especialidad, keywords in _ESPECIALIDAD_KEYWORDS.items():
        for kw in keywords:
            if kw in texto:
                return especialidad
    return "sin_especificar"


def _extraer_especialidad_texto(texto: str) -> str:
    """Keyword matching directo: más preciso para detectar 'cardiólogo' → cardiología."""
    texto_lower = texto.lower()
    for especialidad, keywords in _ESPECIALIDAD_KEYWORDS.items():
        for kw in keywords:
            if kw in texto_lower:
                return especialidad
    return "sin_especificar"


def _predecir_intencion(texto: str, especialidad_col: str | None = None) -> CitaIntent:
    X = _vectorizer.transform([texto])
    accion = ACCION_CLASSES[_clf_accion.predict(X)[0]]
    horario = HORARIO_CLASSES[_clf_horario.predict(X)[0]]

    if especialidad_col:
        especialidad = _normalizar_especialidad(especialidad_col)
    else:
        especialidad = _extraer_especialidad_texto(texto)
        if especialidad == "sin_especificar":
            especialidad = ESPECIALIDAD_CLASSES[_clf_especialidad.predict(X)[0]]

    return CitaIntent(
        accion=accion,
        especialidad=especialidad,
        preferencia_horario=horario,
    )


# ──────────────────────────────────────────────────────────────────────────
# Clustering semántico por especialidad
# ──────────────────────────────────────────────────────────────────────────

def _optimal_k(X, k_min=2, k_max=MAX_CLUSTERS_PER_ESPECIALIDAD):
    n_samples = X.shape[0]
    if n_samples < 4:
        return 1
    return min(_K_FIXO, n_samples - 1)


def _cluster_mensajes(textos: list[str]) -> tuple[list[tuple[int, str, int, int]], list[int] | None]:
    """Retorna ([(cluster_id, texto_representativo, num_mensajes, idx_rep), ...], labels)."""
    n = len(textos)
    if n == 0:
        return [], None
    if n < MIN_MESSAGES_FOR_CLUSTERING:
        idx_rep = max(range(n), key=lambda i: len(textos[i]))
        return [(0, textos[idx_rep], n, idx_rep)], None

    tfidf = TfidfVectorizer(max_features=500, ngram_range=(1, 2), lowercase=True)
    X = tfidf.fit_transform(textos)

    k = _optimal_k(X)
    k = max(1, k)

    km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=1, max_iter=50, batch_size=2048)
    labels = km.fit_predict(X)

    representantes = []
    for cluster_id in range(k):
        cluster_indices = np.where(labels == cluster_id)[0]
        if len(cluster_indices) == 0:
            continue
        X_cluster = X[cluster_indices]
        centroid = km.cluster_centers_[cluster_id]
        dists = np.linalg.norm(X_cluster.toarray() - centroid, axis=1)
        rep_idx = cluster_indices[np.argmin(dists)]
        representantes.append((cluster_id, textos[rep_idx], len(cluster_indices), int(rep_idx)))

    return representantes, labels.tolist()


# ──────────────────────────────────────────────────────────────────────────
# Procesamiento por especialidad (grupo)
# ──────────────────────────────────────────────────────────────────────────

def _procesar_especialidad_grupo(
    esp_name: str,
    textos_grupo: list[str],
    ids_grupo: list[str],
    optimizar_tokens: bool,
) -> tuple[list[AnalysisResponse], dict]:
    timings = {}

    if not textos_grupo:
        return [], timings

    t0 = time.time()
    reps, labels = _cluster_mensajes(textos_grupo)
    timings["clustering"] = time.time() - t0

    rep_textos = [r[1] for r in reps]

    if optimizar_tokens:
        t0 = time.time()
        rep_textos_en = _traducir_lote(rep_textos)
        timings["traduccion"] = time.time() - t0
    else:
        rep_textos_en = rep_textos

    t0 = time.time()
    results = []
    for i, (cluster_id, rep_texto, n_messages, rep_idx) in enumerate(reps):
        intent = _predecir_intencion(rep_texto, especialidad_col=esp_name)
        sum_es = _generar_summary(rep_texto)
        sum_en = _generar_summary(rep_textos_en[i])

        if labels is not None:
            cluster_texts = [textos_grupo[j] for j in range(len(textos_grupo)) if labels[j] == cluster_id]
            tokens_es = sum(len(_encoder.encode(t)) for t in cluster_texts)
        else:
            tokens_es = sum(len(_encoder.encode(t)) for t in textos_grupo)

        if optimizar_tokens:
            tokens_en = n_messages * len(_encoder.encode(rep_textos_en[i]))
        else:
            tokens_en = tokens_es

        id_rep = ids_grupo[rep_idx] if rep_idx < len(ids_grupo) else ""

        results.append(AnalysisResponse(
            metrics=TokenMetrics(
                original_tokens=tokens_es,
                translated_tokens=tokens_en,
                tokens_saved_per_request=max(0, tokens_es - len(_encoder.encode(rep_texto))),
                fragmentacion_ratio=round(tokens_es / max(tokens_en, 1), 4),
            ),
            extracted_data=ExtractedCitaData(
                intent=intent,
                summary_es=sum_es,
                summary_en=sum_en,
                id_paciente=id_rep,
                especialidad_medica=esp_name,
                cluster_id=cluster_id,
                messages_in_cluster=n_messages,
            ),
        ))
    timings["tiktoken"] = time.time() - t0

    return results, timings


def _procesar_por_especialidad(
    df: pd.DataFrame,
    col_mensaje: str,
    col_especialidad: str | None,
    col_paciente: str | None,
    optimizar_tokens: bool,
) -> tuple[list[AnalysisResponse], dict]:
    timings = {}
    all_results = []

    t0 = time.time()
    if col_especialidad:
        grupos = list(df.groupby(col_especialidad))
    else:
        grupos = [("general", df)]
    timings["agrupacion"] = time.time() - t0

    def _preparar_grupo(name, group):
        textos = group[col_mensaje].dropna().astype(str).str.strip()
        textos = textos[textos.ne("")].tolist()
        ids = group[col_paciente].astype(str).tolist() if col_paciente else [""] * len(group)
        return name, textos, ids

    items = [_preparar_grupo(name, group) for name, group in grupos]
    items = [(n, t, i) for n, t, i in items if t]

    with ThreadPoolExecutor(max_workers=max(1, len(items))) as pool:
        futures = [
            pool.submit(_procesar_especialidad_grupo, name, textos, ids, optimizar_tokens)
            for name, textos, ids in items
        ]
        for fut in futures:
            results_chunk, t_chunk = fut.result()
            all_results.extend(results_chunk)
            for k, v in t_chunk.items():
                timings[k] = timings.get(k, 0.0) + v

    return all_results, timings


# ──────────────────────────────────────────────────────────────────────────
# Entradas: archivo / carpeta / single
# ──────────────────────────────────────────────────────────────────────────

def procesar_archivo_excel(contents: bytes, optimizar_tokens: bool = False) -> list[AnalysisResponse]:
    df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
    _validar_columnas(df)

    col_mensaje = _detectar_columna_mensaje(df)
    col_especialidad = _detectar_columna_especialidad(df)
    col_paciente = _detectar_columna_paciente(df)

    results, _ = _procesar_por_especialidad(
        df, col_mensaje, col_especialidad, col_paciente, optimizar_tokens
    )
    return results


def procesar_carpeta_excel(carpeta: Path, optimizar_tokens: bool = False) -> list[AnalysisResponse]:
    archivos = list(carpeta.glob("*.xlsx")) + list(carpeta.glob("*.xls"))
    if not archivos:
        raise ValueError(f"No se encontraron archivos .xlsx en la carpeta: {carpeta}")

    resultados = []
    for archivo in archivos:
        df = pd.read_excel(archivo, engine="openpyxl")
        _validar_columnas(df)

        col_mensaje = _detectar_columna_mensaje(df)
        col_especialidad = _detectar_columna_especialidad(df)
        col_paciente = _detectar_columna_paciente(df)

        lote, _ = _procesar_por_especialidad(
            df, col_mensaje, col_especialidad, col_paciente, optimizar_tokens
        )
        resultados.extend(lote)
    return resultados


def analizar_cita(texto_es: str, optimizar_tokens: bool = False) -> AnalysisResponse:
    intent = _predecir_intencion(texto_es)

    if optimizar_tokens:
        texto_en = _traducir_con_cache(texto_es)
    else:
        texto_en = texto_es

    tokens_es = len(_encoder.encode(texto_es))
    tokens_en = len(_encoder.encode(texto_en))

    return AnalysisResponse(
        metrics=TokenMetrics(
            original_tokens=tokens_es,
            translated_tokens=tokens_en,
            tokens_saved_per_request=0,
            fragmentacion_ratio=round(tokens_es / max(tokens_en, 1), 4),
        ),
        extracted_data=ExtractedCitaData(
            intent=intent,
            summary_es=_generar_summary(texto_es),
            summary_en=_generar_summary(texto_en),
            id_paciente="",
            especialidad_medica=intent.especialidad,
            cluster_id=-1,
            messages_in_cluster=1,
        ),
    )


# ──────────────────────────────────────────────────────────────────────────
# Streaming SSE
# ──────────────────────────────────────────────────────────────────────────

async def procesar_archivo_excel_stream(
    contents: bytes,
    optimizar_tokens: bool = False,
) -> AsyncGenerator[str, None]:

    def _emit(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    yield _emit("progress", {"stage": "lectura", "message": "Leyendo archivo Excel...", "progress": 0})

    try:
        df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
        _validar_columnas(df)
    except Exception as e:
        yield _emit("error", {"message": str(e)})
        return

    col_mensaje = _detectar_columna_mensaje(df)
    col_especialidad = _detectar_columna_especialidad(df)
    col_paciente = _detectar_columna_paciente(df)

    mensajes = df[col_mensaje].dropna().astype(str).str.strip()
    total_original = int(mensajes.ne("").sum())

    if total_original == 0:
        yield _emit("progress", {
            "stage": "completo",
            "message": "No se encontraron mensajes en el archivo",
            "progress": 100,
            "total": 0,
            "processed": 0,
            "results": [],
            "timings": {},
        })
        return

    yield _emit("progress", {
        "stage": "lectura",
        "message": f"Archivo leído: {total_original} mensajes",
        "progress": 3,
        "total": total_original,
        "processed": 0,
    })

    if col_especialidad:
        n_especialidades = int(df[col_especialidad].nunique())
        yield _emit("progress", {
            "stage": "clustering",
            "message": f"Agrupando por especialidad médica ({n_especialidades} especialidades)...",
            "progress": 8,
            "total": total_original,
            "processed": 0,
        })
    else:
        yield _emit("progress", {
            "stage": "clustering",
            "message": "Agrupando mensajes similares...",
            "progress": 8,
            "total": total_original,
            "processed": 0,
        })

    def _do_full_processing():
        return _procesar_por_especialidad(
            df, col_mensaje, col_especialidad, col_paciente, optimizar_tokens
        )

    all_results, timings = await asyncio.get_event_loop().run_in_executor(
        None, _do_full_processing
    )

    yield _emit("progress", {
        "stage": "clasificacion",
        "message": f"Extrayendo intención de {len(all_results)} representantes...",
        "progress": 90,
        "total": total_original,
        "processed": total_original,
    })

    yield _emit("progress", {
        "stage": "completo",
        "message": f"Completado: {total_original} mensajes → {len(all_results)} grupos representativos",
        "progress": 100,
        "total": total_original,
        "processed": total_original,
        "results": [r.model_dump() for r in all_results],
        "timings": timings,
    })
