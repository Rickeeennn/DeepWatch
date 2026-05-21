"""
DeepWatch — ETL 1: Raw → Trusted
==================================
Lê os CSVs novos da camada 1raw (incrementalmente via offset),
valida, limpa e unifica por tanque na camada 2trusted.

Estrutura esperada de entrada:
  Local/1raw/FPSO-01/TK-01/nivel.csv
  Local/1raw/FPSO-01/TK-01/PIPE-IN-01.csv
  ...

Estrutura de saída (uma linha por timestamp, schema fixo):
  Local/2trusted/FPSO-01/TK-01.csv

Schema de saída:
  timestamp, platform_id, tank_id, side,
  tank_level_percent, tank_status,
  p1_pipe_type, p1_flow_rate_m3_h, p1_status,
  p2_pipe_type, p2_flow_rate_m3_h, p2_status,
  p3_pipe_type, p3_flow_rate_m3_h, p3_status,
  p4_pipe_type, p4_flow_rate_m3_h, p4_status,
  p5_pipe_type, p5_flow_rate_m3_h, p5_status

Canos inexistentes: pipe_type=EMPTY, flow_rate=0.0, status=EMPTY

Estado de offset:
  Local/.etl_state/offset_raw.json

Rodar: python etl_raw_to_trusted.py
"""

import os
import json
import sys
import pandas as pd
from datetime import datetime

# ==========================================
# CAMINHOS
# ==========================================

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
RAW_DIR     = os.path.join(BASE_DIR, "1raw")
TRUSTED_DIR = os.path.join(BASE_DIR, "2trusted")
STATE_DIR   = os.path.join(BASE_DIR, ".etl_state")
OFFSET_FILE = os.path.join(STATE_DIR, "offset_raw.json")

# ==========================================
# CONFIGURAÇÕES
# ==========================================

MAX_PIPES      = 5          # número fixo de colunas de cano no trusted
EMPTY_STATUS   = "EMPTY"   # valor para canos inexistentes
FLOW_RATE_MIN  = 0.0
FLOW_RATE_MAX  = 5000.0
TANK_LEVEL_MIN = 0.0
TANK_LEVEL_MAX = 100.0

# Colunas obrigatórias por tipo de sensor
COLS_NIVEL = {"timestamp", "platform_id", "tank_id", "side",
              "tank_level_percent", "status"}
COLS_VAZAO = {"timestamp", "platform_id", "tank_id", "pipe_id",
              "pipe_type", "flow_rate_m3_h", "status"}

# Schema fixo de saída
OUTPUT_COLS = (
    ["timestamp", "platform_id", "tank_id", "side",
     "tank_level_percent", "tank_status"] +
    [col
     for i in range(1, MAX_PIPES + 1)
     for col in (f"p{i}_pipe_type", f"p{i}_flow_rate_m3_h", f"p{i}_status")]
)

# ==========================================
# GERENCIAMENTO DE OFFSET
# ==========================================

def load_offset():
    if not os.path.exists(OFFSET_FILE):
        return {}
    with open(OFFSET_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_offset(offset):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OFFSET_FILE, "w", encoding="utf-8") as f:
        json.dump(offset, f, indent=2)

def offset_key(platform_id, tank_id, filename):
    return f"{platform_id}/{tank_id}/{filename}"

# ==========================================
# DESCOBERTA DE ARQUIVOS POR TANQUE
# ==========================================

def discover_tanks(raw_dir):
    """
    Percorre raw_dir/FPSO-XX/TK-XX/ e retorna um dict:
    { (platform_id, tank_id): { "nivel": path, "pipes": [path, ...] } }
    """
    tanks = {}
    if not os.path.exists(raw_dir):
        print(f"[ERRO] Pasta 1raw não encontrada: {raw_dir}")
        sys.exit(1)

    for platform_id in sorted(os.listdir(raw_dir)):
        p_path = os.path.join(raw_dir, platform_id)
        if not os.path.isdir(p_path):
            continue
        for tank_id in sorted(os.listdir(p_path)):
            t_path = os.path.join(p_path, tank_id)
            if not os.path.isdir(t_path):
                continue
            nivel_path = None
            pipe_paths = []
            for filename in sorted(os.listdir(t_path)):
                if not filename.endswith(".csv"):
                    continue
                full = os.path.join(t_path, filename)
                if filename == "nivel.csv":
                    nivel_path = full
                else:
                    pipe_paths.append((filename, full))
            tanks[(platform_id, tank_id)] = {
                "nivel": nivel_path,
                "pipes": pipe_paths,   # lista de (filename, path) ordenada
            }
    return tanks

