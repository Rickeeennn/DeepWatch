"""
DeepWatch — ETL 2 Lambda: Trusted → Refined (S3)
=================================================
Versão da ETL2 adaptada para rodar como AWS Lambda.

Lê dados novos do bucket trusted (incrementalmente via offset),
agrega por janela de 1 minuto e salva métricas operacionais
no bucket refined com particionamento para Glue/Athena.

Offset salvo em:
  s3://<trusted_bucket>/.etl_state/offset_trusted.json

Estrutura de saída (particionada):
  s3://<refined_bucket>/platform_id=FPSO-01/tank_id=TK-01/refined.csv

Variáveis de ambiente (configuradas no Terraform):
  TRUSTED_BUCKET  — bucket de entrada  (ex: deepwatch-trusted-dev)
  REFINED_BUCKET  — bucket de saída    (ex: deepwatch-client-dev)
  AWS_REGION      — região             (ex: us-east-1)

Trigger: manual via console AWS Lambda ou AWS CLI.
"""

import os
import io
import json
import boto3
import math
import pandas as pd
import numpy as np
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO
# ==========================================

TRUSTED_BUCKET = os.environ["TRUSTED_BUCKET"]
REFINED_BUCKET = os.environ["REFINED_BUCKET"]
AWS_REGION     = os.environ.get("AWS_REGION", "us-east-1")
OFFSET_KEY     = ".etl_state/offset_trusted.json"

# Limiares de alerta
CRITICAL_LEVEL_PCT   = 90.0
ATTENTION_LEVEL_PCT  = 80.0
CRITICAL_TTC_HOURS   = 12.0
ATTENTION_TTC_HOURS  = 24.0

# Entupimento
PIPE_DEGRADED_DROP   = 0.20
PIPE_BLOCKED_DROP    = 0.65

# Vazamento
LEAK_LEVEL_DROP_PCT  = 0.05

# Balanço de massa
MASS_BALANCE_TOL     = 0.15

# Física do tanque
AREA_TANQUE_M2       = 700.0
NIVEL_MAXIMO_M       = 30.0

MAX_PIPES            = 5

# ==========================================
# S3 HELPERS
# ==========================================

def get_s3():
    return boto3.client("s3", region_name=AWS_REGION)

def s3_read_csv(s3, bucket, key, parse_dates=None):
    resp = s3.get_object(Bucket=bucket, Key=key)
    kwargs = dict(encoding="utf-8-sig", encoding_errors="replace")
    if parse_dates:
        kwargs["parse_dates"] = parse_dates
    return pd.read_csv(io.BytesIO(resp["Body"].read()), **kwargs)

def s3_write_csv(s3, bucket, key, df):
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue().encode("utf-8-sig"),
        ContentType="text/csv",
    )

def s3_list_keys(s3, bucket, prefix=""):
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            keys.append(obj["Key"])
    return keys

def s3_read_json(s3, bucket, key):
    try:
        resp = s3.get_object(Bucket=bucket, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except Exception:
        return {}

def s3_write_json(s3, bucket, key, data):
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

# ==========================================
# DESCOBERTA DE ARQUIVOS TRUSTED
# ==========================================

def discover_trusted(s3):
    """
    Lista o bucket trusted e retorna:
    [ {platform_id, tank_id, key} ]
    """
    files = []
    for key in s3_list_keys(s3, TRUSTED_BUCKET):
        if not key.endswith(".csv") or key.startswith(".etl_state"):
            continue
        parts = key.split("/")
        if len(parts) != 2:
            continue
        platform_id = parts[0]
        tank_id     = parts[1].replace(".csv", "")
        files.append({"platform_id": platform_id,
                      "tank_id": tank_id,
                      "key": key})
    return sorted(files, key=lambda x: x["key"])

# ==========================================
# LEITURA INCREMENTAL
# ==========================================

def read_new_rows(s3, key, offset):
    rows_done = offset.get(key, 0)
    df = s3_read_csv(s3, TRUSTED_BUCKET, key, parse_dates=["timestamp"])
    total = len(df)
    if total <= rows_done:
        return None, rows_done
    return df.iloc[rows_done:].copy(), total

# ==========================================
# SEPARAÇÃO NIVEL / VAZÃO DO SCHEMA WIDE
# ==========================================

def extract_nivel(df):
    """Extrai colunas de nível do schema wide."""
    cols = ["timestamp", "platform_id", "tank_id", "side",
            "tank_level_percent", "tank_status"]
    return df[[c for c in cols if c in df.columns]].copy()

def extract_pipes(df):
    """
    Reconstrói um DataFrame longo de vazão a partir do schema wide.
    Retorna DataFrame com colunas: timestamp, pipe_id, pipe_type,
    flow_rate_m3_h, sensor_status
    """
    rows = []
    for i in range(1, MAX_PIPES + 1):
        pt  = f"p{i}_pipe_type"
        fl  = f"p{i}_flow_rate_m3_h"
        st  = f"p{i}_status"
        if pt not in df.columns:
            continue
        sub = df[df[pt] != "EMPTY"][["timestamp", pt, fl, st]].copy()
        if sub.empty:
            continue
        sub = sub.rename(columns={pt: "pipe_type",
                                   fl: "flow_rate_m3_h",
                                   st: "sensor_status"})
        sub["pipe_id"] = f"PIPE-IN-{i:02d}"
        rows.append(sub)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)

