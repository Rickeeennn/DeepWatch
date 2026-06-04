"""
DeepWatch – bronze_to_silver_s3.py
ETL Bronze → Silver com merge de nivel + vazao e camada de segurança.

Os simuladores gravam arquivos separados:
  sensors/nivel/nivel_YYYYMMDD_HHMMSS.csv  →  colunas: timestamp, platform_id, tank_id, tank_level_percent
  sensors/vazao/vazao_YYYYMMDD_HHMMSS.csv  →  colunas: timestamp, platform_id, tank_id, flow_rate_m3_h

Este ETL:
  1. Carrega os dois conjuntos separadamente
  2. Faz merge pelo timestamp mais próximo (tolerância: 90s)
  3. Aplica validação física (segurança)
  4. Calcula desvio do balanço de massa
  5. Salva Silver no S3
"""

import boto3
import io
import logging
import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sensor_validator import (
    EstadoAnterior,
    calcular_balanco_massa,
    validar_leitura_completa,
)

# ─── Logs ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger          = logging.getLogger("deepwatch.bronze_to_silver")
security_logger = logging.getLogger("deepwatch.security")

# ─── Parâmetros ───────────────────────────────────────────────────
AWS_REGION      = os.getenv("AWS_REGION",      "us-east-1")
BRONZE_BUCKET   = os.getenv("BRONZE_BUCKET",   "deepwatch-stage-raw-dev")
SILVER_BUCKET   = os.getenv("SILVER_BUCKET",   "deepwatch-trusted-dev")
NIVEL_PREFIX    = os.getenv("NIVEL_PREFIX",    "sensors/nivel/")
VAZAO_PREFIX    = os.getenv("VAZAO_PREFIX",    "sensors/vazao/")
SILVER_PREFIX   = os.getenv("SILVER_PREFIX",   "silver/")
SECURITY_PREFIX = os.getenv("SECURITY_PREFIX", "security-events/")
TANK_CAPACITY_M3= float(os.getenv("TANK_CAPACITY_M3", "10000"))

# Tolerância do merge: arquivos de nivel e vazao gravados com até 90s de diferença
# são considerados do mesmo minuto operacional
MERGE_TOLERANCE = pd.Timedelta("90s")


# ─── S3 helpers ──────────────────────────────────────────────────

def get_s3():
    return boto3.client("s3", region_name=AWS_REGION)


def listar_csvs(s3, bucket: str, prefix: str) -> list:
    paginator = s3.get_paginator("list_objects_v2")
    keys = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                keys.append(obj["Key"])
    return keys


def ler_csv(s3, bucket: str, key: str) -> pd.DataFrame:
    resp = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(resp["Body"].read()))


def salvar_csv(s3, df: pd.DataFrame, bucket: str, prefix: str, nome: str) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    key = f"{prefix}{nome}"
    s3.put_object(
        Bucket=bucket, Key=key,
        Body=buf.getvalue().encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )
    logger.info(f"Salvo: s3://{bucket}/{key}")
    return key


def salvar_eventos(s3, eventos: list):
    if not eventos:
        return
    buf = io.StringIO()
    pd.DataFrame(eventos).to_csv(buf, index=False)
    ts  = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    key = f"{SECURITY_PREFIX}security_events_{ts}.csv"
    s3.put_object(
        Bucket=SILVER_BUCKET, Key=key,
        Body=buf.getvalue().encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )
    security_logger.warning(
        f"{len(eventos)} evento(s) de segurança → s3://{SILVER_BUCKET}/{key}"
    )


# ─── Carregamento e merge ─────────────────────────────────────────

