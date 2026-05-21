"""
DeepWatch — ETL 1: Raw → Trusted
==================================
Lê os CSVs novos da camada 1raw (incrementalmente via offset),
valida, limpa e unifica por tanque na camada 2trusted.

Estrutura esperada de entrada:
  Local/1raw/FPSO-01/TK-01/nivel.csv
  Local/1raw/FPSO-01/TK-01/PIPE-IN-01.csv
  ...

Estrutura de saída:
  Local/2trusted/FPSO-01/TK-01/trusted.csv  ← append incremental

Estado de offset:
  Local/.etl_state/offset_raw.json
  Guarda quantas linhas já foram processadas por arquivo.

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
# RANGES DE VALIDAÇÃO
# ==========================================

FLOW_RATE_MIN     = 0.0
FLOW_RATE_MAX     = 5000.0
TANK_LEVEL_MIN    = 0.0
TANK_LEVEL_MAX    = 100.0

# Colunas obrigatórias por tipo de sensor
COLS_NIVEL = {"timestamp", "platform_id", "tank_id", "side",
              "tank_level_percent", "status"}
COLS_VAZAO = {"timestamp", "platform_id", "tank_id", "pipe_id",
              "pipe_type", "flow_rate_m3_h", "status"}

# Schema unificado de saída do trusted
OUTPUT_COLS = [
    "timestamp", "platform_id", "tank_id", "side",
    "sensor_type",          # "NIVEL" | "VAZAO"
    "pipe_id",              # null para leituras de nível
    "pipe_type",            # null para leituras de nível
    "tank_level_percent",   # null para leituras de vazão
    "flow_rate_m3_h",       # null para leituras de nível
    "sensor_status",        # status original do sensor
]

# ==========================================
# GERENCIAMENTO DE OFFSET
# ==========================================

def load_offset():
    if not os.path.exists(OFFSET_FILE):
        return {}
    with open(OFFSET_FILE, "r") as f:
        return json.load(f)

def save_offset(offset):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OFFSET_FILE, "w") as f:
        json.dump(offset, f, indent=2)

def offset_key(platform_id, tank_id, filename):
    """Chave única para cada arquivo CSV no estado de offset."""
    return f"{platform_id}/{tank_id}/{filename}"

# ==========================================
# DESCOBERTA DE ARQUIVOS
# ==========================================

def discover_files(raw_dir):
    """
    Percorre a hierarquia raw_dir/FPSO-XX/TK-XX/*.csv
    e retorna lista de dicts com metadados de cada arquivo.
    """
    files = []
    if not os.path.exists(raw_dir):
        print(f"[ERRO] Pasta 1raw não encontrada: {raw_dir}")
        sys.exit(1)

    for platform_id in sorted(os.listdir(raw_dir)):
        platform_path = os.path.join(raw_dir, platform_id)
        if not os.path.isdir(platform_path):
            continue
        for tank_id in sorted(os.listdir(platform_path)):
            tank_path = os.path.join(platform_path, tank_id)
            if not os.path.isdir(tank_path):
                continue
            for filename in sorted(os.listdir(tank_path)):
                if not filename.endswith(".csv"):
                    continue
                sensor_type = "NIVEL" if filename == "nivel.csv" else "VAZAO"
                files.append({
                    "platform_id":  platform_id,
                    "tank_id":      tank_id,
                    "filename":     filename,
                    "sensor_type":  sensor_type,
                    "path":         os.path.join(tank_path, filename),
                })
    return files

# ==========================================
# LEITURA INCREMENTAL
# ==========================================

def read_new_rows(file_info, offset):
    """
    Lê apenas as linhas novas do CSV (após o offset registrado).
    Retorna DataFrame com as novas linhas e o novo offset.
    """
    key        = offset_key(file_info["platform_id"],
                            file_info["tank_id"],
                            file_info["filename"])
    rows_done  = offset.get(key, 0)
    path       = file_info["path"]

    # Conta total de linhas sem carregar tudo na memória
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        total_lines = sum(1 for _ in f)

    # total_lines inclui o header; linhas de dados = total_lines - 1
    data_lines = total_lines - 1

    if data_lines <= rows_done:
        return None, rows_done  # nada de novo

    # Lê só as linhas novas: pula header + rows_done linhas já processadas
    df = pd.read_csv(
        path,
        skiprows=range(1, rows_done + 1),  # pula as já processadas (não o header)
        header=0,
        encoding="utf-8-sig",
        encoding_errors="replace",
    )

    # Se rows_done > 0 o skiprows acima já deixou só as novas;
    # se rows_done == 0, df já é o arquivo inteiro
    new_offset = rows_done + len(df)
    return df, new_offset

# ==========================================
# VALIDAÇÃO E LIMPEZA
# ==========================================

def validate_and_clean_nivel(df, source):
    """Valida schema e limpa leituras de nível."""
    report = {"arquivo": source, "tipo": "NIVEL", "erros": {}}

    missing = COLS_NIVEL - set(df.columns)
    if missing:
        print(f"  [AVISO] {source} — colunas ausentes: {missing} — arquivo ignorado")
        return None, report

    df = df.copy()

    # Timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    inv = df["timestamp"].isna().sum()
    report["erros"]["timestamps_invalidos"] = int(inv)
    df = df.dropna(subset=["timestamp"])

    # Numérico
    df["tank_level_percent"] = pd.to_numeric(df["tank_level_percent"], errors="coerce")
    inv_num = df["tank_level_percent"].isna().sum()
    report["erros"]["valores_nao_numericos"] = int(inv_num)
    df = df.dropna(subset=["tank_level_percent"])

    # Range
    mask = (df["tank_level_percent"] < TANK_LEVEL_MIN) | \
           (df["tank_level_percent"] > TANK_LEVEL_MAX)
    report["erros"]["fora_de_faixa"] = int(mask.sum())
    df = df[~mask]

    # Deduplicação
    before = len(df)
    df = df.drop_duplicates(subset=["timestamp", "platform_id", "tank_id"])
    report["erros"]["duplicatas"] = before - len(df)

    report["registros_validos"] = len(df)
    return df, report

def validate_and_clean_vazao(df, source):
    """Valida schema e limpa leituras de vazão."""
    report = {"arquivo": source, "tipo": "VAZAO", "erros": {}}

    missing = COLS_VAZAO - set(df.columns)
    if missing:
        print(f"  [AVISO] {source} — colunas ausentes: {missing} — arquivo ignorado")
        return None, report

    df = df.copy()

    # Timestamp
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    inv = df["timestamp"].isna().sum()
    report["erros"]["timestamps_invalidos"] = int(inv)
    df = df.dropna(subset=["timestamp"])

    # Numérico
    df["flow_rate_m3_h"] = pd.to_numeric(df["flow_rate_m3_h"], errors="coerce")
    inv_num = df["flow_rate_m3_h"].isna().sum()
    report["erros"]["valores_nao_numericos"] = int(inv_num)
    df = df.dropna(subset=["flow_rate_m3_h"])

    # Range
    mask = (df["flow_rate_m3_h"] < FLOW_RATE_MIN) | \
           (df["flow_rate_m3_h"] > FLOW_RATE_MAX)
    report["erros"]["fora_de_faixa"] = int(mask.sum())
    df = df[~mask]

    # Deduplicação — inclui pipe_id pois dois canos do mesmo tanque
    # no mesmo timestamp são registros distintos e válidos
    before = len(df)
    df = df.drop_duplicates(
        subset=["timestamp", "platform_id", "tank_id", "pipe_id"])
    report["erros"]["duplicatas"] = before - len(df)

    report["registros_validos"] = len(df)
    return df, report

# ==========================================
# NORMALIZAÇÃO E UNIFICAÇÃO
# ==========================================

def normalize(df, sensor_type):
    """Normaliza strings e arredondamentos, adiciona sensor_type."""
    df = df.copy()
    df["timestamp"]   = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df["platform_id"] = df["platform_id"].astype(str).str.strip().str.upper()
    df["tank_id"]     = df["tank_id"].astype(str).str.strip().str.upper()
    df["sensor_type"] = sensor_type

    if sensor_type == "NIVEL":
        df["tank_level_percent"] = df["tank_level_percent"].round(4)
        df["flow_rate_m3_h"]     = None
        df["pipe_id"]            = None
        df["pipe_type"]          = None
        df.rename(columns={"status": "sensor_status"}, inplace=True)
        if "side" not in df.columns:
            df["side"] = None

    elif sensor_type == "VAZAO":
        df["flow_rate_m3_h"]     = df["flow_rate_m3_h"].round(4)
        df["tank_level_percent"] = None
        df.rename(columns={"status": "sensor_status"}, inplace=True)
        if "side" not in df.columns:
            df["side"] = None

    return df[OUTPUT_COLS]

# ==========================================
# PERSISTÊNCIA NO TRUSTED
# ==========================================

def save_trusted(df, platform_id, tank_id):
    """
    Append no CSV trusted do tanque.
    Estrutura: 2trusted/FPSO-01/TK-01.csv
    """
    fpso_dir = os.path.join(TRUSTED_DIR, platform_id)
    os.makedirs(fpso_dir, exist_ok=True)
    out_path = os.path.join(fpso_dir, f"{tank_id}.csv")

    write_header = not os.path.exists(out_path)
    df.to_csv(out_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")
    return out_path

# ==========================================
# LOOP PRINCIPAL
# ==========================================

def main():
    print("=" * 55)
    print(" DeepWatch — ETL 1: Raw → Trusted")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    offset  = load_offset()
    files   = discover_files(RAW_DIR)

    if not files:
        print("[AVISO] Nenhum arquivo CSV encontrado em 1raw.")
        sys.exit(0)

    total_new      = 0
    total_errors   = 0
    files_updated  = 0
    reports        = []

    for file_info in files:
        platform_id = file_info["platform_id"]
        tank_id     = file_info["tank_id"]
        sensor_type = file_info["sensor_type"]
        source      = f"{platform_id}/{tank_id}/{file_info['filename']}"

        df_new, new_offset = read_new_rows(file_info, offset)

        if df_new is None or len(df_new) == 0:
            continue  # nada novo neste arquivo

        # Valida e limpa conforme tipo
        if sensor_type == "NIVEL":
            df_clean, report = validate_and_clean_nivel(df_new, source)
        else:
            df_clean, report = validate_and_clean_vazao(df_new, source)

        if df_clean is None or len(df_clean) == 0:
            # Atualiza offset mesmo assim para não reprocessar linhas ruins
            key = offset_key(platform_id, tank_id, file_info["filename"])
            offset[key] = new_offset
            reports.append(report)
            continue

        # Normaliza e salva
        df_norm = normalize(df_clean, sensor_type)
        save_trusted(df_norm, platform_id, tank_id)

        # Atualiza offset
        key = offset_key(platform_id, tank_id, file_info["filename"])
        offset[key] = new_offset

        erros = sum(report["erros"].values())
        total_new    += report["registros_validos"]
        total_errors += erros
        files_updated += 1
        reports.append(report)

    save_offset(offset)

    # ---- Relatório ----
    print(f"\n  Arquivos com dados novos : {files_updated}")
    print(f"  Registros válidos salvos : {total_new}")
    print(f"  Erros/descartes totais   : {total_errors}")

    if total_errors > 0:
        print("\n  Detalhes de erros:")
        for r in reports:
            erros = {k: v for k, v in r["erros"].items() if v > 0}
            if erros:
                print(f"    {r['arquivo']} ({r['tipo']}): {erros}")

    if total_new == 0:
        print("\n  Nenhum dado novo encontrado. Trusted já está atualizado.")
    else:
        print(f"\n  Trusted atualizado em: {TRUSTED_DIR}")

    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()