# ==========================================
# BASELINE DOS CANOS (histórico completo)
# ==========================================

def compute_pipe_baselines(s3, platform_id, tank_id):
    key = f"{platform_id}/{tank_id}.csv"
    try:
        df = s3_read_csv(s3, TRUSTED_BUCKET, key, parse_dates=["timestamp"])
    except Exception:
        return {}

    df_pipes = extract_pipes(df)
    if df_pipes.empty:
        return {}

    df_pipes["flow_rate_m3_h"] = pd.to_numeric(
        df_pipes["flow_rate_m3_h"], errors="coerce")

    baselines = {}
    for pipe_id, group in df_pipes.groupby("pipe_id"):
        group   = group.sort_values("timestamp")
        q1_len  = max(1, len(group) // 4)
        baselines[pipe_id] = group.head(q1_len)["flow_rate_m3_h"].mean()
    return baselines

# ==========================================
# AGREGAÇÃO POR MINUTO
# ==========================================

def aggregate_nivel(df_nivel):
    if df_nivel.empty:
        return pd.DataFrame()
    df = df_nivel.copy()
    df["minute"] = df["timestamp"].dt.floor("min")
    agg = df.groupby("minute").agg(
        avg_level  = ("tank_level_percent", "mean"),
        min_level  = ("tank_level_percent", "min"),
        max_level  = ("tank_level_percent", "max"),
        side       = ("side", "first"),
        n_readings = ("tank_level_percent", "count"),
    ).reset_index()
    agg["avg_level"] = agg["avg_level"].round(4)
    agg["min_level"] = agg["min_level"].round(4)
    agg["max_level"] = agg["max_level"].round(4)
    return agg

def aggregate_pipes(df_pipes):
    if df_pipes.empty:
        return pd.DataFrame(), pd.DataFrame()
    df = df_pipes.copy()
    df["minute"] = df["timestamp"].dt.floor("min")
    df_per_pipe = df.groupby(["minute", "pipe_id"]).agg(
        avg_flow_pipe = ("flow_rate_m3_h", "mean"),
        pipe_type     = ("pipe_type", "first"),
        sensor_status = ("sensor_status", lambda x: x.mode()[0]),
    ).reset_index()
    df_per_pipe["avg_flow_pipe"] = df_per_pipe["avg_flow_pipe"].round(4)

    entradas = df_per_pipe[df_per_pipe["pipe_type"] == "ENTRADA"]
    df_total = entradas.groupby("minute").agg(
        flow_total_m3_h = ("avg_flow_pipe", "sum"),
        active_pipes    = ("pipe_id", "count"),
    ).reset_index()
    df_total["flow_total_m3_h"] = df_total["flow_total_m3_h"].round(4)
    return df_per_pipe, df_total

# ==========================================
# MÉTRICAS OPERACIONAIS
# ==========================================

def compute_ttc(nivel_agg):
    if len(nivel_agg) < 2:
        return [None] * len(nivel_agg)
    df = nivel_agg.sort_values("minute").copy()
    df["delta_min"]    = df["minute"].diff().dt.total_seconds() / 60.0
    df["delta_level"]  = df["avg_level"].diff()
    df["rate_per_min"] = df["delta_level"] / df["delta_min"]
    df["rate_smooth"]  = df["rate_per_min"].rolling(5, min_periods=1).median()

    def ttc_row(row):
        rate = row["rate_smooth"]
        if pd.isna(rate) or rate <= 0:
            return None
        return round((100.0 - row["avg_level"]) / rate / 60.0, 2)

    return df.apply(ttc_row, axis=1).tolist()

def classify_tank_status(level, ttc_hours):
    if level >= CRITICAL_LEVEL_PCT:
        return "CRÍTICO"
    if ttc_hours is not None and ttc_hours < CRITICAL_TTC_HOURS:
        return "CRÍTICO"
    if level >= ATTENTION_LEVEL_PCT:
        return "ATENÇÃO"
    if ttc_hours is not None and ttc_hours < ATTENTION_TTC_HOURS:
        return "ATENÇÃO"
    return "NORMAL"

def classify_pipe_status(avg_flow, baseline):
    if baseline is None or baseline <= 0:
        return "NORMAL"
    drop = (baseline - avg_flow) / baseline
    if drop >= PIPE_BLOCKED_DROP:
        return "ENTUPIDO"
    if drop >= PIPE_DEGRADED_DROP:
        return "DEGRADADO"
    return "NORMAL"

def detect_leak(nivel_agg, flow_total_agg):
    if nivel_agg.empty or flow_total_agg.empty:
        return [False] * len(nivel_agg)
    df = nivel_agg.sort_values("minute").copy()
    df["delta_level"] = df["avg_level"].diff()
    df = df.merge(flow_total_agg[["minute", "flow_total_m3_h"]],
                  on="minute", how="left")
    df["flow_total_m3_h"] = df["flow_total_m3_h"].fillna(0)
    leak = ((df["delta_level"] < -LEAK_LEVEL_DROP_PCT) &
            (df["flow_total_m3_h"] == 0))
    return leak.tolist()

def compute_mass_balance(nivel_agg, flow_total_agg):
    if nivel_agg.empty or flow_total_agg.empty:
        return ["OK"] * len(nivel_agg)
    df = nivel_agg.sort_values("minute").copy()
    df["delta_level_pct"]    = df["avg_level"].diff()
    df["delta_vol_real"]     = (df["delta_level_pct"] / 100.0) * \
                                NIVEL_MAXIMO_M * AREA_TANQUE_M2
    df = df.merge(flow_total_agg[["minute", "flow_total_m3_h"]],
                  on="minute", how="left")
    df["flow_total_m3_h"]    = df["flow_total_m3_h"].fillna(0)
    df["delta_vol_esperado"] = df["flow_total_m3_h"] / 60.0

    def flag(row):
        if pd.isna(row["delta_vol_real"]) or row["delta_vol_esperado"] == 0:
            return "OK"
        div = abs(row["delta_vol_esperado"] - row["delta_vol_real"]) / \
              (abs(row["delta_vol_esperado"]) + 1e-9)
        return "DIVERGENTE" if div > MASS_BALANCE_TOL else "OK"

    return df.apply(flag, axis=1).tolist()

# ==========================================
# CONSTRUÇÃO DO REFINED
# ==========================================

def build_refined(platform_id, tank_id, df_new, pipe_baselines):
    df_nivel = extract_nivel(df_new)
    df_pipes = extract_pipes(df_new)

    nivel_agg            = aggregate_nivel(df_nivel)
    df_per_pipe, flow_agg = aggregate_pipes(df_pipes)

    if nivel_agg.empty:
        return pd.DataFrame()

    nivel_agg["ttc_hours"]    = compute_ttc(nivel_agg)
    nivel_agg["leak_flag"]    = detect_leak(nivel_agg, flow_agg)
    nivel_agg["mass_balance"] = compute_mass_balance(nivel_agg, flow_agg)

    if not flow_agg.empty:
        nivel_agg = nivel_agg.merge(
            flow_agg[["minute", "flow_total_m3_h", "active_pipes"]],
            on="minute", how="left"
        )
    else:
        nivel_agg["flow_total_m3_h"] = None
        nivel_agg["active_pipes"]    = 0

    nivel_agg["tank_status"] = nivel_agg.apply(
        lambda r: classify_tank_status(r["avg_level"], r["ttc_hours"]),
        axis=1
    )

    pipe_status_by_minute = {}
    if not df_per_pipe.empty:
        for _, row in df_per_pipe.iterrows():
            minute  = row["minute"]
            pipe_id = row["pipe_id"]
            status  = classify_pipe_status(
                row["avg_flow_pipe"], pipe_baselines.get(pipe_id))
            pipe_status_by_minute.setdefault(minute, {})[pipe_id] = status

    nivel_agg["pipe_statuses"] = nivel_agg["minute"].apply(
        lambda m: json.dumps(
            pipe_status_by_minute.get(m, {}), ensure_ascii=False))

    def worst_pipe(s):
        v = list(json.loads(s).values())
        if "ENTUPIDO"  in v: return "ENTUPIDO"
        if "DEGRADADO" in v: return "DEGRADADO"
        return "NORMAL"

    nivel_agg["worst_pipe_status"] = nivel_agg["pipe_statuses"].apply(worst_pipe)

    def overall(row):
        if row["tank_status"] == "CRÍTICO":           return "CRÍTICO"
        if row["leak_flag"]:                           return "CRÍTICO"
        if row["mass_balance"] == "DIVERGENTE":        return "CRÍTICO"
        if row["tank_status"] == "ATENÇÃO":            return "ATENÇÃO"
        if row["worst_pipe_status"] in ("ENTUPIDO", "DEGRADADO"): return "ATENÇÃO"
        return "NORMAL"

    nivel_agg["overall_status"] = nivel_agg.apply(overall, axis=1)

    records = nivel_agg.rename(columns={"minute": "window_start"}).copy()
    records["platform_id"] = platform_id
    records["tank_id"]     = tank_id

    out_cols = [
        "window_start", "platform_id", "tank_id", "side",
        "avg_level", "min_level", "max_level", "ttc_hours",
        "flow_total_m3_h", "active_pipes", "pipe_statuses",
        "worst_pipe_status", "tank_status", "leak_flag",
        "mass_balance", "overall_status", "n_readings",
    ]
    return records[[c for c in out_cols if c in records.columns]]

# ==========================================
# PERSISTÊNCIA NO REFINED (S3)
# ==========================================

def save_refined(s3, platform_id, tank_id, df):
    """
    Faz append no CSV refined com particionamento Glue/Athena.
    Chave: platform_id=FPSO-01/tank_id=TK-01/refined.csv
    """
    key = f"platform_id={platform_id}/tank_id={tank_id}/refined.csv"

    try:
        existing = s3_read_csv(s3, REFINED_BUCKET, key,
                               parse_dates=["window_start"])
        df["window_start"] = df["window_start"].astype(str)
        combined = pd.concat([existing, df], ignore_index=True)
    except Exception:
        df["window_start"] = df["window_start"].astype(str)
        combined = df

    s3_write_csv(s3, REFINED_BUCKET, key, combined)

# ==========================================
# HANDLER LAMBDA
# ==========================================

def lambda_handler(event, context):
    print("=" * 55)
    print(" DeepWatch — ETL2 Lambda: Trusted → Refined")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    s3     = get_s3()
    offset = s3_read_json(s3, TRUSTED_BUCKET, OFFSET_KEY)
    files  = discover_trusted(s3)

    if not files:
        print("[AVISO] Nenhum arquivo encontrado no bucket trusted.")
        return {"status": "ok", "tanks_updated": 0}

    total_windows  = 0
    tanks_updated  = 0
    status_summary = {"CRÍTICO": 0, "ATENÇÃO": 0, "NORMAL": 0}

    for file_info in files:
        platform_id = file_info["platform_id"]
        tank_id     = file_info["tank_id"]
        key         = file_info["key"]

        df_new, new_offset = read_new_rows(s3, key, offset)
        if df_new is None or len(df_new) == 0:
            continue

        pipe_baselines = compute_pipe_baselines(s3, platform_id, tank_id)
        df_refined     = build_refined(platform_id, tank_id,
                                       df_new, pipe_baselines)

        if df_refined.empty:
            offset[key] = new_offset
            continue

        save_refined(s3, platform_id, tank_id, df_refined)
        offset[key] = new_offset

        n = len(df_refined)
        total_windows += n
        tanks_updated += 1

        for status in df_refined["overall_status"]:
            if status in status_summary:
                status_summary[status] += 1

        last    = df_refined.iloc[-1]
        ttc_str = (f"{last['ttc_hours']:.1f}h"
                   if pd.notna(last.get("ttc_hours")) else "N/A")
        print(f"  {platform_id}/{tank_id} — {n} janelas | "
              f"nível: {last['avg_level']:.1f}% | "
              f"TTC: {ttc_str} | status: {last['overall_status']}")

    s3_write_json(s3, TRUSTED_BUCKET, OFFSET_KEY, offset)

    result = {
        "status":        "ok",
        "tanks_updated": tanks_updated,
        "windows":       total_windows,
        "CRÍTICO":       status_summary["CRÍTICO"],
        "ATENÇÃO":       status_summary["ATENÇÃO"],
        "NORMAL":        status_summary["NORMAL"],
        "timestamp":     datetime.now().isoformat(),
    }
    print(f"\n  Tanques atualizados: {tanks_updated}")
    print(f"  Janelas geradas    : {total_windows}")
    print(f"  🔴 CRÍTICO: {status_summary['CRÍTICO']} "
          f"🟡 ATENÇÃO: {status_summary['ATENÇÃO']} "
          f"🟢 NORMAL: {status_summary['NORMAL']}")
    print("=" * 55)
    return result
