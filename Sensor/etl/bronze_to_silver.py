import pandas as pd
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "bronze")
SILVER_DIR = os.path.join(BASE_DIR, "silver")
FLOW_RATE_MIN = 0.0
FLOW_RATE_MAX = 5000.0
PRESSURE_MIN = 0.0
PRESSURE_MAX = 200.0
TANK_LEVEL_MIN = 0.0
TANK_LEVEL_MAX = 100.0

REQUIRED_COLUMNS = {"timestamp", "platform_id", "tank_id", "flow_rate_m3_h", "pressure_bar", "tank_level_percent"}


def load_bronze_files(bronze_dir):
    dataframes = []
    for filename in os.listdir(bronze_dir):
        if filename.endswith(".csv"):
            path = os.path.join(bronze_dir, filename)
            df = pd.read_csv(path)
            df["_source_file"] = filename
            dataframes.append(df)
    if not dataframes:
        print("Nenhum arquivo CSV encontrado em:", bronze_dir)
        sys.exit(1)
    return pd.concat(dataframes, ignore_index=True)


def validate_columns(df):
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        print(f"Colunas ausentes no CSV: {missing}")
        sys.exit(1)


def clean(df):
    initial_count = len(df)
    report = {}

    df = df.drop_duplicates(subset=["timestamp", "platform_id", "tank_id"])
    report["duplicatas_removidas"] = initial_count - len(df)

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    invalid_ts = df["timestamp"].isna().sum()
    df = df.dropna(subset=["timestamp"])
    report["timestamps_invalidos"] = invalid_ts

    numeric_cols = ["flow_rate_m3_h", "pressure_bar", "tank_level_percent"]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    nulls_before = df[numeric_cols].isna().sum().sum()
    df = df.dropna(subset=numeric_cols)
    report["valores_nao_numericos"] = nulls_before

    mask_flow = (df["flow_rate_m3_h"] < FLOW_RATE_MIN) | (df["flow_rate_m3_h"] > FLOW_RATE_MAX)
    mask_pressure = (df["pressure_bar"] < PRESSURE_MIN) | (df["pressure_bar"] > PRESSURE_MAX)
    mask_level = (df["tank_level_percent"] < TANK_LEVEL_MIN) | (df["tank_level_percent"] > TANK_LEVEL_MAX)

    out_of_range = (mask_flow | mask_pressure | mask_level).sum()
    df = df[~(mask_flow | mask_pressure | mask_level)]
    report["fora_de_faixa"] = out_of_range

    report["registros_finais"] = len(df)
    return df, report


def normalize(df):
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df["platform_id"] = df["platform_id"].astype(str).str.strip().str.upper()
    df["tank_id"] = df["tank_id"].astype(str).str.strip().str.upper()
    df["flow_rate_m3_h"] = df["flow_rate_m3_h"].round(4)
    df["pressure_bar"] = df["pressure_bar"].round(4)
    df["tank_level_percent"] = df["tank_level_percent"].round(4)
    return df


def save_silver(df, silver_dir):
    os.makedirs(silver_dir, exist_ok=True)
    output_cols = ["timestamp", "platform_id", "tank_id", "flow_rate_m3_h", "pressure_bar", "tank_level_percent"]
    timestamp_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(silver_dir, f"silver_{timestamp_label}.csv")
    df[output_cols].sort_values(["platform_id", "tank_id", "timestamp"]).to_csv(output_path, index=False)
    return output_path


def print_report(report):
    print("\n=== Relatório Bronze → Silver ===")
    print(f"  Duplicatas removidas     : {report['duplicatas_removidas']}")
    print(f"  Timestamps inválidos     : {report['timestamps_invalidos']}")
    print(f"  Valores não numéricos    : {report['valores_nao_numericos']}")
    print(f"  Registros fora de faixa  : {report['fora_de_faixa']}")
    print(f"  Registros finais (silver): {report['registros_finais']}")
    print("=================================\n")


def main():
    df = load_bronze_files(BRONZE_DIR)
    validate_columns(df)
    df, report = clean(df)
    df = normalize(df)
    output_path = save_silver(df, SILVER_DIR)
    print_report(report)
    print(f"Arquivo Silver salvo em: {output_path}")


if __name__ == "__main__":
    main()
