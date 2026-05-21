"""
DeepWatch — ETL 1 Lambda: Raw → Trusted (S3)
=============================================
Versão da ETL1 adaptada para rodar como AWS Lambda.

Lê CSVs novos do bucket raw (incrementalmente via offset),
valida, limpa e salva no bucket trusted em schema wide:
uma linha por timestamp com colunas fixas p1..p5.

Offset salvo em:
  s3://<raw_bucket>/.etl_state/offset_raw.json

Variáveis de ambiente (configuradas no Terraform):
  RAW_BUCKET      — bucket de entrada  (ex: deepwatch-stage-raw-dev)
  TRUSTED_BUCKET  — bucket de saída    (ex: deepwatch-trusted-dev)
  AWS_REGION      — região             (ex: us-east-1)

Trigger: manual via console AWS Lambda ou AWS CLI.
"""

import os
import io
import json
import boto3
import pandas as pd
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO
# ==========================================

RAW_BUCKET     = os.environ["RAW_BUCKET"]
TRUSTED_BUCKET = os.environ["TRUSTED_BUCKET"]
AWS_REGION     = os.environ.get("AWS_REGION", "us-east-1")
OFFSET_KEY     = ".etl_state/offset_raw.json"

MAX_PIPES      = 5
EMPTY_STATUS   = "EMPTY"
FLOW_RATE_MIN  = 0.0
FLOW_RATE_MAX  = 5000.0
TANK_LEVEL_MIN = 0.0
TANK_LEVEL_MAX = 100.0

COLS_NIVEL = {"timestamp", "platform_id", "tank_id", "side",
              "tank_level_percent", "status"}
COLS_VAZAO = {"timestamp", "platform_id", "tank_id", "pipe_id",
              "pipe_type", "flow_rate_m3_h", "status"}

OUTPUT_COLS = (
    ["timestamp", "platform_id", "tank_id", "side",
     "tank_level_percent", "tank_status"] +
    [col
     for i in range(1, MAX_PIPES + 1)
     for col in (f"p{i}_pipe_type", f"p{i}_flow_rate_m3_h", f"p{i}_status")]
)

# ==========================================
# S3 HELPERS
# ==========================================

def get_s3():
    return boto3.client("s3", region_name=AWS_REGION)

def s3_read_csv(s3, bucket, key):
    """Lê um CSV do S3 e retorna DataFrame."""
    resp = s3.get_object(Bucket=bucket, Key=key)
    return pd.read_csv(
        io.BytesIO(resp["Body"].read()),
        encoding="utf-8-sig",
        encoding_errors="replace",
    )

def s3_write_csv(s3, bucket, key, df):
    """Escreve DataFrame como CSV no S3."""
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=buf.getvalue().encode("utf-8-sig"),
        ContentType="text/csv",
    )

def s3_list_keys(s3, bucket, prefix=""):
    """Lista todas as chaves no bucket com prefixo dado."""
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
    except s3.exceptions.NoSuchKey:
        return {}
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
# DESCOBERTA DE TANQUES NO S3
# ==========================================

def discover_tanks(s3):
    """
    Lista o bucket raw e agrupa chaves por (platform_id, tank_id).
    Retorna: { (platform_id, tank_id): {"nivel": key, "pipes": [(filename, key)]} }
    """
    all_keys = [
        k for k in s3_list_keys(s3, RAW_BUCKET)
        if k.endswith(".csv") and not k.startswith(".etl_state")
    ]

    tanks = {}
    for key in sorted(all_keys):
        # Formato esperado: FPSO-01/TK-01/nivel.csv
        parts = key.split("/")
        if len(parts) != 3:
            continue
        platform_id, tank_id, filename = parts
        tk = (platform_id, tank_id)
        if tk not in tanks:
            tanks[tk] = {"nivel": None, "pipes": []}
        if filename == "nivel.csv":
            tanks[tk]["nivel"] = key
        elif filename.endswith(".csv"):
            tanks[tk]["pipes"].append((filename, key))

    # Ordena pipes por nome
    for tk in tanks:
        tanks[tk]["pipes"].sort(key=lambda x: x[0])

    return tanks

