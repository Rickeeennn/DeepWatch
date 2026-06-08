"""
DeepWatch – testar_pipeline.py
Demonstração local do pipeline completo sem necessidade de AWS.

O que este script faz:
  1. Gera dados Bronze realistas para 3 tanques (30 minutos de leituras)
  2. Injeta 4 anomalias para demonstrar a detecção de segurança
  3. Roda Bronze → Silver (com validação física)
  4. Roda Silver → Gold (com insights preditivos)
  5. Roda o Monitor de pipeline
  6. Salva todos os CSVs de saída em saidas/
  7. Gera um relatório completo em saidas/relatorio.txt

Como usar:
  cd deepwatch-poc/teste_local
  python testar_pipeline.py

Outputs gerados em saidas/:
  bronze_nivel.csv          ← dados brutos do sensor de nível
  bronze_vazao.csv          ← dados brutos do sensor de vazão
  silver.csv                ← após limpeza + validação + balanço de massa
  gold.csv                  ← insights preditivos por tanque
  security_events.csv       ← anomalias detectadas (se houver)
  relatorio.txt             ← relatório completo da execução
"""

import os
import sys
import math
import numpy as np
import pandas as pd
from collections import deque
from datetime import datetime, timedelta
from scipy.signal import butter, lfilter, lfilter_zi

# ── Garante que sensor_validator.py seja encontrado ──────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sensor_validator import (
    EstadoAnterior,
    calcular_balanco_massa,
    validar_leitura_completa,
)

# ─── Configuração ────────────────────────────────────────────────
PLATFORM_ID      = "FPSO-P67"
TANK_CAPACITY_M3 = 10000.0
DURACAO_MINUTOS  = 30       # minutos de dados a gerar
LEITURAS_POR_MIN = 1        # 1 leitura por minuto (já filtrada)

DADOS_DIR  = os.path.join(os.path.dirname(__file__), "dados")
SAIDAS_DIR = os.path.join(os.path.dirname(__file__), "saidas")
os.makedirs(DADOS_DIR,  exist_ok=True)
os.makedirs(SAIDAS_DIR, exist_ok=True)

# ─── Parâmetros dos tanques ───────────────────────────────────────
# Cada tanque tem nível inicial e vazão distintos para gerar
# dados variados e realistas
TANQUES = [
    {"id": "T-01", "nivel_inicial_pct": 91.0, "vazao_m3h": 69.0},   # crítico
    {"id": "T-02", "nivel_inicial_pct": 78.0, "vazao_m3h": 95.0},   # atenção
    {"id": "T-03", "nivel_inicial_pct": 45.0, "vazao_m3h": 60.0},   # normal
]

# ─── Anomalias injetadas para demonstração ───────────────────────
# Cada anomalia tem: tanque, minuto da injeção, tipo e valor injetado
ANOMALIAS = [
    {
        "tank_id":  "T-01",
        "minuto":   10,
        "tipo":     "VARIACAO_NIVEL_IMPOSSIVEL",
        "descricao":"Nível salta de ~92% para 62% em 1 minuto",
        "nivel_injetado": 62.0,
        "vazao_injetada": 69.0,
    },
    {
        "tank_id":  "T-02",
        "minuto":   15,
        "tipo":     "VALOR_FORA_RANGE_FISICO",
        "descricao":"Nível reportado como 150% (impossível fisicamente)",
        "nivel_injetado": 150.0,
        "vazao_injetada": 95.0,
    },
    {
        "tank_id":  "T-03",
        "minuto":   20,
        "tipo":     "TIMESTAMP_ATRASADO",
        "descricao":"Leitura reenviada com timestamp de 10 minutos atrás (replay attack)",
        "nivel_injetado": 46.0,
        "vazao_injetada": 60.0,
        "timestamp_offset_min": -10,   # 10 minutos no passado
    },
    {
        "tank_id":  "T-01",
        "minuto":   25,
        "tipo":     "VARIACAO_VAZAO_SUSPEITA",
        "descricao":"Vazão cai de ~69 para 5 m³/h em 1 minuto (queda de 93%)",
        "nivel_injetado": 92.5,
        "vazao_injetada": 5.0,
    },
]

