"""
DeepWatch – pipeline_monitor.py
Monitor de saúde do pipeline de dados e eventos de segurança.

O que monitora:
  1. Frescor dos dados: há quanto tempo não chega dado novo no Bronze?
  2. Taxa de rejeição: quantas leituras foram rejeitadas na Silver?
  3. Eventos de segurança: quantas leituras suspeitas foram detectadas?
  4. Saúde do Gold: o Gold foi gerado recentemente?
  5. Tanques críticos: quantos tanques estão em estado CRÍTICO no Gold?

Como usar:
  - Rodar manualmente: python pipeline_monitor.py
  - Agendar no cron da EC2: */5 * * * * python /opt/deepwatch/pipeline_monitor.py
"""

import boto3
import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("deepwatch.monitor")

# ─── Parâmetros ───────────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION",    "us-east-1")
BRONZE_BUCKET = os.getenv("BRONZE_BUCKET", "deepwatch-stage-raw-dev")
SILVER_BUCKET = os.getenv("SILVER_BUCKET", "deepwatch-trusted-dev")
GOLD_BUCKET   = os.getenv("GOLD_BUCKET",   "deepwatch-client-dev")
BRONZE_PREFIX = os.getenv("BRONZE_PREFIX", "sensors/")
SILVER_PREFIX = os.getenv("SILVER_PREFIX", "silver/")
GOLD_PREFIX   = os.getenv("GOLD_PREFIX",   "gold/")
SECURITY_PFX  = os.getenv("SECURITY_PREFIX", "security-events/")

# Limites para alertas
MAX_MINUTOS_SEM_DADO_BRONZE  = 5    # mais de 5min sem dado = sensor offline
MAX_MINUTOS_SEM_DADO_GOLD    = 30   # gold desatualizado
MAX_TAXA_REJEICAO_SILVER     = 0.05 # 5% de rejeição é atenção
CRITICO_TAXA_REJEICAO_SILVER = 0.15 # 15% é crítico


# ─── S3 helpers ──────────────────────────────────────────────────

def s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def ultimo_objeto(s3, bucket: str, prefix: str) -> Optional[dict]:
    """Retorna o objeto mais recente de um bucket/prefix."""
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    objetos  = response.get("Contents", [])
    if not objetos:
        return None
    return max(objetos, key=lambda o: o["LastModified"])


def minutos_desde_ultima_modificacao(obj: Optional[dict]) -> Optional[float]:
    if obj is None:
        return None
    agora   = datetime.now(timezone.utc)
    ultima  = obj["LastModified"]
    delta   = agora - ultima
    return round(delta.total_seconds() / 60, 1)


def ler_csv_s3(s3, bucket, key) -> Optional[pd.DataFrame]:
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        return pd.read_csv(io.BytesIO(response["Body"].read()))
    except Exception as e:
        logger.error(f"Erro ao ler {bucket}/{key}: {e}")
        return None


def contar_objetos(s3, bucket: str, prefix: str) -> int:
    paginator = s3.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        total += len(page.get("Contents", []))
    return total


# ─── Verificações individuais ─────────────────────────────────────

def checar_frescor_bronze(s3) -> dict:
    """Verifica há quanto tempo o último dado chegou no Bronze."""
    obj = ultimo_objeto(s3, BRONZE_BUCKET, BRONZE_PREFIX)
    minutos = minutos_desde_ultima_modificacao(obj)

    if minutos is None:
        return {
            "check": "bronze_frescor",
            "status": "CRÍTICO",
            "mensagem": "Nenhum arquivo encontrado no Bronze",
            "valor": None
        }

    if minutos > MAX_MINUTOS_SEM_DADO_BRONZE:
        status = "CRÍTICO" if minutos > MAX_MINUTOS_SEM_DADO_BRONZE * 3 else "ATENÇÃO"
        return {
            "check": "bronze_frescor",
            "status": status,
            "mensagem": f"Último dado Bronze há {minutos} min (limite: {MAX_MINUTOS_SEM_DADO_BRONZE} min)",
            "valor": minutos
        }

    return {
        "check": "bronze_frescor",
        "status": "NORMAL",
        "mensagem": f"Bronze atualizado há {minutos} min",
        "valor": minutos
    }