# ==========================================
# LEITURA INCREMENTAL
# ==========================================

def read_new_rows(path, key, offset):
    """
    Lê apenas as linhas novas do CSV após o offset registrado.
    Retorna (DataFrame | None, novo_offset).
    """
    rows_done = offset.get(key, 0)

    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        total_lines = sum(1 for _ in f)

    data_lines = total_lines - 1
    if data_lines <= rows_done:
        return None, rows_done

    df = pd.read_csv(
        path,
        skiprows=range(1, rows_done + 1),
        header=0,
        encoding="utf-8-sig",
        encoding_errors="replace",
    )
    return df, rows_done + len(df)

# ==========================================
# VALIDAÇÃO E LIMPEZA
# ==========================================

def clean_nivel(df, source):
    report = {"arquivo": source, "erros": {}}

    missing = COLS_NIVEL - set(df.columns)
    if missing:
        print(f"  [AVISO] {source} — colunas ausentes: {missing}")
        return None, report

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    report["erros"]["ts_invalidos"] = int(df["timestamp"].isna().sum())
    df = df.dropna(subset=["timestamp"])

    df["tank_level_percent"] = pd.to_numeric(
        df["tank_level_percent"], errors="coerce")
    report["erros"]["nao_numericos"] = int(
        df["tank_level_percent"].isna().sum())
    df = df.dropna(subset=["tank_level_percent"])

    mask = ((df["tank_level_percent"] < TANK_LEVEL_MIN) |
            (df["tank_level_percent"] > TANK_LEVEL_MAX))
    report["erros"]["fora_de_faixa"] = int(mask.sum())
    df = df[~mask]

    before = len(df)
    df = df.drop_duplicates(subset=["timestamp", "platform_id", "tank_id"])
    report["erros"]["duplicatas"] = before - len(df)

    df["timestamp"] = df["timestamp"].dt.floor("s")
    report["registros_validos"] = len(df)
    return df, report

def clean_vazao(df, source):
    report = {"arquivo": source, "erros": {}}

    missing = COLS_VAZAO - set(df.columns)
    if missing:
        print(f"  [AVISO] {source} — colunas ausentes: {missing}")
        return None, report

    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    report["erros"]["ts_invalidos"] = int(df["timestamp"].isna().sum())
    df = df.dropna(subset=["timestamp"])

    df["flow_rate_m3_h"] = pd.to_numeric(
        df["flow_rate_m3_h"], errors="coerce")
    report["erros"]["nao_numericos"] = int(
        df["flow_rate_m3_h"].isna().sum())
    df = df.dropna(subset=["flow_rate_m3_h"])

    mask = ((df["flow_rate_m3_h"] < FLOW_RATE_MIN) |
            (df["flow_rate_m3_h"] > FLOW_RATE_MAX))
    report["erros"]["fora_de_faixa"] = int(mask.sum())
    df = df[~mask]

    before = len(df)
    df = df.drop_duplicates(
        subset=["timestamp", "platform_id", "tank_id", "pipe_id"])
    report["erros"]["duplicatas"] = before - len(df)

    df["timestamp"] = df["timestamp"].dt.floor("s")
    report["registros_validos"] = len(df)
    return df, report

# ==========================================
# UNIFICAÇÃO EM SCHEMA WIDE (UMA LINHA POR TIMESTAMP)
# ==========================================

