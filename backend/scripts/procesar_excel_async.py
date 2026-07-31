"""
Script CLIENTE (no forma parte del backend).

Lee el Excel de solicitudes de citas médicas y envía cada mensaje al backend
HTTP POST a http://127.0.0.1:8000/api/analyze, en paralelo (asyncio + httpx),
e imprime métricas agregadas de tokenización (ES vs EN).

REQUISITO: el backend debe estar corriendo antes de ejecutar este script
    uvicorn app.main:app --reload      (desde la carpeta backend/)

Uso (desde la carpeta backend/):
    python scripts/procesar_excel_async.py
"""

import asyncio
import time
from pathlib import Path

import httpx
import pandas as pd
from tqdm.asyncio import tqdm

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EXCEL_FILE = DATA_DIR / "citas_medicas_solicitudes.xlsx"

API_URL = "http://127.0.0.1:8000/api/analyze"
MAX_CONCURRENT_REQUESTS = 50

PRICE_PER_MILLION_TOKENS_USD = 2.50


async def send_mensaje(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, texto: str):
    async with semaphore:
        try:
            response = await client.post(
                API_URL, json={"text": texto, "optimizar_tokens": True}, timeout=10.0
            )
            if response.status_code == 200:
                return response.json()
            return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            return {"error": str(e)}


async def main():
    start_time = time.time()
    print("Cargando dataset de citas medicas...")
    df = pd.read_excel(EXCEL_FILE, engine="openpyxl")

    df_validos = df[df["mensaje_texto"].astype(str).str.strip().ne("") & df["mensaje_texto"].notna()]
    mensajes = df_validos["mensaje_texto"].tolist()

    print(f"Registros totales: {len(df):,}")
    print(f"Mensajes validos enviados: {len(mensajes):,}")
    print(f"Conectando al backend en: {API_URL}")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    limits = httpx.Limits(max_keepalive_connections=MAX_CONCURRENT_REQUESTS, max_connections=MAX_CONCURRENT_REQUESTS)

    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [send_mensaje(client, semaphore, texto) for texto in mensajes]
        results = await tqdm.gather(*tasks, desc="Procesando")

    total_es, total_en = 0, 0
    sum_frag = 0.0
    n = 0
    for res in results:
        if "metrics" in res:
            m = res["metrics"]
            total_es += m["original_tokens"]
            total_en += m["translated_tokens"]
            sum_frag += m.get("fragmentacion_ratio", 1.0)
            n += 1

    elapsed = time.time() - start_time
    costo_es = (total_es / 1_000_000) * PRICE_PER_MILLION_TOKENS_USD
    costo_en = (total_en / 1_000_000) * PRICE_PER_MILLION_TOKENS_USD

    print("\n" + "=" * 50)
    print(f"Tiempo total: {elapsed:.2f} segundos")
    print(f"Tokens Espanol: {total_es:,}")
    print(f"Tokens Ingles: {total_en:,}")
    print(f"Fragmentacion media ES/EN: {sum_frag / max(n, 1):.3f}")
    print(f"Costo espanol: ${costo_es:.4f} USD")
    print(f"Costo ingles: ${costo_en:.4f} USD")
    print(f"Ahorro economico: ${costo_es - costo_en:.4f} USD")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
