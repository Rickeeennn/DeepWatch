"""
DeepWatch — ETL 2: Trusted → Refined
======================================
Lê dados novos do trusted (incrementalmente via offset),
agrega por janela de 1 minuto por tanque e produz métricas
operacionais na camada 3refined.

Métricas calculadas por janela de 1 minuto:
  - Vazão total de entrada (soma dos canos ativos)
  - Nível médio, mínimo e máximo da janela
  - TTC — Time to Completion (horas até tanque cheio)
  - Status do tanque (NORMAL / ATENÇÃO / CRÍTICO)
  - Status de cada cano individualmente (entupimento)
  - Flag de vazamento (nível caindo sem saída registrada)
  - Balanço de massa (divergência entre entrada e variação de nível)
  - overall_status — pior status consolidado do tanque

Estrutura de saída (particionada para Glue/Athena):
  Local/3refined/platform_id=FPSO-01/tank_id=TK-01/refined.csv

Estado de offset:
  Local/.etl_state/offset_trusted.json

Rodar: python etl_trusted_to_refined.py
"""

import os
import json
import sys
import pandas as pd
import numpy as np
from datetime import datetime

# ==========================================
# CAMINHOS
# ==========================================

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
TRUSTED_DIR  = os.path.join(BASE_DIR, "2trusted")
REFINED_DIR  = os.path.join(BASE_DIR, "3refined")
STATE_DIR    = os.path.join(BASE_DIR, ".etl_state")
OFFSET_FILE  = os.path.join(STATE_DIR, "offset_trusted.json")

# ==========================================
# LIMIARES DE ALERTA (definidos com o time)
# ==========================================

CRITICAL_LEVEL_PCT    = 90.0   # % — nível crítico
ATTENTION_LEVEL_PCT   = 80.0   # % — nível de atenção
CRITICAL_TTC_HOURS    = 12.0   # horas — TTC crítico
ATTENTION_TTC_HOURS   = 24.0   # horas — TTC de atenção

# Entupimento: queda de vazão de um cano em relação à sua média histórica
PIPE_DEGRADED_DROP    = 0.20   # -20% = DEGRADADO
PIPE_BLOCKED_DROP     = 0.65   # -65% = ENTUPIDO

# Vazamento: nível caindo enquanto não há saída registrada
LEAK_LEVEL_DROP_PCT   = 0.05   # queda de 0.05% por minuto sem saída = suspeita

# Balanço de massa: divergência tolerada entre entrada e variação de volume
# (margem para sloshing, ruído de sensor, evaporação leve)
MASS_BALANCE_TOLERANCE = 0.15  # 15% de divergência tolerada

# Área do tanque em m² (mesma do mock) — necessária para converter % → m³
AREA_TANQUE_M2   = 700.0
NIVEL_MAXIMO_M   = 30.0

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

def offset_key(platform_id, tank_id):
    return f"{platform_id}/{tank_id}.csv"

# ==========================================
# LEITURA INCREMENTAL DO TRUSTED
# ==========================================

def discover_trusted_files(trusted_dir):
    """Percorre trusted_dir/FPSO-XX/TK-XX.csv"""
    files = []
    if not os.path.exists(trusted_dir):
        print(f"[ERRO] Pasta 2trusted não encontrada: {trusted_dir}")
        sys.exit(1)

    for platform_id in sorted(os.listdir(trusted_dir)):
        p_path = os.path.join(trusted_dir, platform_id)
        if not os.path.isdir(p_path):
            continue
        for filename in sorted(os.listdir(p_path)):
            if not filename.endswith(".csv"):
                continue
            tank_id  = filename[:-4]   # remove .csv → TK-01
            csv_path = os.path.join(p_path, filename)
            files.append({
                "platform_id": platform_id,
                "tank_id":     tank_id,
                "path":        csv_path,
            })
    return files

def read_new_rows(file_info, offset):
    key       = offset_key(file_info["platform_id"], file_info["tank_id"])
    rows_done = offset.get(key, 0)
    path      = file_info["path"]

    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        total_lines = sum(1 for _ in f)

    data_lines = total_lines - 1
    if data_lines <= rows_done:
        return None, rows_done

    df = pd.read_csv(
        path,
        skiprows=range(1, rows_done + 1),
        header=0,
        parse_dates=["timestamp"],
        encoding="utf-8-sig",
        encoding_errors="replace",
    )
    new_offset = rows_done + len(df)
    return df, new_offset

# ==========================================
# SEPARAÇÃO DE LEITURAS
# ==========================================

def split_sensors(df):
    """Separa o trusted em dois DataFrames: nível e vazão."""
    df_nivel = df[df["sensor_type"] == "NIVEL"].copy()
    df_vazao = df[df["sensor_type"] == "VAZAO"].copy()
    return df_nivel, df_vazao