def checar_taxa_rejeicao_silver(s3) -> dict:
    """
    Compara registros Bronze vs Silver para calcular taxa de rejeição.
    Taxa alta indica muitos dados inválidos — pode ser ataque ou falha de sensor.
    """
    n_bronze = contar_objetos(s3, BRONZE_BUCKET, BRONZE_PREFIX)
    n_silver = contar_objetos(s3, SILVER_BUCKET, SILVER_PREFIX)

    if n_bronze == 0:
        return {
            "check": "silver_taxa_rejeicao",
            "status": "ATENÇÃO",
            "mensagem": "Sem arquivos Bronze para comparar",
            "valor": None
        }

    # Conta linhas nos CSVs mais recentes
    obj_bronze = ultimo_objeto(s3, BRONZE_BUCKET, BRONZE_PREFIX)
    obj_silver = ultimo_objeto(s3, SILVER_BUCKET, SILVER_PREFIX)

    if obj_bronze is None or obj_silver is None:
        return {
            "check": "silver_taxa_rejeicao",
            "status": "ATENÇÃO",
            "mensagem": "Não foi possível comparar Bronze e Silver",
            "valor": None
        }

    df_b = ler_csv_s3(s3, BRONZE_BUCKET, obj_bronze["Key"])
    df_s = ler_csv_s3(s3, SILVER_BUCKET, obj_silver["Key"])

    if df_b is None or df_s is None:
        return {
            "check": "silver_taxa_rejeicao",
            "status": "ATENÇÃO",
            "mensagem": "Erro ao ler arquivos para comparação",
            "valor": None
        }

    taxa = 1 - (len(df_s) / len(df_b)) if len(df_b) > 0 else 0

    if taxa >= CRITICO_TAXA_REJEICAO_SILVER:
        status = "CRÍTICO"
    elif taxa >= MAX_TAXA_REJEICAO_SILVER:
        status = "ATENÇÃO"
    else:
        status = "NORMAL"

    return {
        "check": "silver_taxa_rejeicao",
        "status": status,
        "mensagem": f"Taxa de rejeição: {taxa:.1%} ({len(df_b)} Bronze → {len(df_s)} Silver)",
        "valor": round(taxa, 4)
    }


def checar_eventos_seguranca(s3) -> dict:
    """Verifica se há eventos de segurança recentes registrados pelo ETL."""
    obj = ultimo_objeto(s3, SILVER_BUCKET, SECURITY_PFX)

    if obj is None:
        return {
            "check": "security_events",
            "status": "NORMAL",
            "mensagem": "Nenhum evento de segurança registrado",
            "valor": 0
        }

    minutos = minutos_desde_ultima_modificacao(obj)
    df = ler_csv_s3(s3, SILVER_BUCKET, obj["Key"])
    n_eventos = len(df) if df is not None else 0

    if n_eventos == 0:
        status = "NORMAL"
    elif n_eventos < 5:
        status = "ATENÇÃO"
    else:
        status = "CRÍTICO"

    # Conta tipos de eventos
    tipos = {}
    if df is not None and "tipo_evento" in df.columns:
        tipos = df["tipo_evento"].value_counts().to_dict()

    return {
        "check": "security_events",
        "status": status,
        "mensagem": f"{n_eventos} evento(s) de segurança nos últimos {minutos} min | Tipos: {tipos}",
        "valor": n_eventos,
        "detalhes": tipos
    }