def carregar_nivel(s3) -> pd.DataFrame:
    keys = listar_csvs(s3, BRONZE_BUCKET, NIVEL_PREFIX)
    if not keys:
        logger.warning("Nenhum arquivo de nível encontrado no Bronze.")
        return pd.DataFrame()
    dfs = [ler_csv(s3, BRONZE_BUCKET, k) for k in keys]
    df  = pd.concat(dfs, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    logger.info(f"Nível carregado: {len(df)} linhas de {len(keys)} arquivo(s)")
    return df


def carregar_vazao(s3) -> pd.DataFrame:
    keys = listar_csvs(s3, BRONZE_BUCKET, VAZAO_PREFIX)
    if not keys:
        logger.warning("Nenhum arquivo de vazão encontrado no Bronze.")
        return pd.DataFrame()
    dfs = [ler_csv(s3, BRONZE_BUCKET, k) for k in keys]
    df  = pd.concat(dfs, ignore_index=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    logger.info(f"Vazão carregada: {len(df)} linhas de {len(keys)} arquivo(s)")
    return df


def merge_nivel_vazao(df_nivel: pd.DataFrame, df_vazao: pd.DataFrame) -> pd.DataFrame:
    """
    Merge pelo timestamp mais próximo dentro da tolerância.

    Como os dois simuladores rodam independentemente, seus timestamps
    não são idênticos — podem ter alguns segundos de diferença.
    merge_asof une cada leitura de nível com a leitura de vazão mais
    próxima no tempo, desde que a diferença seja menor que MERGE_TOLERANCE.
    """
    if df_nivel.empty or df_vazao.empty:
        logger.warning("Um dos sensores não tem dados — merge não realizado.")
        return pd.DataFrame()

    # Ordena por timestamp (obrigatório para merge_asof)
    df_nivel = df_nivel.sort_values("timestamp").copy()
    df_vazao = df_vazao.sort_values("timestamp").copy()

    df = pd.merge_asof(
        df_nivel,
        df_vazao[["timestamp", "platform_id", "tank_id", "flow_rate_m3_h"]],
        on="timestamp",
        by=["platform_id", "tank_id"],
        tolerance=MERGE_TOLERANCE,
        direction="nearest",
        suffixes=("", "_vazao")
    )

    antes  = len(df)
    df     = df.dropna(subset=["flow_rate_m3_h"])
    perdas = antes - len(df)

    if perdas > 0:
        logger.warning(
            f"{perdas} leitura(s) de nível sem vazão correspondente "
            f"(diferença > {MERGE_TOLERANCE}) — descartadas."
        )

    logger.info(f"Merge concluído: {len(df)} linhas combinadas")
    return df.reset_index(drop=True)


# ─── Validação e limpeza ─────────────────────────────────────────

def limpar(df: pd.DataFrame) -> tuple:
    inicial = len(df)
    report  = {}

    df = df.drop_duplicates(subset=["timestamp", "platform_id", "tank_id"])
    report["duplicatas"] = inicial - len(df)

    for col in ["flow_rate_m3_h", "tank_level_percent"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    nulos = df[["flow_rate_m3_h", "tank_level_percent"]].isna().sum().sum()
    df    = df.dropna(subset=["flow_rate_m3_h", "tank_level_percent"])
    report["nulos"] = nulos

    fora = (
        (df["tank_level_percent"] < 0)  | (df["tank_level_percent"] > 100) |
        (df["flow_rate_m3_h"]    < 0)   | (df["flow_rate_m3_h"]    > 5000)
    )
    report["fora_de_faixa"] = int(fora.sum())
    df = df[~fora]

    report["apos_limpeza"] = len(df)
    return df, report


def validar_fisica(df: pd.DataFrame) -> tuple:
    """Detecta leituras fisicamente impossíveis — possível injeção de dados."""
    df      = df.sort_values(["platform_id", "tank_id", "timestamp"]).copy()
    estados = {}
    rejeitados   = []
    eventos_seg  = []

    for idx, row in df.iterrows():
        chave     = f"{row['platform_id']}_{row['tank_id']}"
        estado_ant= estados.get(chave)

        resultado = validar_leitura_completa(
            nivel    = float(row["tank_level_percent"]),
            vazao    = float(row["flow_rate_m3_h"]),
            timestamp= row["timestamp"].to_pydatetime(),
            estado_anterior=estado_ant
        )

        if not resultado.valida:
            rejeitados.append(idx)
            eventos_seg.append({
                "timestamp_evento":  datetime.utcnow().isoformat(),
                "timestamp_leitura": str(row["timestamp"]),
                "platform_id":       row["platform_id"],
                "tank_id":           row["tank_id"],
                "tipo_evento":       resultado.tipo_evento,
                "motivo":            resultado.motivo,
                "nivel":             row["tank_level_percent"],
                "vazao":             row["flow_rate_m3_h"],
            })
            security_logger.warning(
                f"[{resultado.tipo_evento}] {row['platform_id']}/{row['tank_id']} "
                f"— {resultado.motivo}"
            )
        else:
            estados[chave] = EstadoAnterior(
                nivel    = float(row["tank_level_percent"]),
                vazao    = float(row["flow_rate_m3_h"]),
                timestamp= row["timestamp"].to_pydatetime()
            )

    df_valido = df.drop(index=rejeitados)
    stats = {
        "rejeitados_fisica": len(rejeitados),
        "eventos_seguranca": len(eventos_seg)
    }
    return df_valido, eventos_seg, stats


def calcular_balanco(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["platform_id", "tank_id", "timestamp"]).copy()
    df["mass_balance_deviation_pct"] = 0.0

    for _, grupo in df.groupby(["platform_id", "tank_id"]):
        grupo         = grupo.sort_values("timestamp")
        delta_nivel   = grupo["tank_level_percent"].diff()
        delta_min     = grupo["timestamp"].diff().dt.total_seconds().div(60)
        vazao_entrada = grupo["flow_rate_m3_h"]

        desvios = []
        for i in range(len(grupo)):
            if i == 0 or pd.isna(delta_min.iloc[i]):
                desvios.append(0.0)
            else:
                desvios.append(calcular_balanco_massa(
                    delta_nivel_real    = float(delta_nivel.iloc[i]),
                    vazao_entrada       = float(vazao_entrada.iloc[i]),
                    vazao_saida         = 0.0,
                    capacidade_tanque_m3= TANK_CAPACITY_M3,
                    delta_minutos       = float(delta_min.iloc[i])
                ))
        df.loc[grupo.index, "mass_balance_deviation_pct"] = desvios

    return df


# ─── Main ─────────────────────────────────────────────────────────

def main():
    s3       = get_s3()
    ts_label = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    # 1. Carrega nivel e vazao separadamente
    df_nivel = carregar_nivel(s3)
    df_vazao = carregar_vazao(s3)

    if df_nivel.empty or df_vazao.empty:
        logger.warning("Dados insuficientes para processar. Encerrando.")
        return

    # 2. Merge pelo timestamp mais próximo
    df = merge_nivel_vazao(df_nivel, df_vazao)
    if df.empty:
        logger.warning("Merge resultou em DataFrame vazio. Encerrando.")
        return

    # 3. Limpeza básica
    df, r_limpeza = limpar(df)

    # 4. Validação física (segurança)
    df, eventos, r_seguranca = validar_fisica(df)

    # 5. Balanço de massa
    df = calcular_balanco(df)

    # 6. Normaliza e seleciona colunas Silver
    df["timestamp"]          = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df["platform_id"]        = df["platform_id"].str.strip().str.upper()
    df["tank_id"]            = df["tank_id"].str.strip().str.upper()
    df["flow_rate_m3_h"]     = df["flow_rate_m3_h"].round(4)
    df["tank_level_percent"] = df["tank_level_percent"].round(4)

    df_silver = df[[
        "timestamp", "platform_id", "tank_id",
        "flow_rate_m3_h", "tank_level_percent",
        "mass_balance_deviation_pct"
    ]].sort_values(["platform_id", "tank_id", "timestamp"])

    # 7. Salva Silver e eventos de segurança
    salvar_csv(s3, df_silver, SILVER_BUCKET, SILVER_PREFIX, f"silver_{ts_label}.csv")
    salvar_eventos(s3, eventos)

    # 8. Relatório
    print("\n=== Bronze → Silver ===")
    print(f"  Linhas nivel carregadas  : {len(df_nivel)}")
    print(f"  Linhas vazao carregadas  : {len(df_vazao)}")
    print(f"  Após merge               : {len(df_nivel)}")
    print(f"  Duplicatas removidas     : {r_limpeza['duplicatas']}")
    print(f"  Valores nulos            : {r_limpeza['nulos']}")
    print(f"  Fora de faixa            : {r_limpeza['fora_de_faixa']}")
    print(f"  Rejeitados (segurança)   : {r_seguranca['rejeitados_fisica']}")
    print(f"  Eventos de segurança     : {r_seguranca['eventos_seguranca']}")
    print(f"  Registros Silver finais  : {len(df_silver)}")
    print("=======================\n")


if __name__ == "__main__":
    main()