# ==========================================
# LEITURA INCREMENTAL VIA OFFSET
# ==========================================

def read_new_rows(s3, key, offset):
    """Lê só as linhas novas do CSV baseado no offset registrado."""
    rows_done = offset.get(key, 0)

    df = s3_read_csv(s3, RAW_BUCKET, key)
    total_rows = len(df)

    if total_rows <= rows_done:
        return None, rows_done

    df_new = df.iloc[rows_done:]
    return df_new, total_rows

# ==========================================
# VALIDAÇÃO E LIMPEZA
# ==========================================

def clean_nivel(df):
    missing = COLS_NIVEL - set(df.columns)
    if missing:
        return None

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["tank_level_percent"] = pd.to_numeric(
        df["tank_level_percent"], errors="coerce")
    df = df.dropna(subset=["tank_level_percent"])

    mask = ((df["tank_level_percent"] < TANK_LEVEL_MIN) |
            (df["tank_level_percent"] > TANK_LEVEL_MAX))
    df = df[~mask]
    df = df.drop_duplicates(subset=["timestamp", "platform_id", "tank_id"])
    df["timestamp"] = df["timestamp"].dt.floor("s")
    return df

def clean_vazao(df):
    missing = COLS_VAZAO - set(df.columns)
    if missing:
        return None

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"])
    df["flow_rate_m3_h"] = pd.to_numeric(
        df["flow_rate_m3_h"], errors="coerce")
    df = df.dropna(subset=["flow_rate_m3_h"])

    mask = ((df["flow_rate_m3_h"] < FLOW_RATE_MIN) |
            (df["flow_rate_m3_h"] > FLOW_RATE_MAX))
    df = df[~mask]
    df = df.drop_duplicates(
        subset=["timestamp", "platform_id", "tank_id", "pipe_id"])
    df["timestamp"] = df["timestamp"].dt.floor("s")
    return df

# ==========================================
# UNIFICAÇÃO EM SCHEMA WIDE
# ==========================================