# ==========================================
# AGREGAÇÃO POR MINUTO
# ==========================================

def aggregate_nivel_by_minute(df_nivel):
    """
    Agrega leituras de nível por janela de 1 minuto.
    Retorna DataFrame com: minute, avg_level, min_level, max_level, side
    """
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

def aggregate_vazao_by_minute(df_vazao):
    """
    Agrega leituras de vazão por janela de 1 minuto E por cano.
    Retorna:
      - df_per_pipe: avg_flow por (minute, pipe_id)
      - df_total:    flow_total_m3_h por minute (soma dos canos)
    """
    if df_vazao.empty:
        return pd.DataFrame(), pd.DataFrame()

    df = df_vazao.copy()
    df["minute"] = df["timestamp"].dt.floor("min")

    # Média de cada cano na janela
    df_per_pipe = df.groupby(["minute", "pipe_id"]).agg(
        avg_flow_pipe  = ("flow_rate_m3_h", "mean"),
        pipe_type      = ("pipe_type", "first"),
        sensor_status  = ("sensor_status", lambda x: x.mode()[0]),
    ).reset_index()
    df_per_pipe["avg_flow_pipe"] = df_per_pipe["avg_flow_pipe"].round(4)

    # Soma de todos os canos de entrada na janela = vazão total do tanque
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
    """
    Calcula TTC (horas até tanque cheio) com base na taxa de subida
    do nível entre janelas de minuto consecutivas.
    Retorna Series com TTC em horas para cada linha do nivel_agg.
    """
    if len(nivel_agg) < 2:
        return pd.Series([None] * len(nivel_agg), index=nivel_agg.index)

    df = nivel_agg.sort_values("minute").copy()
    df["delta_min"]   = df["minute"].diff().dt.total_seconds() / 60.0
    df["delta_level"] = df["avg_level"].diff()
    df["rate_per_min"] = df["delta_level"] / df["delta_min"]

    # Mediana das últimas 5 janelas para suavizar ruído
    df["rate_smooth"] = df["rate_per_min"].rolling(5, min_periods=1).median()

    def ttc_row(row):
        rate = row["rate_smooth"]
        if pd.isna(rate) or rate <= 0:
            return None
        remaining = 100.0 - row["avg_level"]
        return round((remaining / rate) / 60.0, 2)  # minutos → horas

    return df.apply(ttc_row, axis=1)

def classify_tank_status(level, ttc_hours):
    """Aplica limiares definidos pelo time."""
    # Crítico: nível OU TTC
    if level >= CRITICAL_LEVEL_PCT:
        return "CRÍTICO"
    if ttc_hours is not None and ttc_hours < CRITICAL_TTC_HOURS:
        return "CRÍTICO"
    # Atenção: nível OU TTC
    if level >= ATTENTION_LEVEL_PCT:
        return "ATENÇÃO"
    if ttc_hours is not None and ttc_hours < ATTENTION_TTC_HOURS:
        return "ATENÇÃO"
    return "NORMAL"

def classify_pipe_status(avg_flow, baseline_flow):
    """
    Compara vazão atual do cano com baseline histórico.
    baseline_flow = média das primeiras leituras do cano (referência de normal).
    """
    if baseline_flow is None or baseline_flow <= 0:
        return "NORMAL"
    drop = (baseline_flow - avg_flow) / baseline_flow
    if drop >= PIPE_BLOCKED_DROP:
        return "ENTUPIDO"
    elif drop >= PIPE_DEGRADED_DROP:
        return "DEGRADADO"
    return "NORMAL"

def detect_leak(nivel_agg, flow_total_agg):
    """
    Flag de vazamento: nível caindo enquanto não há saída registrada.
    Retorna Series booleana alinhada ao nivel_agg.
    """
    if nivel_agg.empty or flow_total_agg.empty:
        return pd.Series([False] * len(nivel_agg), index=nivel_agg.index)

    df = nivel_agg.sort_values("minute").copy()
    df["delta_level"] = df["avg_level"].diff()

    # Junta com vazão total para checar se há saída
    df = df.merge(
        flow_total_agg[["minute", "flow_total_m3_h"]],
        on="minute", how="left"
    )
    df["flow_total_m3_h"] = df["flow_total_m3_h"].fillna(0)

    # Vazamento: nível caindo mais que threshold E sem saída registrada
    leak_flag = (
        (df["delta_level"] < -LEAK_LEVEL_DROP_PCT) &
        (df["flow_total_m3_h"] == 0)
    )
    return leak_flag.values