# ─── Relatório global ─────────────────────────────────────────────
linhas_relatorio = []

def log(msg: str, indent: int = 0):
    linha = "  " * indent + msg
    print(linha)
    linhas_relatorio.append(linha)


# ═══════════════════════════════════════════════════════════════════
# FASE 1 — GERAÇÃO DOS DADOS BRONZE
# ═══════════════════════════════════════════════════════════════════

def gerar_bronze() -> tuple:
    """
    Gera leituras de nível e vazão para cada tanque ao longo de
    DURACAO_MINUTOS minutos. Injeta anomalias nos minutos configurados.
    """
    log("=" * 60)
    log("FASE 1 — Geração dos dados Bronze (simuladores)")
    log("=" * 60)

    # Índice de anomalias por tanque e minuto para acesso rápido
    anomalias_idx = {
        (a["tank_id"], a["minuto"]): a for a in ANOMALIAS
    }

    # Configuração do filtro Butterworth (nível)
    b, a = butter(4, 0.01, btype="low", analog=False)

    linhas_nivel = []
    linhas_vazao = []
    base_time    = datetime.utcnow().replace(second=0, microsecond=0)

    for tank in TANQUES:
        tank_id       = tank["id"]
        nivel_pct     = tank["nivel_inicial_pct"]
        vazao_h       = tank["vazao_m3h"]
        taxa_pct_min  = (vazao_h / TANK_CAPACITY_M3) * 100  # %/min

        # Estado inicial do filtro
        nivel_m       = nivel_pct * 100 / 100   # simples — nível em metros proporcionais
        zi            = lfilter_zi(b, a) * nivel_m
        estado_filtro = zi.copy()

        log(f"\n  Tanque {tank_id}:")
        log(f"    Nível inicial : {nivel_pct}%", 1)
        log(f"    Vazão         : {vazao_h} m³/h", 1)
        log(f"    Taxa          : {taxa_pct_min:.4f}%/min", 1)

        for minuto in range(DURACAO_MINUTOS):
            ts = base_time + timedelta(minutes=minuto)

            # Verifica se há anomalia neste minuto
            anomalia = anomalias_idx.get((tank_id, minuto))

            if anomalia and "timestamp_offset_min" in anomalia:
                # Replay attack: timestamp no passado
                ts_anomalia = ts + timedelta(minutes=anomalia["timestamp_offset_min"])
                linhas_nivel.append({
                    "timestamp":           ts_anomalia.strftime("%Y-%m-%dT%H:%M:%S"),
                    "platform_id":         PLATFORM_ID,
                    "tank_id":             tank_id,
                    "tank_level_percent":  anomalia["nivel_injetado"],
                })
                linhas_vazao.append({
                    "timestamp":    ts_anomalia.strftime("%Y-%m-%dT%H:%M:%S"),
                    "platform_id":  PLATFORM_ID,
                    "tank_id":      tank_id,
                    "flow_rate_m3_h": anomalia["vazao_injetada"],
                })
                log(f"    [ANOMALIA injetada min={minuto}] {anomalia['tipo']}", 1)
                log(f"      → {anomalia['descricao']}", 1)
                continue

            if anomalia:
                # Anomalia de valor ou variação
                linhas_nivel.append({
                    "timestamp":           ts.strftime("%Y-%m-%dT%H:%M:%S"),
                    "platform_id":         PLATFORM_ID,
                    "tank_id":             tank_id,
                    "tank_level_percent":  anomalia["nivel_injetado"],
                })
                linhas_vazao.append({
                    "timestamp":      ts.strftime("%Y-%m-%dT%H:%M:%S"),
                    "platform_id":    PLATFORM_ID,
                    "tank_id":        tank_id,
                    "flow_rate_m3_h": anomalia["vazao_injetada"],
                })
                log(f"    [ANOMALIA injetada min={minuto}] {anomalia['tipo']}", 1)
                log(f"      → {anomalia['descricao']}", 1)
                continue

            # Leitura normal: nível sobe pela taxa da vazão + ruído
            nivel_pct = min(99.9, nivel_pct + taxa_pct_min + np.random.normal(0, 0.02))
            vazao_h_atual = round(vazao_h + np.random.normal(0, 0.5), 4)

            linhas_nivel.append({
                "timestamp":           ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "platform_id":         PLATFORM_ID,
                "tank_id":             tank_id,
                "tank_level_percent":  round(nivel_pct, 4),
            })
            linhas_vazao.append({
                "timestamp":      ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "platform_id":    PLATFORM_ID,
                "tank_id":        tank_id,
                "flow_rate_m3_h": vazao_h_atual,
            })

    df_nivel = pd.DataFrame(linhas_nivel)
    df_vazao = pd.DataFrame(linhas_vazao)

    # Salva Bronze localmente
    path_nivel = os.path.join(SAIDAS_DIR, "bronze_nivel.csv")
    path_vazao = os.path.join(SAIDAS_DIR, "bronze_vazao.csv")
    df_nivel.to_csv(path_nivel, index=False)
    df_vazao.to_csv(path_vazao, index=False)

    log(f"\n  Bronze gerado:")
    log(f"    {path_nivel}  ({len(df_nivel)} linhas)", 1)
    log(f"    {path_vazao}  ({len(df_vazao)} linhas)", 1)

    return df_nivel, df_vazao


