"""
DeepWatch – silver_to_gold_s3.py
ETL Silver → Gold com insights preditivos e preventivos.

Baseado no silver_to_gold.py existente, adiciona:
  1. Leitura/escrita no S3
  2. TTC calculado com regressão linear sobre histórico real de cada tanque
     (mais robusto que taxa instantânea — usa sensor de nível + sensor de vazão)
  3. Desvio do balanço de massa agregado por tanque
  4. Score de criticidade composto (TTC + desvio de balanço)
  5. Alertas preditivos antecipados
"""

import boto3
import io
import logging
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("deepwatch.silver_to_gold")

# ─── Parâmetros ───────────────────────────────────────────────────
AWS_REGION    = os.getenv("AWS_REGION", "us-east-1")
SILVER_BUCKET = os.getenv("SILVER_BUCKET", "deepwatch-trusted-dev")
GOLD_BUCKET   = os.getenv("GOLD_BUCKET",   "deepwatch-client-dev")
SILVER_PREFIX = os.getenv("SILVER_PREFIX", "silver/")
GOLD_PREFIX   = os.getenv("GOLD_PREFIX",   "gold/")

TANK_CAPACITY_M3     = float(os.getenv("TANK_CAPACITY_M3", "10000"))
CRITICAL_LEVEL       = 90.0    # % — acima disso é crítico por nível
ATTENTION_LEVEL      = 75.0    # %
CRITICAL_TTC_HOURS   = 10.0    # horas — TTC abaixo disso é crítico
ATTENTION_TTC_HOURS  = 30.0    # horas
CRITICAL_BALANCE_DEV = 2.0     # % — desvio balanço crítico
ATTENTION_BALANCE_DEV= 1.0     # %


# ─── S3 helpers ──────────────────────────────────────────────────

def get_s3_client():
    return boto3.client("s3", region_name=AWS_REGION)


def listar_arquivos_silver(s3) -> list:
    paginator = s3.get_paginator("list_objects_v2")
    arquivos  = []
    for page in paginator.paginate(Bucket=SILVER_BUCKET, Prefix=SILVER_PREFIX):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".csv"):
                arquivos.append(obj["Key"])
    logger.info(f"Encontrados {len(arquivos)} arquivo(s) Silver")
    return arquivos


def ler_csv_s3(s3, bucket, key) -> pd.DataFrame:
    response = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(io.BytesIO(response["Body"].read()), parse_dates=["timestamp"])


def salvar_csv_s3(s3, df: pd.DataFrame, bucket: str, prefix: str, nome: str) -> str:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False)
    key = f"{prefix}{nome}"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buffer.getvalue().encode("utf-8"),
        ContentType="text/csv",
        ServerSideEncryption="AES256"
    )
    logger.info(f"Gold salvo: s3://{bucket}/{key}")
    return key


# ─── Cálculos preditivos ─────────────────────────────────────────

def estimar_ttc_regressao(grupo: pd.DataFrame) -> tuple:
    """
    Estima o TTC (horas) usando regressão linear sobre o histórico.
    Mais robusto que taxa instantânea porque suaviza picos de vazão.

    Usa os DOIS sensores:
      - Sensor de nível: série histórica de tank_level_percent
      - Sensor de vazão: usado para validar a taxa calculada

    Retorna: (ttc_horas, taxa_pct_hora, confianca)
    """
    grupo = grupo.sort_values("timestamp").copy()
    if len(grupo) < 3:
        return None, None, "baixa"

    # Eixo X: minutos desde a primeira leitura
    t0 = grupo["timestamp"].iloc[0]
    grupo["minutos"] = (grupo["timestamp"] - t0).dt.total_seconds() / 60

    # Regressão linear: nível ~ tempo
    x = grupo["minutos"].values
    y = grupo["tank_level_percent"].values
    coef = np.polyfit(x, y, 1)          # coef[0] = taxa (%/min), coef[1] = intercepto

    taxa_pct_min  = coef[0]
    taxa_pct_hora = taxa_pct_min * 60
    nivel_atual   = grupo["tank_level_percent"].iloc[-1]

    # Valida taxa contra a vazão média real (sensor de vazão)
    if "flow_rate_m3_h" in grupo.columns:
        vazao_media       = grupo["flow_rate_m3_h"].mean()
        taxa_por_vazao    = (vazao_media / TANK_CAPACITY_M3) * 100    # %/h
        razao_validacao   = abs(taxa_pct_hora / taxa_por_vazao) if taxa_por_vazao > 0 else 0
        # Se a taxa calculada difere muito da esperada pela vazão → baixa confiança
        confianca = "alta" if 0.5 <= razao_validacao <= 1.5 else "media"
    else:
        confianca = "media"

    if taxa_pct_min <= 0:
        return None, round(taxa_pct_hora, 4), confianca   # nível estável ou caindo

    restante = 100.0 - nivel_atual
    ttc_min  = restante / taxa_pct_min
    ttc_horas = round(ttc_min / 60, 2)

    return ttc_horas, round(taxa_pct_hora, 4), confianca