def compute_mass_balance(nivel_agg, flow_total_agg):
    """
    Balanço de massa simplificado por janela de minuto.
    Compara variação de volume esperada (pela vazão) com variação real (pelo nível).
    Retorna Series com flag 'DIVERGENTE' ou 'OK'.
    """
    if nivel_agg.empty or flow_total_agg.empty:
        return pd.Series(["OK"] * len(nivel_agg))

    df = nivel_agg.sort_values("minute").copy()
    df["delta_level_pct"] = df["avg_level"].diff()
    df["delta_vol_m3_nivel"] = (df["delta_level_pct"] / 100.0) * \
                                NIVEL_MAXIMO_M * AREA_TANQUE_M2

    df = df.merge(
        flow_total_agg[["minute", "flow_total_m3_h"]],
        on="minute", how="left"
    )
    df["flow_total_m3_h"] = df["flow_total_m3_h"].fillna(0)

    # Volume esperado = vazão total × 1 minuto (em m³)
    df["delta_vol_m3_esperado"] = df["flow_total_m3_h"] / 60.0

    def balance_flag(row):
        esperado = row["delta_vol_m3_esperado"]
        real     = row["delta_vol_m3_nivel"]
        if pd.isna(real) or esperado == 0:
            return "OK"
        divergencia = abs(esperado - real) / (abs(esperado) + 1e-9)
        return "DIVERGENTE" if divergencia > MASS_BALANCE_TOLERANCE else "OK"

    return df.apply(balance_flag, axis=1).values

# ==========================================
# CONSTRUÇÃO DO REFINED
# ==========================================

def build_refined(platform_id, tank_id, df_trusted, pipe_baselines):
    """
    Monta o DataFrame refined para um tanque específico.
    pipe_baselines: dict {pipe_id: baseline_flow_m3h} calculado
                    sobre o histórico completo do trusted.
    """
    df_nivel, df_vazao = split_sensors(df_trusted)

    nivel_agg              = aggregate_nivel_by_minute(df_nivel)
    df_per_pipe, flow_agg  = aggregate_vazao_by_minute(df_vazao)

    if nivel_agg.empty:
        return pd.DataFrame()

    # TTC
    nivel_agg["ttc_hours"] = compute_ttc(nivel_agg).values

    # Flags de anomalia
    nivel_agg["leak_flag"]      = detect_leak(nivel_agg, flow_agg)
    nivel_agg["mass_balance"]   = compute_mass_balance(nivel_agg, flow_agg)

    # Junta vazão total
    if not flow_agg.empty:
        nivel_agg = nivel_agg.merge(
            flow_agg[["minute", "flow_total_m3_h", "active_pipes"]],
            on="minute", how="left"
        )
    else:
        nivel_agg["flow_total_m3_h"] = None
        nivel_agg["active_pipes"]    = 0

    # Status do tanque por janela
    nivel_agg["tank_status"] = nivel_agg.apply(
        lambda r: classify_tank_status(r["avg_level"], r["ttc_hours"]), axis=1
    )

    # Status de cada cano (serializado como JSON para a linha do tanque)
    pipe_status_by_minute = {}
    if not df_per_pipe.empty:
        for _, row in df_per_pipe.iterrows():
            minute   = row["minute"]
            pipe_id  = row["pipe_id"]
            baseline = pipe_baselines.get(pipe_id)
            status   = classify_pipe_status(row["avg_flow_pipe"], baseline)
            pipe_status_by_minute.setdefault(minute, {})[pipe_id] = status

    nivel_agg["pipe_statuses"] = nivel_agg["minute"].apply(
        lambda m: json.dumps(pipe_status_by_minute.get(m, {}), ensure_ascii=False)
    )

    # Pior status de cano na janela
    def worst_pipe_status(statuses_json):
        s = json.loads(statuses_json)
        if not s:
            return "NORMAL"
        vals = list(s.values())
        if "ENTUPIDO"  in vals: return "ENTUPIDO"
        if "DEGRADADO" in vals: return "DEGRADADO"
        return "NORMAL"

    nivel_agg["worst_pipe_status"] = nivel_agg["pipe_statuses"].apply(
        worst_pipe_status)

    # overall_status — consolida tudo
    def overall(row):
        if row["tank_status"] == "CRÍTICO":
            return "CRÍTICO"
        if row["leak_flag"] or row["mass_balance"] == "DIVERGENTE":
            return "CRÍTICO"
        if row["tank_status"] == "ATENÇÃO":
            return "ATENÇÃO"
        if row["worst_pipe_status"] in ("ENTUPIDO", "DEGRADADO"):
            return "ATENÇÃO"
        return "NORMAL"

    nivel_agg["overall_status"] = nivel_agg.apply(overall, axis=1)

    # Monta DataFrame final
    records = nivel_agg.rename(columns={"minute": "window_start"}).copy()
    records["platform_id"] = platform_id
    records["tank_id"]     = tank_id

    output_cols = [
        "window_start",
        "platform_id",
        "tank_id",
        "side",
        "avg_level",
        "min_level",
        "max_level",
        "ttc_hours",
        "flow_total_m3_h",
        "active_pipes",
        "pipe_statuses",
        "worst_pipe_status",
        "tank_status",
        "leak_flag",
        "mass_balance",
        "overall_status",
        "n_readings",
    ]
    return records[[c for c in output_cols if c in records.columns]]

