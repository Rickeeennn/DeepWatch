import pandas as pd
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SILVER_DIR = os.path.join(BASE_DIR, "silver")
GOLD_DIR = os.path.join(BASE_DIR, "gold")
TANK_CAPACITY_PERCENT = 100.0
CRITICAL_LEVEL = 90.0
ATTENTION_LEVEL = 75.0

CRITICAL_PRESSURE_HIGH = 150.0
ATTENTION_PRESSURE_HIGH = 100.0
ATTENTION_PRESSURE_LOW = 5.0

ATTENTION_FLOW_DROP_THRESHOLD = 0.3


def load_silver_files(silver_dir):
    dataframes = []
    for filename in os.listdir(silver_dir):
        if filename.endswith(".csv"):
            path = os.path.join(silver_dir, filename)
            df = pd.read_csv(path, parse_dates=["timestamp"])
            dataframes.append(df)
    if not dataframes:
        print("Nenhum arquivo CSV encontrado em:", silver_dir)
        sys.exit(1)
    return pd.concat(dataframes, ignore_index=True)


def compute_tank_status(level):
    if level >= CRITICAL_LEVEL:
        return "CRÍTICO"
    elif level >= ATTENTION_LEVEL:
        return "ATENÇÃO"
    return "NORMAL"


def compute_pressure_status(pressure):
    if pressure >= CRITICAL_PRESSURE_HIGH:
        return "CRÍTICO"
    elif pressure >= ATTENTION_PRESSURE_HIGH or pressure <= ATTENTION_PRESSURE_LOW:
        return "ATENÇÃO"
    return "NORMAL"


def estimate_time_to_full(group):
    group = group.sort_values("timestamp").copy()
    group["delta_minutes"] = group["timestamp"].diff().dt.total_seconds().div(60)
    group["delta_level"] = group["tank_level_percent"].diff()
    group["level_rate_per_min"] = group["delta_level"] / group["delta_minutes"]
    last = group.iloc[-1]
    rate = group["level_rate_per_min"].dropna().median()
    if pd.isna(rate) or rate <= 0:
        return None
    remaining = TANK_CAPACITY_PERCENT - last["tank_level_percent"]
    return round(remaining / rate, 2)


def compute_transfer_efficiency(group):
    group = group.sort_values("timestamp").copy()
    if len(group) < 2:
        return None, None, "NORMAL"
    flow_std = round(group["flow_rate_m3_h"].std(), 4)
    pressure_std = round(group["pressure_bar"].std(), 4)
    group["flow_rolling"] = group["flow_rate_m3_h"].rolling(window=5, min_periods=1).mean()
    last_flow = group["flow_rolling"].iloc[-1]
    avg_flow = group["flow_rate_m3_h"].mean()
    if avg_flow > 0 and (avg_flow - last_flow) / avg_flow >= ATTENTION_FLOW_DROP_THRESHOLD:
        efficiency_flag = "ATENÇÃO"
    else:
        efficiency_flag = "NORMAL"
    return flow_std, pressure_std, efficiency_flag


def build_gold(df):
    records = []

    for (platform_id, tank_id), group in df.groupby(["platform_id", "tank_id"]):
        group = group.sort_values("timestamp")
        last = group.iloc[-1]
        first = group.iloc[0]

        current_level = last["tank_level_percent"]
        current_pressure = last["pressure_bar"]
        current_flow = last["flow_rate_m3_h"]

        avg_level = round(group["tank_level_percent"].mean(), 4)
        avg_pressure = round(group["pressure_bar"].mean(), 4)
        avg_flow = round(group["flow_rate_m3_h"].mean(), 4)
        max_level = round(group["tank_level_percent"].max(), 4)
        min_level = round(group["tank_level_percent"].min(), 4)

        tank_status = compute_tank_status(current_level)
        pressure_status = compute_pressure_status(current_pressure)

        minutes_to_full = estimate_time_to_full(group)
        flow_std, pressure_std, transfer_efficiency_status = compute_transfer_efficiency(group)

        overall_status = "NORMAL"
        if tank_status == "CRÍTICO" or pressure_status == "CRÍTICO":
            overall_status = "CRÍTICO"
        elif tank_status == "ATENÇÃO" or pressure_status == "ATENÇÃO" or transfer_efficiency_status == "ATENÇÃO":
            overall_status = "ATENÇÃO"

        records.append({
            "platform_id": platform_id,
            "tank_id": tank_id,
            "observation_start": first["timestamp"].strftime("%Y-%m-%dT%H:%M:%S"),
            "observation_end": last["timestamp"].strftime("%Y-%m-%dT%H:%M:%S"),
            "total_readings": len(group),
            "current_level_percent": round(current_level, 4),
            "avg_level_percent": avg_level,
            "max_level_percent": max_level,
            "min_level_percent": min_level,
            "current_flow_m3_h": round(current_flow, 4),
            "avg_flow_m3_h": avg_flow,
            "flow_std": flow_std,
            "current_pressure_bar": round(current_pressure, 4),
            "avg_pressure_bar": avg_pressure,
            "pressure_std": pressure_std,
            "minutes_to_full": minutes_to_full,
            "tank_status": tank_status,
            "pressure_status": pressure_status,
            "transfer_efficiency_status": transfer_efficiency_status,
            "overall_status": overall_status,
        })

    return pd.DataFrame(records)


def save_gold(df, gold_dir):
    os.makedirs(gold_dir, exist_ok=True)
    timestamp_label = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(gold_dir, f"gold_{timestamp_label}.csv")
    status_order = {"CRÍTICO": 0, "ATENÇÃO": 1, "NORMAL": 2}
    df["_sort_key"] = df["overall_status"].map(status_order)
    df.sort_values(["_sort_key", "platform_id", "tank_id"]).drop(columns=["_sort_key"]).to_csv(output_path, index=False)
    return output_path


def print_report(df):
    print("\n=== Relatório Silver → Gold ===")
    print(f"  Pares plataforma/tanque processados: {len(df)}")
    status_counts = df["overall_status"].value_counts()
    for status, count in status_counts.items():
        print(f"  {status}: {count} tanque(s)")
    criticos = df[df["overall_status"] == "CRÍTICO"][["platform_id", "tank_id", "current_level_percent", "minutes_to_full"]]
    if not criticos.empty:
        print("\n  Tanques em estado CRÍTICO:")
        for _, row in criticos.iterrows():
            mins = f"{row['minutes_to_full']} min" if pd.notna(row["minutes_to_full"]) else "N/A"
            print(f"    [{row['platform_id']}] {row['tank_id']} — nível: {row['current_level_percent']}% — tempo até cheio: {mins}")
    print("================================\n")


def main():
    df = load_silver_files(SILVER_DIR)
    gold_df = build_gold(df)
    output_path = save_gold(gold_df, GOLD_DIR)
    print_report(gold_df)
    print(f"Arquivo Gold salvo em: {output_path}")


if __name__ == "__main__":
    main()