def status_por_ttc(ttc_horas) -> str:
    if ttc_horas is None:
        return "NORMAL"
    if ttc_horas < CRITICAL_TTC_HOURS:
        return "CRÍTICO"
    if ttc_horas < ATTENTION_TTC_HOURS:
        return "ATENÇÃO"
    return "NORMAL"


def status_por_nivel(nivel: float) -> str:
    if nivel >= CRITICAL_LEVEL:
        return "CRÍTICO"
    if nivel >= ATTENTION_LEVEL:
        return "ATENÇÃO"
    return "NORMAL"


def status_por_balanco(desvio: float) -> str:
    if desvio >= CRITICAL_BALANCE_DEV:
        return "CRÍTICO"
    if desvio >= ATTENTION_BALANCE_DEV:
        return "ATENÇÃO"
    return "NORMAL"


def alerta_preditivo(ttc_horas, nivel_atual: float, desvio_balanco: float) -> str:
    """
    Gera alerta preditivo baseado na combinação dos três indicadores.
    Insight preventivo: avisa ANTES do problema ocorrer.
    """
    alertas = []

    if ttc_horas is not None:
        if ttc_horas < 6:
            alertas.append(f"SHUT-IN IMINENTE: {ttc_horas:.1f}h para 100%")
        elif ttc_horas < CRITICAL_TTC_HOURS:
            alertas.append(f"TTC CRÍTICO: tanque cheia em {ttc_horas:.1f}h")
        elif ttc_horas < ATTENTION_TTC_HOURS:
            alertas.append(f"TTC atenção: {ttc_horas:.1f}h")

    if desvio_balanco >= CRITICAL_BALANCE_DEV:
        alertas.append(f"INCONSISTÊNCIA: desvio balanço {desvio_balanco:.1f}% (possível vazamento)")
    elif desvio_balanco >= ATTENTION_BALANCE_DEV:
        alertas.append(f"Balanço de massa: {desvio_balanco:.1f}% acima da tolerância")

    return " | ".join(alertas) if alertas else "OK"


def eficiencia_transferencia(grupo: pd.DataFrame) -> tuple:
    """Reutiliza lógica do silver_to_gold.py original."""
    grupo = grupo.sort_values("timestamp").copy()
    if len(grupo) < 2:
        return None, "NORMAL"
    flow_std = round(grupo["flow_rate_m3_h"].std(), 4)
    grupo["flow_rolling"] = grupo["flow_rate_m3_h"].rolling(window=5, min_periods=1).mean()
    last_flow = grupo["flow_rolling"].iloc[-1]
    avg_flow  = grupo["flow_rate_m3_h"].mean()
    flag = "ATENÇÃO" if (avg_flow > 0 and (avg_flow - last_flow) / avg_flow >= 0.3) else "NORMAL"
    return flow_std, flag


# ─── Build Gold ──────────────────────────────────────────────────