# ==========================================
# BASELINE DOS CANOS
# ==========================================

def compute_pipe_baselines(trusted_dir, platform_id, tank_id):
    """
    Lê o trusted completo do tanque para calcular a média histórica
    de cada cano — usada como referência para detectar entupimento.
    """
    path = os.path.join(trusted_dir, platform_id, f"{tank_id}.csv")
    if not os.path.exists(path):
        return {}

    df = pd.read_csv(path, parse_dates=["timestamp"], encoding="utf-8-sig", encoding_errors="replace")
    df_vazao = df[df["sensor_type"] == "VAZAO"].copy()

    if df_vazao.empty:
        return {}

    df_vazao["flow_rate_m3_h"] = pd.to_numeric(
        df_vazao["flow_rate_m3_h"], errors="coerce")

    # Baseline = média do primeiro quartil temporal de cada cano
    # (primeiras leituras quando o cano ainda estava normal)
    baselines = {}
    for pipe_id, group in df_vazao.groupby("pipe_id"):
        group = group.sort_values("timestamp")
        q1_len = max(1, len(group) // 4)
        baselines[pipe_id] = group.head(q1_len)["flow_rate_m3_h"].mean()

    return baselines

# ==========================================
# PERSISTÊNCIA NO REFINED
# ==========================================

def save_refined(df, platform_id, tank_id):
    """
    Salva em estrutura particionada compatível com Glue/Athena.
    Partição: platform_id=FPSO-01/tank_id=TK-01/refined.csv
    """
    part_dir = os.path.join(
        REFINED_DIR,
        f"platform_id={platform_id}",
        f"tank_id={tank_id}",
    )
    os.makedirs(part_dir, exist_ok=True)
    out_path = os.path.join(part_dir, "refined.csv")

    write_header = not os.path.exists(out_path)
    df["window_start"] = df["window_start"].astype(str)
    df.to_csv(out_path, mode="a", header=write_header, index=False, encoding="utf-8-sig")
    return out_path

# ==========================================
# LOOP PRINCIPAL
# ==========================================

def main():
    print("=" * 55)
    print(" DeepWatch — ETL 2: Trusted → Refined")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 55)

    offset = load_offset()
    files  = discover_trusted_files(TRUSTED_DIR)

    if not files:
        print("[AVISO] Nenhum arquivo trusted encontrado.")
        sys.exit(0)

    total_windows  = 0
    tanks_updated  = 0
    status_summary = {"CRÍTICO": 0, "ATENÇÃO": 0, "NORMAL": 0}

    for file_info in files:
        platform_id = file_info["platform_id"]
        tank_id     = file_info["tank_id"]

        df_new, new_offset = read_new_rows(file_info, offset)

        if df_new is None or len(df_new) == 0:
            continue

        # Baseline calculado sobre histórico completo (não só dados novos)
        pipe_baselines = compute_pipe_baselines(
            TRUSTED_DIR, platform_id, tank_id)

        # Processa apenas os dados novos
        df_refined = build_refined(
            platform_id, tank_id, df_new, pipe_baselines)

        if df_refined.empty:
            key = offset_key(platform_id, tank_id)
            offset[key] = new_offset
            continue

        save_refined(df_refined, platform_id, tank_id)

        key = offset_key(platform_id, tank_id)
        offset[key] = new_offset

        n_windows = len(df_refined)
        total_windows += n_windows
        tanks_updated += 1

        for status in df_refined["overall_status"]:
            if status in status_summary:
                status_summary[status] += 1

        # Log por tanque
        last = df_refined.iloc[-1]
        ttc_str = (f"{last['ttc_hours']:.1f}h"
                   if pd.notna(last.get("ttc_hours")) else "N/A")
        print(
            f"  {platform_id}/{tank_id} — "
            f"{n_windows} janelas | "
            f"nível: {last['avg_level']:.1f}% | "
            f"TTC: {ttc_str} | "
            f"status: {last['overall_status']}"
        )

    save_offset(offset)

    # ---- Relatório final ----
    print(f"\n  Tanques atualizados  : {tanks_updated}")
    print(f"  Janelas geradas      : {total_windows}")
    print(f"  🔴 CRÍTICO  : {status_summary['CRÍTICO']}")
    print(f"  🟡 ATENÇÃO  : {status_summary['ATENÇÃO']}")
    print(f"  🟢 NORMAL   : {status_summary['NORMAL']}")

    if total_windows == 0:
        print("\n  Nenhum dado novo. Refined já está atualizado.")
    else:
        print(f"\n  Refined salvo em: {REFINED_DIR}")

    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()