def build_wide_rows(df_nivel, pipe_dfs):
    """
    Recebe:
      df_nivel  — DataFrame limpo do sensor de nível
      pipe_dfs  — lista ordenada de DataFrames limpos de cada cano (máx 5)

    Retorna DataFrame com schema fixo (uma linha por timestamp do nível).
    Canos com índice acima do número real ficam preenchidos com EMPTY.
    """
    if df_nivel is None or df_nivel.empty:
        return pd.DataFrame()

    # Base: uma linha por timestamp de nível
    base = df_nivel[["timestamp", "platform_id", "tank_id", "side",
                      "tank_level_percent", "status"]].copy()
    base = base.rename(columns={"status": "tank_status"})
    base["timestamp"] = pd.to_datetime(base["timestamp"])

    # Normaliza strings
    base["platform_id"] = base["platform_id"].astype(str).str.strip().str.upper()
    base["tank_id"]     = base["tank_id"].astype(str).str.strip().str.upper()
    base["tank_level_percent"] = base["tank_level_percent"].round(4)

    # Faz merge de cada cano pelo timestamp mais próximo (tolerância 2s)
    # Colunas ainda não existem — são criadas pelo merge e depois preenchidas com EMPTY
    for idx, df_pipe in enumerate(pipe_dfs):
        col_num = idx + 1
        if col_num > MAX_PIPES:
            break

        if df_pipe is None or df_pipe.empty:
            # Cano inexistente — cria colunas EMPTY diretamente
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

        # Preenche com EMPTY apenas onde não houve match (NaN após merge)
        base[f"p{col_num}_pipe_type"]      = base[f"p{col_num}_pipe_type"].fillna(EMPTY_STATUS)
        base[f"p{col_num}_flow_rate_m3_h"] = base[f"p{col_num}_flow_rate_m3_h"].fillna(0.0).round(4)
        base[f"p{col_num}_status"]         = base[f"p{col_num}_status"].fillna(EMPTY_STATUS)

    # Preenche colunas de canos acima do número real do tanque
    for i in range(len(pipe_dfs) + 1, MAX_PIPES + 1):
        base[f"p{i}_pipe_type"]      = EMPTY_STATUS
        base[f"p{i}_flow_rate_m3_h"] = 0.0
        base[f"p{i}_status"]         = EMPTY_STATUS

    # Formata timestamp para string ISO
    base["timestamp"] = base["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    return base[OUTPUT_COLS]

# ==========================================
# PERSISTÊNCIA NO TRUSTED
# ==========================================

def save_trusted(df, platform_id, tank_id):
    fpso_dir = os.path.join(TRUSTED_DIR, platform_id)
    os.makedirs(fpso_dir, exist_ok=True)
    out_path = os.path.join(fpso_dir, f"{tank_id}.csv")

    write_header = not os.path.exists(out_path)
    df.to_csv(out_path, mode="a", header=write_header,
              index=False, encoding="utf-8-sig")
    return out_path

# ==========================================
# LOOP PRINCIPAL
# ==========================================

def main():
    print("=" * 55)
    print(" DeepWatch — ETL 1: Raw → Trusted")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    offset = load_offset()
    tanks  = discover_tanks(RAW_DIR)

    if not tanks:
        print("[AVISO] Nenhum tanque encontrado em 1raw.")
        sys.exit(0)

    total_rows    = 0
    total_errors  = 0
    tanks_updated = 0

    for (platform_id, tank_id), info in tanks.items():
        label = f"{platform_id}/{tank_id}"

        # --- Lê nível ---
        df_nivel = None
        nivel_report = {}
        if info["nivel"]:
            key_nivel = offset_key(platform_id, tank_id, "nivel.csv")
            df_raw_nivel, new_off_nivel = read_new_rows(
                info["nivel"], key_nivel, offset)
            if df_raw_nivel is not None:
                df_nivel, nivel_report = clean_nivel(
                    df_raw_nivel, f"{label}/nivel.csv")

        if df_nivel is None or df_nivel.empty:
            continue  # sem dados de nível novos, nada a unificar

        # --- Lê canos ---
        pipe_dfs   = []
        pipe_offsets = []
        for filename, path in info["pipes"]:
            key_pipe = offset_key(platform_id, tank_id, filename)
            df_raw_pipe, new_off_pipe = read_new_rows(path, key_pipe, offset)
            if df_raw_pipe is not None:
                df_pipe, _ = clean_vazao(df_raw_pipe, f"{label}/{filename}")
            else:
                df_pipe = None
            pipe_dfs.append(df_pipe)
            pipe_offsets.append((key_pipe, new_off_pipe))

        # --- Unifica em schema wide ---
        df_wide = build_wide_rows(df_nivel, pipe_dfs)

        if df_wide.empty:
            continue

        save_trusted(df_wide, platform_id, tank_id)

        # --- Persiste offsets ---
        offset[offset_key(platform_id, tank_id, "nivel.csv")] = new_off_nivel
        for key_pipe, new_off_pipe in pipe_offsets:
            offset[key_pipe] = new_off_pipe

        n_rows = len(df_wide)
        erros  = sum(nivel_report.get("erros", {}).values())
        total_rows   += n_rows
        total_errors += erros
        tanks_updated += 1
        print(f"  {label} — {n_rows} linhas salvas")

    save_offset(offset)

    print(f"\n  Tanques atualizados      : {tanks_updated}")
    print(f"  Linhas trusted geradas   : {total_rows}")
    print(f"  Erros/descartes totais   : {total_errors}")

    if total_rows == 0:
        print("\n  Nenhum dado novo. Trusted já está atualizado.")
    else:
        print(f"\n  Trusted em: {TRUSTED_DIR}")

    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()