# ═══════════════════════════════════════════════════════════════════
# FASE 2 — BRONZE → SILVER
# ═══════════════════════════════════════════════════════════════════

def bronze_para_silver(df_nivel: pd.DataFrame,
                       df_vazao: pd.DataFrame) -> pd.DataFrame:
    log("\n" + "=" * 60)
    log("FASE 2 — Bronze → Silver (limpeza + segurança + balanço de massa)")
    log("=" * 60)

    # Converte timestamps
    df_nivel["timestamp"] = pd.to_datetime(df_nivel["timestamp"], errors="coerce")
    df_vazao["timestamp"] = pd.to_datetime(df_vazao["timestamp"], errors="coerce")

    # Merge pelo timestamp mais próximo (tolerância 90s)
    df_nivel = df_nivel.sort_values("timestamp")
    df_vazao = df_vazao.sort_values("timestamp")

    df = pd.merge_asof(
        df_nivel, df_vazao[["timestamp", "platform_id", "tank_id", "flow_rate_m3_h"]],
        on="timestamp", by=["platform_id", "tank_id"],
        tolerance=pd.Timedelta("90s"), direction="nearest"
    ).dropna(subset=["flow_rate_m3_h"]).reset_index(drop=True)

    log(f"\n  Merge nivel + vazão: {len(df)} linhas combinadas")

    # Limpeza básica
    antes = len(df)
    df    = df.drop_duplicates(subset=["timestamp", "platform_id", "tank_id"])
    dupl  = antes - len(df)

    fora = (
        (df["tank_level_percent"] < 0)  | (df["tank_level_percent"] > 100) |
        (df["flow_rate_m3_h"]    < 0)   | (df["flow_rate_m3_h"]    > 5000)
    )
    df_fora  = df[fora].copy()
    df       = df[~fora].copy()

    log(f"  Duplicatas removidas      : {dupl}")
    log(f"  Fora de faixa removidos   : {len(df_fora)}")
    for _, row in df_fora.iterrows():
        log(f"    → {row['tank_id']} | nível={row['tank_level_percent']}% "
            f"| vazão={row['flow_rate_m3_h']} m³/h", 1)

    # Validação física — detecção de anomalias
    # Modo local: valida faixa física e variação física, mas NÃO valida timestamp
    # (dados históricos gerados localmente não passariam pela janela de 5 minutos)
    log("\n  Validação física (detecção de injeção de dados):")
    df      = df.sort_values(["platform_id", "tank_id", "timestamp"]).copy()
    estados = {}
    rejeitados_idx  = []
    eventos_seg     = []

    for idx, row in df.iterrows():
        chave      = f"{row['platform_id']}_{row['tank_id']}"
        estado_ant = estados.get(chave)

        from sensor_validator import validar_faixa_fisica, validar_variacao_fisica, ResultadoValidacao

        # 1. Valida faixa física
        resultado = validar_faixa_fisica(
            float(row["tank_level_percent"]),
            float(row["flow_rate_m3_h"])
        )

        # 2. Valida variação física (se passou na faixa e tem estado anterior)
        if resultado.valida and estado_ant is not None:
            delta_min = (row["timestamp"].to_pydatetime() - estado_ant.timestamp).total_seconds() / 60
            if delta_min > 0:
                resultado = validar_variacao_fisica(
                    float(row["tank_level_percent"]),
                    float(row["flow_rate_m3_h"]),
                    estado_ant,
                    delta_min
                )

        if not resultado.valida:
            rejeitados_idx.append(idx)
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
            log(f"    🔴 REJEITADO [{resultado.tipo_evento}]", 1)
            log(f"       {row['tank_id']} | {resultado.motivo}", 1)
        else:
            estados[chave] = EstadoAnterior(
                nivel     = float(row["tank_level_percent"]),
                vazao     = float(row["flow_rate_m3_h"]),
                timestamp = row["timestamp"].to_pydatetime()
            )

    df = df.drop(index=rejeitados_idx).reset_index(drop=True)
    log(f"\n  Leituras rejeitadas (física): {len(rejeitados_idx)}")
    log(f"  Eventos de segurança        : {len(eventos_seg)}")

    # Balanço de massa por leitura
    df["mass_balance_deviation_pct"] = 0.0
    for _, grupo in df.groupby(["platform_id", "tank_id"]):
        grupo = grupo.sort_values("timestamp")
        dn    = grupo["tank_level_percent"].diff()
        dt    = grupo["timestamp"].diff().dt.total_seconds().div(60)
        vi    = grupo["flow_rate_m3_h"]
        devs  = []
        for i in range(len(grupo)):
            if i == 0 or pd.isna(dt.iloc[i]):
                devs.append(0.0)
            else:
                devs.append(calcular_balanco_massa(
                    float(dn.iloc[i]), float(vi.iloc[i]),
                    0.0, TANK_CAPACITY_M3, float(dt.iloc[i])
                ))
        df.loc[grupo.index, "mass_balance_deviation_pct"] = devs

    # Salva Silver
    df_silver = df[[
        "timestamp", "platform_id", "tank_id",
        "flow_rate_m3_h", "tank_level_percent",
        "mass_balance_deviation_pct"
    ]].copy()
    df_silver["timestamp"] = df_silver["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")

    path_silver = os.path.join(SAIDAS_DIR, "silver.csv")
    df_silver.to_csv(path_silver, index=False)

    # Salva eventos de segurança
    if eventos_seg:
        path_sec = os.path.join(SAIDAS_DIR, "security_events.csv")
        pd.DataFrame(eventos_seg).to_csv(path_sec, index=False)
        log(f"\n  ⚠ Eventos de segurança salvos em: {path_sec}")

    log(f"\n  Silver salvo: {path_silver}  ({len(df_silver)} linhas)")
    return df_silver