def checar_frescor_gold(s3) -> dict:
    """Verifica se o Gold foi processado recentemente."""
    obj = ultimo_objeto(s3, GOLD_BUCKET, GOLD_PREFIX)
    minutos = minutos_desde_ultima_modificacao(obj)

    if minutos is None:
        return {
            "check": "gold_frescor",
            "status": "CRÍTICO",
            "mensagem": "Nenhum arquivo Gold encontrado",
            "valor": None
        }

    status = "CRÍTICO" if minutos > MAX_MINUTOS_SEM_DADO_GOLD * 2 \
             else "ATENÇÃO" if minutos > MAX_MINUTOS_SEM_DADO_GOLD \
             else "NORMAL"

    return {
        "check": "gold_frescor",
        "status": status,
        "mensagem": f"Gold processado há {minutos} min",
        "valor": minutos
    }


def checar_tanques_criticos(s3) -> dict:
    """Lê o Gold mais recente e conta tanques críticos."""
    obj = ultimo_objeto(s3, GOLD_BUCKET, GOLD_PREFIX)
    if obj is None:
        return {
            "check": "tanques_criticos",
            "status": "ATENÇÃO",
            "mensagem": "Gold não encontrado",
            "valor": None
        }

    df = ler_csv_s3(s3, GOLD_BUCKET, obj["Key"])
    if df is None or "overall_status" not in df.columns:
        return {
            "check": "tanques_criticos",
            "status": "ATENÇÃO",
            "mensagem": "Gold sem coluna overall_status",
            "valor": None
        }

    n_criticos = int((df["overall_status"] == "CRÍTICO").sum())
    n_atencao  = int((df["overall_status"] == "ATENÇÃO").sum())
    n_total    = len(df)

    status = "CRÍTICO" if n_criticos > 0 else "ATENÇÃO" if n_atencao > 0 else "NORMAL"

    detalhes = []
    if "ttc_hours" in df.columns and "alerta_preditivo" in df.columns:
        for _, row in df[df["overall_status"] == "CRÍTICO"].iterrows():
            detalhes.append(
                f"{row.get('platform_id','?')}/{row.get('tank_id','?')} "
                f"— {row.get('alerta_preditivo','')}"
            )

    return {
        "check": "tanques_criticos",
        "status": status,
        "mensagem": f"{n_criticos} CRÍTICO(s) · {n_atencao} ATENÇÃO · {n_total} total",
        "valor": n_criticos,
        "detalhes": detalhes
    }


# ─── Runner ──────────────────────────────────────────────────────

def executar_monitoramento() -> dict:
    s3 = s3_client()
    ts = datetime.utcnow().isoformat() + "Z"

    checks = [
        checar_frescor_bronze(s3),
        checar_taxa_rejeicao_silver(s3),
        checar_eventos_seguranca(s3),
        checar_frescor_gold(s3),
        checar_tanques_criticos(s3),
    ]

    # Status geral: pior de todos os checks
    ordem = {"CRÍTICO": 0, "ATENÇÃO": 1, "NORMAL": 2}
    status_geral = min(checks, key=lambda c: ordem[c["status"]])["status"]

    resultado = {
        "timestamp": ts,
        "status_geral": status_geral,
        "checks": checks
    }

    # Imprime relatório
    icones = {"CRÍTICO": "🔴", "ATENÇÃO": "🟡", "NORMAL": "🟢"}
    print(f"\n{'='*55}")
    print(f"  DeepWatch — Monitor de Pipeline  |  {ts}")
    print(f"  Status geral: {icones[status_geral]} {status_geral}")
    print(f"{'='*55}")
    for check in checks:
        icone = icones[check["status"]]
        print(f"  {icone} [{check['check']}] {check['mensagem']}")
        if check.get("detalhes") and isinstance(check["detalhes"], list):
            for det in check["detalhes"]:
                print(f"       → {det}")
    print(f"{'='*55}\n")

    return resultado


def main():
    resultado = executar_monitoramento()

    # Salva resultado em JSON local (pode ser enviado ao CloudWatch depois)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    with open(f"monitor_report_{ts}.json", "w") as f:
        json.dump(resultado, f, indent=2, default=str)

    # Exit code baseado no status (útil para cron e CI/CD)
    exit_codes = {"NORMAL": 0, "ATENÇÃO": 1, "CRÍTICO": 2}
    exit(exit_codes[resultado["status_geral"]])


if __name__ == "__main__":
    main()
