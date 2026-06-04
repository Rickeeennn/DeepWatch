"""
DeepWatch – injetar_anomalia.py
Demonstração de detecção de ataques IoT na borda.

Simula um atacante que conseguiu acesso à rede do FPSO e tenta
injetar leituras falsas diretamente no S3 Bronze para manipular
o estado dos tanques e enganar os operadores.

O pipeline (bronze_to_silver_s3.py) detecta e rejeita cada ataque
automaticamente pela validação física dos dados.

Como usar:
  python injetar_anomalia.py

O que acontece:
  1. Envia leituras normais (aceitas pelo pipeline)
  2. Injeta 4 ataques diferentes
  3. Roda o ETL Bronze → Silver
  4. Mostra os eventos de segurança detectados
"""

import boto3
import io
import sys
import os
import time
import subprocess
from datetime import datetime, timedelta

import pandas as pd

# ─── Configuração ─────────────────────────────────────────────────
AWS_REGION    = "us-east-1"
BRONZE_BUCKET = "deepwatch-sptech-stage-raw-dev"
SILVER_BUCKET = "deepwatch-sptech-trusted-dev"
GOLD_BUCKET   = "deepwatch-sptech-client-dev"
PLATFORM_ID   = "FPSO-P67"
TANK_ID       = "T-01"

NIVEL_PREFIX    = "sensors/nivel/"
SECURITY_PREFIX = "security-events/"

# ─── S3 ───────────────────────────────────────────────────────────
s3 = boto3.client("s3", region_name=AWS_REGION)


def gravar_leitura(nivel: float, vazao: float,
                   timestamp: datetime = None, label: str = "normal"):
    """Grava uma leitura diretamente no S3 Bronze."""
    if timestamp is None:
        timestamp = datetime.utcnow()

    # Nivel
    linha_nivel = (
        f"timestamp,platform_id,tank_id,tank_level_percent\n"
        f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S')},"
        f"{PLATFORM_ID},{TANK_ID},{nivel}\n"
    )
    nome_nivel = f"nivel_ATAQUE_{timestamp.strftime('%Y%m%d_%H%M%S')}_{label}.csv"
    s3.put_object(
        Bucket=BRONZE_BUCKET,
        Key=f"{NIVEL_PREFIX}{nome_nivel}",
        Body=linha_nivel.encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )

    # Vazao
    linha_vazao = (
        f"timestamp,platform_id,tank_id,flow_rate_m3_h\n"
        f"{timestamp.strftime('%Y-%m-%dT%H:%M:%S')},"
        f"{PLATFORM_ID},{TANK_ID},{vazao}\n"
    )
    nome_vazao = f"vazao_ATAQUE_{timestamp.strftime('%Y%m%d_%H%M%S')}_{label}.csv"
    s3.put_object(
        Bucket=BRONZE_BUCKET,
        Key=f"sensors/vazao/{nome_vazao}",
        Body=linha_vazao.encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )


def contar_eventos_seguranca() -> int:
    """Conta eventos de segurança no S3."""
    try:
        resp = s3.list_objects_v2(Bucket=SILVER_BUCKET, Prefix=SECURITY_PREFIX)
        arquivos = resp.get("Contents", [])
        if not arquivos:
            return 0
        # Lê o arquivo mais recente
        ultimo = max(arquivos, key=lambda o: o["LastModified"])
        r = s3.get_object(Bucket=SILVER_BUCKET, Key=ultimo["Key"])
        df = pd.read_csv(io.BytesIO(r["Body"].read()))
        return len(df)
    except Exception:
        return 0


def separador(titulo: str):
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print(f"{'='*60}")


def main():
    now = datetime.utcnow().replace(second=0, microsecond=0)

    separador("DeepWatch — Demonstração de Detecção de Ataques IoT")
    print(f"  Bucket Bronze : {BRONZE_BUCKET}")
    print(f"  Bucket Silver : {SILVER_BUCKET}")
    print(f"  Tanque alvo   : {PLATFORM_ID}/{TANK_ID}")
    print(f"  Início        : {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")

    # ── PASSO 1: Leituras normais de referência ───────────────────
    separador("PASSO 1 — Enviando leituras normais (referência)")

    leituras_normais = [
        (91.0, 69.0, -5),
        (91.1, 69.1, -4),
        (91.2, 69.0, -3),
        (91.3, 69.2, -2),
        (91.4, 69.1, -1),
    ]

    for nivel, vazao, offset_min in leituras_normais:
        ts = now + timedelta(minutes=offset_min)
        gravar_leitura(nivel, vazao, ts, "normal")
        print(f"  ✓ [NORMAL] {ts.strftime('%H:%M')} | "
              f"Nível: {nivel}% | Vazão: {vazao} m³/h → gravado no S3")
        time.sleep(0.3)

    print(f"\n  5 leituras normais enviadas.")

    # ── PASSO 2: Injeção dos ataques ──────────────────────────────
    separador("PASSO 2 — Injetando ataques")

    ataques = [
        {
            "nome":    "ATAQUE 1 — Injeção de nível falso",
            "label":   "atk1_nivel",
            "descr":   "Nível salta de 91.4% → 62% em 1 minuto (fisicamente impossível)",
            "nivel":   62.0,
            "vazao":   69.0,
            "offset":  0,
            "ts_tipo": "normal",
        },
        {
            "nome":    "ATAQUE 2 — Valor absurdo",
            "label":   "atk2_range",
            "descr":   "Nível reportado como 150% (acima do máximo físico de 100%)",
            "nivel":   150.0,
            "vazao":   69.0,
            "offset":  1,
            "ts_tipo": "normal",
        },
        {
            "nome":    "ATAQUE 3 — Replay Attack",
            "label":   "atk3_replay",
            "descr":   "Leitura legítima reenviada com timestamp de 10 minutos atrás",
            "nivel":   91.2,
            "vazao":   69.0,
            "offset":  -15,    # timestamp 15min atrás = além do limite de 5min
            "ts_tipo": "passado",
        },
        {
            "nome":    "ATAQUE 4 — Manipulação de vazão",
            "label":   "atk4_vazao",
            "descr":   "Vazão cai de 69 → 3 m³/h em 1 minuto (queda de 96%)",
            "nivel":   91.5,
            "vazao":   3.0,
            "offset":  2,
            "ts_tipo": "normal",
        },
    ]

    for atk in ataques:
        ts = now + timedelta(minutes=atk["offset"])
        print(f"\n  🔴 {atk['nome']}")
        print(f"     {atk['descr']}")
        print(f"     Timestamp: {ts.strftime('%H:%M')} | "
              f"Nível: {atk['nivel']}% | Vazão: {atk['vazao']} m³/h")
        gravar_leitura(atk["nivel"], atk["vazao"], ts, atk["label"])
        print(f"     → Injetado no S3 Bronze")
        time.sleep(0.5)

    print(f"\n  4 ataques injetados no S3 Bronze.")

    # ── PASSO 3: Aguarda e avisa para rodar o ETL na EC2 ─────────
    separador("PASSO 3 — Próximo passo")
    print("""
  Os ataques foram gravados no S3 Bronze.
  Agora rode o pipeline na EC2 para ver a detecção:

    bash run_pipeline.sh

  Depois verifique os eventos detectados:

    aws s3 ls s3://deepwatch-sptech-trusted-dev/security-events/
""")


if __name__ == "__main__":
    main()