# ═══════════════════════════════════════════════════════════════════
# FASE 3 — SILVER → GOLD
# ═══════════════════════════════════════════════════════════════════

def silver_para_gold(df_silver: pd.DataFrame) -> pd.DataFrame:
    log("\n" + "=" * 60)
    log("FASE 3 — Silver → Gold (insights preditivos)")
    log("=" * 60)

    df_silver["timestamp"] = pd.to_datetime(df_silver["timestamp"])
    registros = []

    for (platform_id, tank_id), grupo in df_silver.groupby(["platform_id", "tank_id"]):
        grupo  = grupo.sort_values("timestamp")
        ultimo = grupo.iloc[-1]

        nivel_atual  = float(ultimo["tank_level_percent"])
        vazao_atual  = float(ultimo["flow_rate_m3_h"])
        nivel_medio  = round(grupo["tank_level_percent"].mean(), 4)
        vazao_media  = round(grupo["flow_rate_m3_h"].mean(), 4)

        # TTC por regressão linear (usa os dois sensores)
        ttc_h = None
        taxa_h = None
        confianca = "baixa"
        if len(grupo) >= 3:
            t0      = grupo["timestamp"].iloc[0]
            minutos = (grupo["timestamp"] - t0).dt.total_seconds().div(60).values
            niveis  = grupo["tank_level_percent"].values
            coef    = np.polyfit(minutos, niveis, 1)
            taxa_min = coef[0]
            taxa_h   = round(taxa_min * 60, 4)
            if taxa_min > 0:
                ttc_min = (95 - nivel_atual) / taxa_min
                ttc_h   = round(ttc_min / 60, 2)
                # Valida contra vazão
                taxa_vazao = (vazao_media / TANK_CAPACITY_M3) * 100
                razao      = abs(taxa_h / taxa_vazao) if taxa_vazao > 0 else 0
                confianca  = "alta" if 0.5 <= razao <= 1.5 else "media"

        # Balanço de massa agregado
        bal_medio = round(grupo["mass_balance_deviation_pct"].mean(), 4)
        bal_max   = round(grupo["mass_balance_deviation_pct"].max(), 4)

        # Status
        s_nivel   = "CRÍTICO" if nivel_atual >= 90 else "ATENÇÃO" if nivel_atual >= 75 else "NORMAL"
        s_ttc     = "NORMAL" if ttc_h is None else "CRÍTICO" if ttc_h < 10 else "ATENÇÃO" if ttc_h < 30 else "NORMAL"
        s_balanco = "CRÍTICO" if bal_medio >= 2 else "ATENÇÃO" if bal_medio >= 1 else "NORMAL"

        prioridade    = {"CRÍTICO": 0, "ATENÇÃO": 1, "NORMAL": 2}
        status_global = min([s_nivel, s_ttc, s_balanco], key=lambda s: prioridade[s])

        # Alerta preditivo
        alertas = []
        if ttc_h is not None:
            if   ttc_h < 6:  alertas.append(f"SHUT-IN IMINENTE: {ttc_h:.1f}h")
            elif ttc_h < 10: alertas.append(f"TTC CRÍTICO: {ttc_h:.1f}h")
            elif ttc_h < 30: alertas.append(f"TTC atenção: {ttc_h:.1f}h")
        if bal_medio >= 2:
            alertas.append(f"INCONSISTÊNCIA balanço: {bal_medio:.1f}%")
        elif bal_medio >= 1:
            alertas.append(f"Balanço atenção: {bal_medio:.1f}%")

        registros.append({
            "platform_id":                    platform_id,
            "tank_id":                        tank_id,
            "total_readings":                 len(grupo),
            "current_level_percent":          round(nivel_atual, 4),
            "avg_level_percent":              nivel_medio,
            "current_flow_m3_h":              round(vazao_atual, 4),
            "avg_flow_m3_h":                  vazao_media,
            "level_fill_rate_pct_h":          taxa_h,
            "ttc_hours":                      ttc_h,
            "ttc_confidence":                 confianca,
            "mass_balance_deviation_avg_pct": bal_medio,
            "mass_balance_deviation_max_pct": bal_max,
            "status_nivel":                   s_nivel,
            "status_ttc":                     s_ttc,
            "status_balanco_massa":           s_balanco,
            "overall_status":                 status_global,
            "alerta_preditivo":               " | ".join(alertas) if alertas else "OK",
            "processed_at":                   datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    df_gold = pd.DataFrame(registros)
    df_gold = df_gold.sort_values("ttc_hours", na_position="last")

    path_gold = os.path.join(SAIDAS_DIR, "gold.csv")
    df_gold.to_csv(path_gold, index=False)

    log(f"\n  Tanques processados: {len(df_gold)}")
    for _, row in df_gold.iterrows():
        ttc_str = f"{row['ttc_hours']}h" if pd.notna(row["ttc_hours"]) else "N/A"
        icone   = "🔴" if row["overall_status"] == "CRÍTICO" else "🟡" if row["overall_status"] == "ATENÇÃO" else "🟢"
        log(f"\n  {icone} {row['tank_id']} — {row['overall_status']}")
        log(f"     Nível  : {row['current_level_percent']}%  ({row['status_nivel']})", 1)
        log(f"     Vazão  : {row['current_flow_m3_h']} m³/h", 1)
        log(f"     TTC    : {ttc_str}  ({row['ttc_confidence']}) ({row['status_ttc']})", 1)
        log(f"     Balanço: {row['mass_balance_deviation_avg_pct']}%  ({row['status_balanco_massa']})", 1)
        if row["alerta_preditivo"] != "OK":
            log(f"     ⚠ {row['alerta_preditivo']}", 1)

    log(f"\n  Gold salvo: {path_gold}")
    return df_gold


# ═══════════════════════════════════════════════════════════════════
# FASE 4 — MONITOR DE PIPELINE
# ═══════════════════════════════════════════════════════════════════

def monitor_local(df_nivel, df_vazao, df_silver, df_gold):
    log("\n" + "=" * 60)
    log("FASE 4 — Monitor de Pipeline (saúde)")
    log("=" * 60)

    sec_path = os.path.join(SAIDAS_DIR, "security_events.csv")
    n_eventos = len(pd.read_csv(sec_path)) if os.path.exists(sec_path) else 0

    checks = [
        ("bronze_nivel",      "🟢" if len(df_nivel) > 0 else "🔴",
         f"{len(df_nivel)} leituras disponíveis"),
        ("bronze_vazao",      "🟢" if len(df_vazao) > 0 else "🔴",
         f"{len(df_vazao)} leituras disponíveis"),
        ("silver_limpeza",    "🟢", f"{len(df_silver)} registros após limpeza e validação"),
        ("security_events",   "🔴" if n_eventos >= 5 else "🟡" if n_eventos > 0 else "🟢",
         f"{n_eventos} evento(s) de segurança detectados"),
        ("gold_criticos",
         "🔴" if (df_gold["overall_status"] == "CRÍTICO").any() else
         "🟡" if (df_gold["overall_status"] == "ATENÇÃO").any() else "🟢",
         f"{(df_gold['overall_status'] == 'CRÍTICO').sum()} crítico(s), "
         f"{(df_gold['overall_status'] == 'ATENÇÃO').sum()} em atenção"),
    ]

    for nome, icone, msg in checks:
        log(f"  {icone} [{nome}] {msg}")


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    ts_inicio = datetime.utcnow()

    log("DeepWatch – Teste Local do Pipeline")
    log(f"Início: {ts_inicio.strftime('%Y-%m-%dT%H:%M:%SZ')}")
    log(f"Plataforma: {PLATFORM_ID}  |  Tanques: {len(TANQUES)}  |  Duração: {DURACAO_MINUTOS} minutos")
    log(f"Anomalias injetadas: {len(ANOMALIAS)}")

    # Executa as fases
    df_nivel              = gerar_bronze()
    df_vazao_raw          = pd.read_csv(os.path.join(SAIDAS_DIR, "bronze_vazao.csv"))
    df_nivel_raw          = pd.read_csv(os.path.join(SAIDAS_DIR, "bronze_nivel.csv"))

    df_silver             = bronze_para_silver(df_nivel_raw, df_vazao_raw)
    df_gold               = silver_para_gold(df_silver)

    monitor_local(df_nivel_raw, df_vazao_raw, df_silver, df_gold)

    # Relatório final
    ts_fim    = datetime.utcnow()
    duracao_s = (ts_fim - ts_inicio).total_seconds()

    log("\n" + "=" * 60)
    log("RESUMO FINAL")
    log("=" * 60)
    log(f"  Tempo de execução  : {duracao_s:.2f}s")
    log(f"  Leituras Bronze    : {len(df_nivel_raw)} nível + {len(df_vazao_raw)} vazão")
    log(f"  Registros Silver   : {len(df_silver)}")
    log(f"  Tanques no Gold    : {len(df_gold)}")

    sec_path = os.path.join(SAIDAS_DIR, "security_events.csv")
    n_ev = len(pd.read_csv(sec_path)) if os.path.exists(sec_path) else 0
    log(f"  Eventos segurança  : {n_ev}")
    log(f"\n  Arquivos gerados em: {SAIDAS_DIR}/")
    for f in sorted(os.listdir(SAIDAS_DIR)):
        size = os.path.getsize(os.path.join(SAIDAS_DIR, f))
        log(f"    {f:<35} {size:>6} bytes")

    # Salva relatório em txt
    path_rel = os.path.join(SAIDAS_DIR, "relatorio.txt")
    with open(path_rel, "w", encoding="utf-8") as f:
        f.write("\n".join(linhas_relatorio))
    log(f"\n  Relatório salvo: {path_rel}")
    log("=" * 60)


if __name__ == "__main__":
    main()