def build_gold(df: pd.DataFrame) -> pd.DataFrame:
    registros = []

    for (platform_id, tank_id), grupo in df.groupby(["platform_id", "tank_id"]):
        grupo  = grupo.sort_values("timestamp")
        ultimo = grupo.iloc[-1]
        primeiro = grupo.iloc[0]

        nivel_atual  = float(ultimo["tank_level_percent"])
        vazao_atual  = float(ultimo["flow_rate_m3_h"])
        nivel_medio  = round(float(grupo["tank_level_percent"].mean()), 4)
        vazao_media  = round(float(grupo["flow_rate_m3_h"].mean()), 4)
        nivel_max    = round(float(grupo["tank_level_percent"].max()), 4)
        nivel_min    = round(float(grupo["tank_level_percent"].min()), 4)

        # TTC por regressão (usa nível + vazão)
        ttc_horas, taxa_pct_hora, confianca_ttc = estimar_ttc_regressao(grupo)

        # Desvio médio do balanço de massa (calculado na Silver)
        desvio_balanco_medio = 0.0
        desvio_balanco_max   = 0.0
        if "mass_balance_deviation_pct" in grupo.columns:
            desvio_balanco_medio = round(float(grupo["mass_balance_deviation_pct"].mean()), 4)
            desvio_balanco_max   = round(float(grupo["mass_balance_deviation_pct"].max()), 4)

        # Eficiência de transferência
        flow_std, eficiencia_status = eficiencia_transferencia(grupo)

        # Status individual
        s_nivel   = status_por_nivel(nivel_atual)
        s_ttc     = status_por_ttc(ttc_horas)
        s_balanco = status_por_balanco(desvio_balanco_medio)

        # Status global: pior dos três
        prioridade = {"CRÍTICO": 0, "ATENÇÃO": 1, "NORMAL": 2}
        status_global = min([s_nivel, s_ttc, s_balanco],
                            key=lambda s: prioridade[s])

        # Alerta preditivo
        alerta = alerta_preditivo(ttc_horas, nivel_atual, desvio_balanco_medio)

        registros.append({
            "platform_id":                platform_id,
            "tank_id":                    tank_id,
            "observation_start":          primeiro["timestamp"].strftime("%Y-%m-%dT%H:%M:%S"),
            "observation_end":            ultimo["timestamp"].strftime("%Y-%m-%dT%H:%M:%S"),
            "total_readings":             len(grupo),
            # ── Nível (sensor de nível) ──────────────────────────
            "current_level_percent":      round(nivel_atual, 4),
            "avg_level_percent":          nivel_medio,
            "max_level_percent":          nivel_max,
            "min_level_percent":          nivel_min,
            "level_fill_rate_pct_h":      taxa_pct_hora,
            # ── Vazão (sensor de vazão) ──────────────────────────
            "current_flow_m3_h":          round(vazao_atual, 4),
            "avg_flow_m3_h":              vazao_media,
            "flow_std":                   flow_std,
            # ── TTC (nível + vazão combinados) ───────────────────
            "ttc_hours":                  ttc_horas,
            "ttc_confidence":             confianca_ttc,
            # ── Balanço de massa (nível + vazão) ─────────────────
            "mass_balance_deviation_avg_pct": desvio_balanco_medio,
            "mass_balance_deviation_max_pct": desvio_balanco_max,
            # ── Status e alertas ─────────────────────────────────
            "status_nivel":               s_nivel,
            "status_ttc":                 s_ttc,
            "status_balanco_massa":       s_balanco,
            "transfer_efficiency_status": eficiencia_status,
            "overall_status":             status_global,
            "alerta_preditivo":           alerta,
            "processed_at":               datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    df_gold = pd.DataFrame(registros)

    # Ordena por criticidade
    ordem = {"CRÍTICO": 0, "ATENÇÃO": 1, "NORMAL": 2}
    df_gold["_sort"] = df_gold["overall_status"].map(ordem)
    df_gold = df_gold.sort_values(["_sort", "ttc_hours"], na_position="last")
    df_gold = df_gold.drop(columns=["_sort"])

    return df_gold


# ─── Main ─────────────────────────────────────────────────────────

def main():
    s3 = get_s3_client()
    ts_label = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    arquivos = listar_arquivos_silver(s3)
    if not arquivos:
        logger.warning("Nenhum arquivo Silver encontrado.")
        return

    dfs = [ler_csv_s3(s3, SILVER_BUCKET, key) for key in arquivos]
    df  = pd.concat(dfs, ignore_index=True)
    logger.info(f"Silver carregado: {len(df)} linhas")

    df_gold = build_gold(df)
    salvar_csv_s3(s3, df_gold, GOLD_BUCKET, GOLD_PREFIX, f"gold_{ts_label}.csv")

    # Relatório
    print("\n=== Relatório Silver → Gold ===")
    print(f"  Tanques processados: {len(df_gold)}")
    for status, count in df_gold["overall_status"].value_counts().items():
        print(f"  {status}: {count} tanque(s)")

    criticos = df_gold[df_gold["overall_status"] == "CRÍTICO"]
    if not criticos.empty:
        print("\n  ⚠ Tanques críticos:")
        for _, row in criticos.iterrows():
            ttc = f"{row['ttc_hours']}h" if pd.notna(row["ttc_hours"]) else "N/A"
            bal = row["mass_balance_deviation_avg_pct"]
            print(f"    [{row['platform_id']}] {row['tank_id']} "
                  f"— nível: {row['current_level_percent']}% "
                  f"— TTC: {ttc} "
                  f"— balanço: {bal:.1f}%")
            if row["alerta_preditivo"] != "OK":
                print(f"    → {row['alerta_preditivo']}")
    print("================================\n")


if __name__ == "__main__":
    main()
