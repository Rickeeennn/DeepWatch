"""
DeepWatch – NivelSensor_s3.py
Simulador do sensor de nível com gravação no S3 Bronze.

Baseado em NivelSensorLive.py. Mantém a física original intacta:
  - Sloshing modelado com duas ondas senoidais
  - Filtro Butterworth passa-baixa (ordem 4, fc=0.01Hz)

Adições da Fase 1:
  - Grava no S3 Bronze a cada 60 leituras (1 vez por minuto)
  - Schema: timestamp, platform_id, tank_id, tank_level_percent
  - Arquivo salvo em: sensors/nivel/nivel_YYYYMMDD_HHMMSS.csv
"""

import io
import math
import os
import sys
import time
from datetime import datetime

import boto3
import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi

# ─── Configuração AWS ─────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION",    "us-east-1")
BRONZE_BUCKET = os.getenv("BRONZE_BUCKET", "deepwatch-stage-raw-dev")
NIVEL_PREFIX  = "sensors/nivel/"

# ─── Identificação do tanque ──────────────────────────────────────
PLATFORM_ID   = os.getenv("PLATFORM_ID", "FPSO-P67")
TANK_ID       = os.getenv("TANK_ID",     "T-01")

# ─── Parâmetros físicos do tanque ─────────────────────────────────
AREA_TANQUE          = 700.0          # m²
VAZAO_NOMINAL_M3S    = 2000.0 / 3600  # m³/s
TAXA_SUBIDA          = VAZAO_NOMINAL_M3S / AREA_TANQUE
NIVEL_INICIAL        = 15.0           # metros
NIVEL_MAXIMO_TANQUE  = 100.0          # metros (100m = 100%)

# ─── Filtro Butterworth ───────────────────────────────────────────
ORDEM          = 4
FREQ_CORTE     = 0.01
b_coef, a_coef = butter(ORDEM, FREQ_CORTE, btype="low", analog=False)

# ─── Frequência de gravação no S3 ────────────────────────────────
LEITURAS_POR_MINUTO = 60  # 1 leitura/s × 60s = grava 1 vez por minuto


def get_s3():
    return boto3.client("s3", region_name=AWS_REGION)


def gravar_s3(s3, nivel_percent: float, timestamp: datetime):
    """
    Grava uma linha no S3 Bronze com o nível atual.
    Cada arquivo tem exatamente 1 linha — representa 1 minuto de leitura.
    """
    linha = (
        f"timestamp,platform_id,tank_id,tank_level_percent\n"
        f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S')},"
        f"{PLATFORM_ID},{TANK_ID},{nivel_percent:.4f}\n"
    )
    nome = f"nivel_{timestamp.strftime('%Y%m%d_%H%M%S')}.csv"
    key  = f"{NIVEL_PREFIX}{nome}"

    s3.put_object(
        Bucket=BRONZE_BUCKET,
        Key=key,
        Body=linha.encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )
    print(f"  [S3] Gravado: s3://{BRONZE_BUCKET}/{key}  |  nível: {nivel_percent:.2f}%")


def main():
    s3 = get_s3()

    zi           = lfilter_zi(b_coef, a_coef)
    estado_filtro = zi * NIVEL_INICIAL
    tempo_s       = 0
    buffer        = []           # acumula leituras do minuto atual

    print("=" * 55)
    print(f"  DeepWatch – Sensor de Nível")
    print(f"  Plataforma : {PLATFORM_ID}  |  Tanque: {TANK_ID}")
    print(f"  Bucket     : {BRONZE_BUCKET}")
    print(f"  Grava no S3 a cada {LEITURAS_POR_MINUTO}s")
    print(f"  Ctrl+C para encerrar")
    print("=" * 55)

    try:
        while True:
            # ── Física do tanque ──────────────────────────────────
            nivel_real = min(
                NIVEL_MAXIMO_TANQUE,
                NIVEL_INICIAL + TAXA_SUBIDA * tempo_s
            )

            onda1    = 0.8 * math.sin(2 * math.pi * 0.08 * tempo_s)
            onda2    = 0.5 * math.sin(2 * math.pi * 0.12 * tempo_s + math.pi / 4)
            sloshing = onda1 + onda2
            ruido    = np.random.normal(0, 0.05)

            nivel_bruto = max(0.0, min(NIVEL_MAXIMO_TANQUE,
                                       nivel_real + sloshing + ruido))

            # ── Filtro Butterworth ────────────────────────────────
            resultado, estado_filtro = lfilter(
                b_coef, a_coef, [nivel_bruto], zi=estado_filtro
            )
            nivel_filtrado = resultado[0]

            # Converte metros → percentual
            nivel_percent = round((nivel_filtrado / NIVEL_MAXIMO_TANQUE) * 100, 4)
            nivel_percent = max(0.0, min(100.0, nivel_percent))

            buffer.append(nivel_percent)

            print(
                f"t={tempo_s:04d}s | "
                f"Bruto: {nivel_bruto:.2f}m | "
                f"Filtrado: {nivel_filtrado:.2f}m | "
                f"Nível: {nivel_percent:.2f}%",
                end=""
            )

            # ── Grava no S3 a cada minuto ─────────────────────────
            if len(buffer) >= LEITURAS_POR_MINUTO:
                valor_a_gravar = buffer[-1]   # última leitura filtrada do minuto
                gravar_s3(s3, valor_a_gravar, datetime.utcnow())
                buffer = []
            else:
                print()

            tempo_s += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nSimulador encerrado.")
        if buffer:
            print(f"Buffer com {len(buffer)} leituras não gravadas (menos de 1 minuto).")


if __name__ == "__main__":
    main()