def build_wide_rows(df_nivel, pipe_dfs):
    if df_nivel is None or df_nivel.empty:
        return pd.DataFrame()

    base = df_nivel[["timestamp", "platform_id", "tank_id", "side",
                      "tank_level_percent", "status"]].copy()
    base = base.rename(columns={"status": "tank_status"})
    base["timestamp"]          = pd.to_datetime(base["timestamp"])
    base["platform_id"]        = base["platform_id"].astype(str).str.strip().str.upper()
    base["tank_id"]            = base["tank_id"].astype(str).str.strip().str.upper()
    base["tank_level_percent"] = base["tank_level_percent"].round(4)

    for idx, df_pipe in enumerate(pipe_dfs):
        col_num = idx + 1
        if col_num > MAX_PIPES:
            break

        if df_pipe is None or df_pipe.empty:
            base[f"p{col_num}_pipe_type"]      = EMPTY_STATUS
            base[f"p{col_num}_flow_rate_m3_h"] = 0.0
            base[f"p{col_num}_status"]         = EMPTY_STATUS
            continue

        df_p = df_pipe[["timestamp", "pipe_type",
                         "flow_rate_m3_h", "status"]].copy()
        df_p["timestamp"] = pd.to_datetime(df_p["timestamp"])
        df_p = df_p.rename(columns={
            "pipe_type":      f"p{col_num}_pipe_type",
            "flow_rate_m3_h": f"p{col_num}_flow_rate_m3_h",
            "status":         f"p{col_num}_status",
        })

        base = pd.merge_asof(
            base.sort_values("timestamp"),
            df_p.sort_values("timestamp"),
            on="timestamp",
            tolerance=pd.Timedelta("2s"),
            direction="nearest",
        )

        base[f"p{col_num}_pipe_type"]      = base[f"p{col_num}_pipe_type"].fillna(EMPTY_STATUS)
        base[f"p{col_num}_flow_rate_m3_h"] = base[f"p{col_num}_flow_rate_m3_h"].fillna(0.0).round(4)
        base[f"p{col_num}_status"]         = base[f"p{col_num}_status"].fillna(EMPTY_STATUS)

    for i in range(len(pipe_dfs) + 1, MAX_PIPES + 1):
        base[f"p{i}_pipe_type"]      = EMPTY_STATUS
        base[f"p{i}_flow_rate_m3_h"] = 0.0
        base[f"p{i}_status"]         = EMPTY_STATUS

    base["timestamp"] = base["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return base[OUTPUT_COLS]

# ==========================================
# PERSISTÊNCIA NO TRUSTED (S3)
# ==========================================

def save_trusted(s3, platform_id, tank_id, df):
    """
    Faz append no CSV trusted do tanque no S3.
    Chave: FPSO-01/TK-01.csv
    Lê o existente, concatena e reescreve.
    """
    key = f"{platform_id}/{tank_id}.csv"

    try:
        existing = s3_read_csv(s3, TRUSTED_BUCKET, key)
        combined = pd.concat([existing, df], ignore_index=True)
    except Exception:
        combined = df

    s3_write_csv(s3, TRUSTED_BUCKET, key, combined)

# ==========================================
# HANDLER LAMBDA
# ==========================================

def lambda_handler(event, context):
    print("=" * 55)
    print(" DeepWatch — ETL1 Lambda: Raw → Trusted")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    s3     = get_s3()
    offset = s3_read_json(s3, RAW_BUCKET, OFFSET_KEY)
    tanks  = discover_tanks(s3)

    if not tanks:
        print("[AVISO] Nenhum arquivo encontrado no bucket raw.")
        return {"status": "ok", "tanks_updated": 0}

    total_rows    = 0
    tanks_updated = 0

    for (platform_id, tank_id), info in tanks.items():
        label = f"{platform_id}/{tank_id}"

        # --- Lê nível ---
        df_nivel = None
        new_off_nivel = offset.get(info["nivel"], 0)

        if info["nivel"]:
            df_raw_nivel, new_off_nivel = read_new_rows(
                s3, info["nivel"], offset)
            if df_raw_nivel is not None:
                df_nivel = clean_nivel(df_raw_nivel)

        if df_nivel is None or df_nivel.empty:
            continue

        # --- Lê canos ---
        pipe_dfs     = []
        pipe_offsets = []

        for filename, key in info["pipes"]:
            df_raw_pipe, new_off_pipe = read_new_rows(s3, key, offset)
            if df_raw_pipe is not None:
                df_pipe = clean_vazao(df_raw_pipe)
            else:
                df_pipe = None
            pipe_dfs.append(df_pipe)
            pipe_offsets.append((key, new_off_pipe))

        # --- Unifica e salva ---
        df_wide = build_wide_rows(df_nivel, pipe_dfs)
        if df_wide.empty:
            continue

        save_trusted(s3, platform_id, tank_id, df_wide)

        # --- Atualiza offsets ---
        offset[info["nivel"]] = new_off_nivel
        for key, new_off in pipe_offsets:
            offset[key] = new_off

        n = len(df_wide)
        total_rows    += n
        tanks_updated += 1
        print(f"  {label} — {n} linhas salvas")

    # Persiste offset no S3
    s3_write_json(s3, RAW_BUCKET, OFFSET_KEY, offset)

    result = {
        "status":        "ok",
        "tanks_updated": tanks_updated,
        "rows_written":  total_rows,
        "timestamp":     datetime.now().isoformat(),
    }
    print(f"\n  Tanques atualizados: {tanks_updated}")
    print(f"  Linhas escritas    : {total_rows}")
    print("=" * 55)
    return result
