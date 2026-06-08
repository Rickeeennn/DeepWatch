"""
DeepWatch – VazaoSensor_s3.py
Simulador do sensor de vazão com gravação no S3 Bronze.

Baseado em VazaoSensorLive.py. Mantém a física original intacta:
  - Pulsação de bomba modelada com duas senoides
  - Ruído eletrônico gaussiano
  - Filtro média móvel (janela = 5s)

Adições da Fase 1:
  - Grava no S3 Bronze a cada 60 leituras (1 vez por minuto)
  - Schema: timestamp, platform_id, tank_id, flow_rate_m3_h
  - Arquivo salvo em: sensors/vazao/vazao_YYYYMMDD_HHMMSS.csv
"""

import math
import os
import time
from collections import deque
from datetime import datetime

import boto3
import numpy as np

# ─── Configuração AWS ─────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION",    "us-east-1")
BRONZE_BUCKET = os.getenv("BRONZE_BUCKET", "deepwatch-stage-raw-dev")
VAZAO_PREFIX  = "sensors/vazao/"

# ─── Identificação do tanque ──────────────────────────────────────
# Deve ser o MESMO platform_id e tank_id do NivelSensor_s3.py
# para que o merge no ETL funcione corretamente
PLATFORM_ID = os.getenv("PLATFORM_ID", "FPSO-P67")
TANK_ID     = os.getenv("TANK_ID",     "T-01")

# ─── Parâmetros do sensor Coriolis ───────────────────────────────
VAZAO_NOMINAL_M3H = 2000.0
VAZAO_NOMINAL_M3S = VAZAO_NOMINAL_M3H / 3600.0

# ─── Filtro Média Móvel ───────────────────────────────────────────
JANELA_MM = 5

# ─── Frequência de gravação no S3 ────────────────────────────────
LEITURAS_POR_MINUTO = 60


def get_s3():
    return boto3.client("s3", region_name=AWS_REGION)


def gravar_s3(s3, vazao_m3h: float, timestamp: datetime):
    """
    Grava uma linha no S3 Bronze com a vazão atual em m³/h.
    Converte m³/s → m³/h antes de gravar.
    """
    linha = (
        f"timestamp,platform_id,tank_id,flow_rate_m3_h\n"
        f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S')},"
        f"{PLATFORM_ID},{TANK_ID},{vazao_m3h:.4f}\n"
    )
    nome = f"vazao_{timestamp.strftime('%Y%m%d_%H%M%S')}.csv"
    key  = f"{VAZAO_PREFIX}{nome}"

    s3.put_object(
        Bucket=BRONZE_BUCKET,
        Key=key,
        Body=linha.encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )
    print(f"  [S3] Gravado: s3://{BRONZE_BUCKET}/{key}  |  vazão: {vazao_m3h:.1f} m³/h")


def main():
    s3 = get_s3()

    janela_mm = deque(maxlen=JANELA_MM)
    tempo_s   = 0
    buffer    = []

    print("=" * 55)
    print(f"  DeepWatch – Sensor de Vazão (Coriolis)")
    print(f"  Plataforma : {PLATFORM_ID}  |  Tanque: {TANK_ID}")
    print(f"  Bucket     : {BRONZE_BUCKET}")
    print(f"  Nominal    : {VAZAO_NOMINAL_M3H} m³/h")
    print(f"  Grava no S3 a cada {LEITURAS_POR_MINUTO}s")
    print(f"  Ctrl+C para encerrar")
    print("=" * 55)

    try:
        while True:
            # ── Física do sensor Coriolis ─────────────────────────
            pulsacao = (
                0.005 * math.sin(2 * math.pi * 0.5  * tempo_s) +
                0.002 * math.sin(2 * math.pi * 1.2  * tempo_s)
            )
            ruido         = np.random.normal(0, 0.001)
            vazao_bruta_s = VAZAO_NOMINAL_M3S + pulsacao + ruido

            # ── Média Móvel ───────────────────────────────────────
            janela_mm.append(vazao_bruta_s)
            vazao_tratada_s = sum(janela_mm) / len(janela_mm)

            # Converte m³/s → m³/h para gravar
            vazao_tratada_h = round(vazao_tratada_s * 3600, 4)

            buffer.append(vazao_tratada_h)

            print(
                f"t={tempo_s:04d}s | "
                f"Bruta: {vazao_bruta_s:.6f} m³/s | "
                f"Tratada: {vazao_tratada_s:.6f} m³/s | "
                f"{vazao_tratada_h:.1f} m³/h",
                end=""
            )

            # ── Grava no S3 a cada minuto ─────────────────────────
            if len(buffer) >= LEITURAS_POR_MINUTO:
                # Usa a média do minuto inteiro para representar a vazão do período
                media_minuto = round(sum(buffer) / len(buffer), 4)
                gravar_s3(s3, media_minuto, datetime.utcnow())
                buffer = []
            else:
                print()

            tempo_s += 1
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nSimulador encerrado.")
        if buffer:
            print(f"Buffer com {len(buffer)} leituras não gravadas.")


if __name__ == "__main__":
    main()
