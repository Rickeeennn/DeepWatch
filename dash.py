import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import math

st.set_page_config(
    page_title="DeepWatch",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

C_BG       = "#0E1113"
C_CARD     = "#14181B"
C_CYAN     = "#25C0C3"
C_GREEN    = "#2B8C69"
C_YELLOW   = "#D8B02D"
C_RED      = "#D75A5A"
C_TEXT     = "#E8EAED"
C_SUBTEXT  = "#8A9BAE"
C_ORANGE   = "#E8732A"

st.markdown(f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Exo+2:wght@300;400;600;700&display=swap');

  html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {{
      background-color: {C_BG} !important;
      color: {C_TEXT} !important;
      font-family: 'Exo 2', sans-serif;
  }}
  [data-testid="stSidebar"] {{
      background-color: {C_CARD} !important;
      border-right: 1px solid #1E2530;
  }}
  [data-testid="stSidebar"] * {{ color: {C_TEXT} !important; }}

  h1, h2, h3, h4 {{ font-family: 'Exo 2', sans-serif; font-weight: 700; color: {C_TEXT}; }}

  [data-testid="metric-container"] {{
      background: {C_CARD};
      border: 1px solid #1E2530;
      border-radius: 8px;
      padding: 12px 16px;
  }}
  [data-testid="stMetricValue"] {{ color: {C_CYAN} !important; font-family: 'Share Tech Mono', monospace; font-size: 1.6rem !important; }}
  [data-testid="stMetricLabel"] {{ color: {C_SUBTEXT} !important; font-size: 0.75rem !important; text-transform: uppercase; letter-spacing: 0.08em; }}
  [data-testid="stMetricDelta"] {{ font-size: 0.8rem !important; }}

  /* Destaque para métricas críticas e de alerta */
  [data-testid="metric-container"].metric-crit {{
      background: rgba(215,90,90,0.12) !important;
      border: 1px solid {C_RED} !important;
      box-shadow: 0 0 12px rgba(215,90,90,0.25);
  }}
  [data-testid="metric-container"].metric-crit [data-testid="stMetricValue"] {{
      color: {C_RED} !important;
  }}
  [data-testid="metric-container"].metric-warn {{
      background: rgba(216,176,45,0.12) !important;
      border: 1px solid {C_YELLOW} !important;
      box-shadow: 0 0 12px rgba(216,176,45,0.2);
  }}
  [data-testid="metric-container"].metric-warn [data-testid="stMetricValue"] {{
      color: {C_YELLOW} !important;
  }}

  .stButton > button {{
      background: transparent;
      border: 1px solid {C_CYAN};
      color: {C_CYAN};
      border-radius: 4px;
      font-family: 'Share Tech Mono', monospace;
      font-size: 0.8rem;
      letter-spacing: 0.05em;
      transition: all 0.2s;
  }}
  .stButton > button:hover {{
      background: {C_CYAN};
      color: {C_BG};
  }}

  .stSelectbox > div > div {{
      background: {C_CARD} !important;
      border: 1px solid #2A3545 !important;
      color: {C_TEXT} !important;
      border-radius: 4px;
  }}

  .stRadio > div {{ flex-direction: row; gap: 12px; }}
  .stRadio label {{ color: {C_SUBTEXT} !important; font-size: 0.8rem; }}

  .stDataFrame {{ border-radius: 8px; overflow: hidden; }}
  [data-testid="stDataFrame"] > div {{ background: {C_CARD}; }}

  hr {{ border-color: #1E2530; }}

  ::-webkit-scrollbar {{ width: 4px; }}
  ::-webkit-scrollbar-track {{ background: {C_BG}; }}
  ::-webkit-scrollbar-thumb {{ background: #2A3545; border-radius: 2px; }}

  .block-container {{ padding-top: 2.5rem; padding-bottom: 5rem; }}

  .sidebar-logo {{
      font-family: 'Share Tech Mono', monospace;
      font-size: 1.4rem;
      color: {C_TEXT};
      letter-spacing: 0.12em;
      padding: 8px 0 4px 0;
  }}
  .sidebar-logo span {{
      color: {C_ORANGE};
  }}
  .sidebar-sub {{
      font-size: 0.65rem;
      color: {C_SUBTEXT};
      letter-spacing: 0.15em;
      text-transform: uppercase;
      margin-bottom: 16px;
  }}

  .tank-card {{
      background: {C_CARD};
      border-radius: 8px;
      padding: 16px;
      border: 1px solid #1E2530;
      text-align: center;
      cursor: pointer;
      transition: border-color 0.2s;
  }}
  .tank-card:hover {{ border-color: {C_CYAN}; }}
  .tank-card-crit {{
      background: rgba(215,90,90,0.08) !important;
      border: 1px solid {C_RED} !important;
      box-shadow: 0 0 14px rgba(215,90,90,0.2);
  }}
  .tank-card-warn {{
      background: rgba(216,176,45,0.08) !important;
      border: 1px solid {C_YELLOW} !important;
      box-shadow: 0 0 14px rgba(216,176,45,0.18);
  }}
  .tank-id {{
      font-family: 'Share Tech Mono', monospace;
      font-size: 1rem;
      color: {C_CYAN};
      margin-bottom: 4px;
  }}
  .tank-level {{
      font-size: 1.6rem;
      font-weight: 700;
      margin-bottom: 6px;
  }}
  .badge {{
      display: inline-block;
      padding: 2px 10px;
      border-radius: 20px;
      font-size: 0.65rem;
      font-family: 'Share Tech Mono', monospace;
      letter-spacing: 0.08em;
      text-transform: uppercase;
  }}
  .badge-ok {{ background: rgba(43,140,105,0.2); color: {C_GREEN}; border: 1px solid {C_GREEN}; }}
  .badge-warn {{ background: rgba(216,176,45,0.25); color: {C_YELLOW}; border: 1px solid {C_YELLOW}; font-weight: 700; }}
  .badge-crit {{ background: rgba(215,90,90,0.25); color: {C_RED}; border: 1px solid {C_RED}; font-weight: 700; animation: pulse-crit 1.6s ease-in-out infinite; }}

  @keyframes pulse-crit {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(215,90,90,0.4); }}
      50% {{ box-shadow: 0 0 0 5px rgba(215,90,90,0); }}
  }}

  .alert-box {{
      background: {C_CARD};
      border-radius: 6px;
      padding: 10px 14px;
      margin-bottom: 8px;
      border-left: 3px solid;
      font-size: 0.85rem;
  }}
  .alert-crit {{
      border-color: {C_RED};
      background: rgba(215,90,90,0.08);
      box-shadow: inset 3px 0 0 {C_RED};
  }}
  .alert-warn {{
      border-color: {C_YELLOW};
      background: rgba(216,176,45,0.07);
  }}
  .alert-ok   {{ border-color: {C_GREEN}; }}
  .alert-title {{ font-weight: 600; margin-bottom: 2px; }}
  .alert-msg {{ color: {C_SUBTEXT}; font-size: 0.78rem; }}

  .section-title {{
      font-size: 0.7rem;
      letter-spacing: 0.15em;
      text-transform: uppercase;
      color: {C_SUBTEXT};
      margin-bottom: 12px;
      padding-bottom: 6px;
      border-bottom: 1px solid #1E2530;
  }}

  .page-title {{
      font-family: 'Share Tech Mono', monospace;
      font-size: 1.5rem;
      color: {C_TEXT};
      margin-bottom: 4px;
  }}
  .page-title span {{
      color: {C_ORANGE};
  }}
  .page-subtitle {{
      font-size: 0.75rem;
      color: {C_SUBTEXT};
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 24px;
  }}

  /* Linha de status na tabela */
  .row-crit {{
      background: rgba(215,90,90,0.10) !important;
      color: {C_RED} !important;
  }}
  .row-warn {{
      background: rgba(216,176,45,0.08) !important;
      color: {C_YELLOW} !important;
  }}

  /* Botao fixo CSV canto inferior esquerdo */
  .csv-fixed-btn {{
      position: fixed;
      bottom: 24px;
      left: 24px;
      z-index: 9999;
      background: {C_CYAN};
      color: #000 !important;
      border: none;
      border-radius: 4px;
      padding: 10px 20px;
      font-family: 'Share Tech Mono', monospace;
      font-size: 0.8rem;
      letter-spacing: 0.08em;
      cursor: pointer;
      font-weight: 700;
      box-shadow: 0 4px 16px rgba(37,192,195,0.25);
      text-transform: uppercase;
      transition: opacity 0.2s;
  }}
  .csv-fixed-btn:hover {{ opacity: 0.85; }}
</style>
""", unsafe_allow_html=True)

@st.cache_data
def gerar_dados():
    np.random.seed(42)
    now = datetime.now().replace(second=0, microsecond=0)
    timestamps = [now - timedelta(minutes=i) for i in range(1440, 0, -1)]

    TANKS = [f"T{str(i).zfill(2)}" for i in range(1, 9)]
    PLATFORM = "FPSO-01"

    tank_trajectories = {
        "T01": [(0, 65), (300, 62), (600, 68), (900, 72), (1150, 75), (1440, 78)],
        "T04": [(0, 52), (400, 48), (800, 50), (1150, 53), (1440, 50)],
        "T06": [(0, 58), (400, 62), (800, 60), (1150, 55), (1440, 57)],
        "T07": [(0, 94), (1150, 94), (1260, 94), (1280, 94), (1300, 95),
                (1320, 96), (1340, 96), (1380, 95), (1440, 95)],
        "T03": [(0, 70), (1150, 70), (1260, 70), (1280, 66), (1300, 62),
                (1320, 58), (1340, 55), (1380, 68), (1440, 90)],
        "T08": [(0, 78), (1150, 78), (1260, 78), (1280, 62), (1300, 52),
                (1320, 40), (1340, 41), (1380, 44), (1440, 70)],
        "T05": [(0, 57), (1150, 57), (1260, 57), (1280, 45), (1300, 33),
                (1320, 50), (1340, 63), (1380, 58), (1440, 40)],
        "T02": [(0, 30), (1150, 30), (1260, 30), (1280, 38), (1300, 47),
                (1320, 46), (1340, 45), (1380, 42), (1440, 36)],
    }

    def interpolate_level(waypoints, minute):
        for j in range(len(waypoints) - 1):
            t0, l0 = waypoints[j]
            t1, l1 = waypoints[j + 1]
            if t0 <= minute <= t1:
                frac = (minute - t0) / (t1 - t0)
                return l0 + frac * (l1 - l0)
        return waypoints[-1][1]

    tank_rows = []
    for tid in TANKS:
        waypoints = tank_trajectories[tid]
        for i, ts in enumerate(timestamps):
            minute = 1440 - i
            noise = np.random.normal(0, 0.4)
            level = np.clip(interpolate_level(waypoints, minute) + noise, 28, 100)
            tank_rows.append({
                "timestamp": ts,
                "platform_id": PLATFORM,
                "tank_id": tid,
                "tank_level_percent": round(level, 2)
            })
    tank_df = pd.DataFrame(tank_rows)

    PIPES = [f"P{str(i).zfill(2)}" for i in range(1, 13)]
    pipe_tank_map = {
        "P01": "T01", "P02": "T01", "P03": "T02",
        "P04": "T02", "P05": "T03", "P06": "T03",
        "P07": "T04", "P08": "T05", "P09": "T05",
        "P10": "T06", "P11": "T07", "P12": "T08"
    }

    pipe_rows = []
    for pid in PIPES:
        tid = pipe_tank_map[pid]
        anomalo = pid == "P05"
        for ts in timestamps:
            if anomalo:
                flow = np.clip(np.random.normal(180, 15), 140, 220)
                press = np.clip(np.random.normal(95, 5), 85, 110)
            else:
                flow = np.clip(np.random.normal(650, 40), 500, 800)
                press = np.clip(np.random.normal(45, 4), 35, 60)
            pipe_rows.append({
                "timestamp": ts,
                "platform_id": PLATFORM,
                "pipe_id": pid,
                "tank_id": tid,
                "flow_rate_m3_h": round(flow, 2),
                "pressure_bar": round(press, 2)
            })
    pipe_df = pd.DataFrame(pipe_rows)

    return tank_df, pipe_df, pipe_tank_map

tank_df, pipe_df, pipe_tank_map = gerar_dados()

TANK_CAPACITY_M3 = 50000

def get_status(level):
    if level >= 95: return "CRÍTICO", "badge-crit", C_RED
    if level >= 85: return "ATENÇÃO", "badge-warn", C_YELLOW
    return "NORMAL", "badge-ok", C_GREEN

def suavizar(series, window=15):
    return series.rolling(window=window, min_periods=1).mean()

def calcular_ttc(tank_id, tank_data, pipe_data):
    ultimo_nivel = tank_data[tank_data["tank_id"] == tank_id]["tank_level_percent"].iloc[-1]
    pipes_do_tanque = pipe_data[pipe_data["tank_id"] == tank_id]
    if pipes_do_tanque.empty:
        return None
    vazao_media = pipes_do_tanque.groupby("timestamp")["flow_rate_m3_h"].sum().mean()
    volume_restante = (100 - ultimo_nivel) / 100 * TANK_CAPACITY_M3
    if vazao_media <= 0:
        return None
    return round(volume_restante / vazao_media, 2)

def gerar_alertas(tank_df, pipe_df):
    alertas = []
    now = tank_df["timestamp"].max()
    latest_tank = tank_df[tank_df["timestamp"] == now]
    for _, row in latest_tank.iterrows():
        lvl = row["tank_level_percent"]
        tid = row["tank_id"]
        status, _, _ = get_status(lvl)
        ttc = calcular_ttc(tid, tank_df, pipe_df)
        if status == "CRÍTICO":
            msg = f"Nível crítico: {lvl:.1f}%"
            if ttc:
                h, m = int(ttc), int((ttc % 1) * 60)
                msg += f" — enchimento completo em {h}h{m:02d}m"
            alertas.append({"entidade": tid, "tipo": "CRÍTICO", "motivo": msg, "timestamp": now})
        elif status == "ATENÇÃO":
            msg = f"Nível em atenção: {lvl:.1f}%"
            alertas.append({"entidade": tid, "tipo": "ATENÇÃO", "motivo": msg, "timestamp": now})

    latest_pipe = pipe_df[pipe_df["timestamp"] == now]
    flow_median = latest_pipe["flow_rate_m3_h"].median()
    press_median = latest_pipe["pressure_bar"].median()
    for _, row in latest_pipe.iterrows():
        anomalo = row["flow_rate_m3_h"] < flow_median * 0.5 and row["pressure_bar"] > press_median * 1.5
        if anomalo:
            alertas.append({
                "entidade": row["pipe_id"],
                "tipo": "CRÍTICO",
                "motivo": f"Possível obstrução: vazão {row['flow_rate_m3_h']:.0f} m³/h, pressão {row['pressure_bar']:.0f} bar",
                "timestamp": now
            })
    return alertas

def plotly_layout(title="", legend=None):
    default_legend = dict(bgcolor="rgba(0,0,0,0)", font=dict(color=C_SUBTEXT))
    if legend is not None:
        default_legend.update(legend)
    return dict(
        title=dict(text=title, font=dict(color=C_TEXT, size=13, family="Exo 2")),
        paper_bgcolor=C_CARD,
        plot_bgcolor=C_CARD,
        font=dict(color=C_SUBTEXT, size=11, family="Exo 2"),
        xaxis=dict(gridcolor="#1E2530", zerolinecolor="#1E2530", tickfont=dict(color=C_SUBTEXT)),
        yaxis=dict(gridcolor="#1E2530", zerolinecolor="#1E2530", tickfont=dict(color=C_SUBTEXT)),
        legend=default_legend,
        margin=dict(l=40, r=20, t=40, b=40),
    )

def filtrar_periodo(df, horas):
    cutoff = df["timestamp"].max() - timedelta(hours=horas)
    return df[df["timestamp"] >= cutoff]

def metric_destaque(label, valor, status=None):
    """Renderiza uma métrica com destaque visual por status."""
    if status == "CRÍTICO":
        border = C_RED
        bg = "rgba(215,90,90,0.12)"
        cor_valor = C_RED
        sombra = f"0 0 14px rgba(215,90,90,0.3)"
    elif status == "ATENÇÃO":
        border = C_YELLOW
        bg = "rgba(216,176,45,0.10)"
        cor_valor = C_YELLOW
        sombra = f"0 0 10px rgba(216,176,45,0.2)"
    else:
        border = "#1E2530"
        bg = C_CARD
        cor_valor = C_CYAN
        sombra = "none"

    st.markdown(f"""
    <div style="
        background:{bg};
        border:1px solid {border};
        border-radius:8px;
        padding:12px 16px;
        box-shadow:{sombra};
        margin-bottom:4px;
    ">
        <div style="font-size:0.72rem;color:{C_SUBTEXT};text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">{label}</div>
        <div style="font-family:'Share Tech Mono',monospace;font-size:1.5rem;color:{cor_valor};font-weight:700;">{valor}</div>
    </div>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sidebar-logo">DEEPWATCH<span>.</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="sidebar-sub">Offshore Intelligence — FPSO-01</div>', unsafe_allow_html=True)
    st.markdown("---")

    pagina = st.radio(
        "NAVEGAÇÃO",
        ["Geral", "Individual"],
        label_visibility="visible"
    )

    st.markdown("---")
    st.markdown('<div class="section-title">Filtros Globais</div>', unsafe_allow_html=True)

    plataformas = tank_df["platform_id"].unique().tolist()
    plataforma_sel = st.selectbox("Plataforma", plataformas)

    periodo_label = st.selectbox("Período", ["Última 1h", "Últimas 6h", "Últimas 24h"])
    periodo_horas = {"Última 1h": 1, "Últimas 6h": 6, "Últimas 24h": 24}[periodo_label]

    st.markdown("---")
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    st.markdown(f'<div style="font-size:0.65rem;color:{C_SUBTEXT};font-family:Share Tech Mono;">LIVE &nbsp;|&nbsp; {now_str}</div>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown(f"""
    <div style="
        position: relative;
        height: 80px;
    ">
        <div style="
            position: absolute;
            bottom: 0;
            width: 100%;
        ">
            <button style="
                width: 100%;
                background: {C_CYAN};
                color: #000000 !important;
                border: none;
                border-radius: 4px;
                padding: 10px;
                font-family: 'Share Tech Mono', monospace;
                font-size: 0.75rem;
                letter-spacing: 0.08em;
                font-weight: 700;
                cursor: pointer;
                box-shadow: 0 4px 16px rgba(37,192,195,0.25);
            ">
                BAIXAR DADOS COMO CSV
            </button>
        </div>
    </div>
    """, unsafe_allow_html=True)

tank_filtered = filtrar_periodo(tank_df[tank_df["platform_id"] == plataforma_sel], periodo_horas)
pipe_filtered = filtrar_periodo(pipe_df[pipe_df["platform_id"] == plataforma_sel], periodo_horas)
alertas = gerar_alertas(tank_df, pipe_df)

now_ts = tank_df["timestamp"].max()
latest_tank = tank_df[tank_df["timestamp"] == now_ts]
latest_pipe = pipe_df[pipe_df["timestamp"] == now_ts]

if pagina == "Geral":
    st.markdown('<div class="page-title">DEEPWATCH<span>.</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="page-subtitle">Monitor operacional — FPSO-01</div>', unsafe_allow_html=True)

    tanques_criticos = sum(1 for _, r in latest_tank.iterrows() if r["tank_level_percent"] >= 85)
    tanque_mais_crit = latest_tank.loc[latest_tank["tank_level_percent"].idxmax()]
    ttcs = {tid: calcular_ttc(tid, tank_df, pipe_df) for tid in latest_tank["tank_id"]}
    ttc_min = min((v for v in ttcs.values() if v), default=None)

    var_volume = tank_filtered.groupby("tank_id")["tank_level_percent"].apply(
        lambda x: x.iloc[-1] - x.iloc[0] if len(x) > 1 else 0
    ).sum()
    balanco_ok = abs(var_volume) < 20
    balanco_status = "OK" if balanco_ok else "ALERTA"

    press_media_global = latest_pipe["pressure_bar"].mean()
    flow_median_g = latest_pipe["flow_rate_m3_h"].median()
    press_median_g = latest_pipe["pressure_bar"].median()
    n_anomalos_g = sum(
        1 for _, r in latest_pipe.iterrows()
        if r["flow_rate_m3_h"] < flow_median_g * 0.5 and r["pressure_bar"] > press_median_g * 1.5
    )

    # Status do tanque mais crítico para destaque
    nivel_mais_crit = tanque_mais_crit["tank_level_percent"]
    status_mais_crit, _, _ = get_status(nivel_mais_crit)

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st_tc = "CRÍTICO" if tanques_criticos >= 3 else ("ATENÇÃO" if tanques_criticos >= 1 else None)
        metric_destaque("Tanques Acima de 85%", str(tanques_criticos), st_tc)
    with c2:
        metric_destaque(
            "Tanque Mais Crítico",
            f"{tanque_mais_crit['tank_id']} — {nivel_mais_crit:.1f}%",
            status_mais_crit
        )
    with c3:
        if ttc_min:
            h, m = int(ttc_min), int((ttc_min % 1) * 60)
            st_ttc = "CRÍTICO" if ttc_min < 4 else ("ATENÇÃO" if ttc_min < 10 else None)
            metric_destaque("TTC Mais Crítico", f"{h}h {m:02d}m", st_ttc)
        else:
            metric_destaque("TTC", "N/D")
    with c4:
        st_bal = "ATENÇÃO" if balanco_status == "ALERTA" else None
        metric_destaque("Balanço de Massa", balanco_status, st_bal)
    with c5:
        st_an = "CRÍTICO" if n_anomalos_g > 0 else None
        metric_destaque("Dutos com Anomalia", str(n_anomalos_g), st_an)

    st.markdown("---")

    st.markdown('<div class="section-title">Alertas Ativos</div>', unsafe_allow_html=True)
    if alertas:
        for a in alertas:
            cls = "alert-crit" if a["tipo"] == "CRÍTICO" else "alert-warn"
            cor = C_RED if a["tipo"] == "CRÍTICO" else C_YELLOW
            icone = "CRÍTICO" if a["tipo"] == "CRÍTICO" else "ATENÇÃO"
            st.markdown(f"""
            <div class="alert-box {cls}">
                <div class="alert-title" style="color:{cor};">[{icone}] {a['entidade']}</div>
                <div class="alert-msg">{a['motivo']}</div>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="alert-box alert-ok"><div class="alert-title" style="color:{C_GREEN};">Nenhum alerta ativo</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown('<div class="section-title">Tanques</div>', unsafe_allow_html=True)

    def hex_color(lvl):
        if lvl >= 95: return C_RED
        if lvl >= 85: return C_RED
        if lvl >= 70: return C_YELLOW
        return C_GREEN

    def hex_stroke(lvl):
        if lvl >= 95: return C_RED
        if lvl >= 85: return C_RED
        if lvl >= 70: return C_YELLOW
        return C_BG

    def hex_points(cx, cy, radius):
        pts = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    tank_rows_list = latest_tank.sort_values("tank_id").to_dict("records")

    R    = 62
    gap  = 4
    r    = R * 0.866
    col_w = 2 * r + gap
    row_h = 1.5 * R + gap * 0.5
    per_row = 4
    n_rows = -(-len(tank_rows_list) // per_row)

    svg_w = int(per_row * col_w + r + gap * 4)
    svg_h = int(n_rows * row_h + 0.5 * R + gap * 4 + R)

    shapes = []
    for idx, tank in enumerate(tank_rows_list):
        col = idx % per_row
        row = idx // per_row
        cx = gap * 2 + r + col * col_w + (r + gap * 0.5 if row % 2 == 1 else 0)
        cy = gap * 2 + R + row * row_h
        lvl = tank["tank_level_percent"]
        cor = hex_color(lvl)
        stroke = hex_stroke(lvl)
        tid_label = tank["tank_id"]
        pts = hex_points(cx, cy, R - 1)

        # Efeito de pulso para tanques críticos
        if lvl >= 95:
            glow = f'<animate attributeName="opacity" values="1;0.7;1" dur="1.4s" repeatCount="indefinite"/>'
            extra_ring = f'<polygon points="{hex_points(cx, cy, R + 5)}" fill="none" stroke="{C_RED}" stroke-width="2" opacity="0.4"><animate attributeName="opacity" values="0.4;0;0.4" dur="1.4s" repeatCount="indefinite"/></polygon>'
        else:
            glow = ""
            extra_ring = ""

        shapes.append(f"""
          {extra_ring}
          <polygon points="{pts}" fill="{cor}" stroke="{C_BG}" stroke-width="3">{glow}</polygon>
          <text x="{cx:.1f}" y="{cy - 11:.1f}" text-anchor="middle"
                font-family="monospace" font-size="13" fill="white" font-weight="600">{tid_label}</text>
          <text x="{cx:.1f}" y="{cy + 13:.1f}" text-anchor="middle"
                font-family="sans-serif" font-size="21" fill="white" font-weight="700">{lvl:.0f}%</text>""")

    honeycomb_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <style>
      body {{ margin:0; padding:0; background:{C_BG}; }}
      .legend {{ display:flex; gap:20px; justify-content:center;
                 font-family:monospace; font-size:12px; color:#8A9BAE;
                 padding: 6px 0 10px 0; }}
      .dot {{ display:inline-block; width:11px; height:11px;
              border-radius:2px; margin-right:5px; vertical-align:middle; }}
    </style>
    </head>
    <body>
      <div class="legend">
        <span><span class="dot" style="background:{C_GREEN}"></span>Normal (&lt;70%)</span>
        <span><span class="dot" style="background:{C_YELLOW}"></span>Atenção (70–85%)</span>
        <span><span class="dot" style="background:{C_RED}"></span>Crítico (&gt;85%)</span>
      </div>
      <svg width="100%" viewBox="0 0 {svg_w} {svg_h}"
           xmlns="http://www.w3.org/2000/svg"
           style="display:block;max-width:680px;margin:0 auto;">
        {''.join(shapes)}
      </svg>
    </body>
    </html>"""

    components.html(honeycomb_html, height=svg_h + 70, scrolling=False)

    st.markdown("---")

    media_ocupacao = latest_tank["tank_level_percent"].mean()
    volume_disponivel = sum((100 - r["tank_level_percent"]) / 100 * TANK_CAPACITY_M3 for _, r in latest_tank.iterrows())
    c1, c2 = st.columns(2)
    with c1:
        st_med = "ATENÇÃO" if media_ocupacao >= 70 else None
        metric_destaque("Média de Ocupação", f"{media_ocupacao:.1f}%", st_med)
    with c2:
        metric_destaque("Volume Disponível Total", f"{volume_disponivel:,.0f} m³")

    df_bar = latest_tank.sort_values("tank_level_percent", ascending=True).copy()
    df_bar["cor"] = df_bar["tank_level_percent"].apply(lambda x: C_RED if x >= 85 else (C_YELLOW if x >= 70 else C_CYAN))
    fig_b = go.Figure()
    fig_b.add_trace(go.Bar(
        x=df_bar["tank_level_percent"], y=df_bar["tank_id"], orientation="h",
        marker_color=df_bar["cor"].tolist(),
        text=df_bar["tank_level_percent"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside", textfont=dict(color=C_TEXT, size=11)
    ))
    fig_b.add_vline(x=70, line_dash="dash", line_color=C_YELLOW, annotation_text="70% — Atenção", annotation_font_color=C_YELLOW)
    fig_b.add_vline(x=85, line_dash="dash", line_color=C_RED, annotation_text="85% — Crítico", annotation_font_color=C_RED)
    fig_b.update_layout(**plotly_layout("Ocupação por Tanque"), xaxis_range=[0, 115])
    st.plotly_chart(fig_b, width='stretch')

    tabela_dados = []
    for _, row in latest_tank.iterrows():
        tid = row["tank_id"]
        lvl = row["tank_level_percent"]
        vol_disp = (100 - lvl) / 100 * TANK_CAPACITY_M3
        status_t, _, cor_st = get_status(lvl)
        ttc_v = calcular_ttc(tid, tank_df, pipe_df)
        ttc_str = f"{int(ttc_v)}h {int((ttc_v%1)*60):02d}m" if ttc_v else "N/D"
        tabela_dados.append({
            "Tanque": tid,
            "Nível (%)": f"{lvl:.1f}",
            "Vol. Disponível (m³)": f"{vol_disp:,.0f}",
            "Status": status_t,
            "TTC": ttc_str
        })

    df_tabela = pd.DataFrame(tabela_dados)

    def colorir_status(val):
        if val == "CRÍTICO":
            return f"background-color: rgba(215,90,90,0.18); color: {C_RED}; font-weight: 700;"
        elif val == "ATENÇÃO":
            return f"background-color: rgba(216,176,45,0.13); color: {C_YELLOW}; font-weight: 700;"
        return ""

    def colorir_linha(row):
        if row["Status"] == "CRÍTICO":
            return [f"background-color: rgba(215,90,90,0.10);" for _ in row]
        elif row["Status"] == "ATENÇÃO":
            return [f"background-color: rgba(216,176,45,0.07);" for _ in row]
        return ["" for _ in row]

    st.dataframe(
        df_tabela.style
            .apply(colorir_linha, axis=1)
            .applymap(colorir_status, subset=["Status"]),
        width='stretch',
        hide_index=True
    )

    st.markdown("---")

    st.markdown('<div class="section-title">Histórico de Nível por Tanque</div>', unsafe_allow_html=True)

    line_colors = [C_CYAN, C_YELLOW, C_RED, "#A78BFA", "#F472B6", "#34D399", "#FB923C", "#60A5FA"]

    tank_ids_sorted = sorted(tank_df["tank_id"].unique().tolist())
    fig_hist = go.Figure()

    for i, tid in enumerate(tank_ids_sorted):
        dados_tid = filtrar_periodo(tank_df[tank_df["tank_id"] == tid], periodo_horas).copy()
        dados_tid["suavizado"] = suavizar(dados_tid["tank_level_percent"])
        nivel_atual_tid = dados_tid["tank_level_percent"].iloc[-1]
        _, badge_cls, cor_status = get_status(nivel_atual_tid)

        # Tanques em alerta ou crítico recebem cor de status; os normais seguem a paleta
        cor_linha = cor_status if badge_cls != "badge-ok" else line_colors[i % len(line_colors)]
        largura = 2.5 if badge_cls != "badge-ok" else 1.5

        fig_hist.add_trace(go.Scatter(
            x=dados_tid["timestamp"],
            y=dados_tid["suavizado"],
            name=tid,
            line=dict(color=cor_linha, width=largura, dash="solid"),
            hovertemplate=f"<b>{tid}</b><br>%{{x|%H:%M}}<br>Nível: %{{y:.1f}}%<extra></extra>"
        ))

    fig_hist.add_hline(y=70, line_dash="dash", line_color=C_YELLOW,
                       annotation_text="70% — Atenção", annotation_font_color=C_YELLOW,
                       annotation_position="bottom right")
    fig_hist.add_hline(y=85, line_dash="dash", line_color=C_RED,
                       annotation_text="85% — Crítico", annotation_font_color=C_RED,
                       annotation_position="bottom right")
    fig_hist.update_layout(
        **plotly_layout(
            "Histórico de Nível (%) — Todos os Tanques",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
        ),
        yaxis_range=[25, 100],
        yaxis_title="Nível (%)",
        hovermode="x unified"
    )
    st.plotly_chart(fig_hist, width='stretch')

    st.markdown("---")

    st.markdown('<div class="section-title">Dutos</div>', unsafe_allow_html=True)

    flow_median_d = latest_pipe["flow_rate_m3_h"].median()
    press_median_d = latest_pipe["pressure_bar"].median()
    latest_pipe_copy = latest_pipe.copy()
    latest_pipe_copy["anomalo"] = latest_pipe_copy.apply(
        lambda r: r["flow_rate_m3_h"] < flow_median_d * 0.5 and r["pressure_bar"] > press_median_d * 1.5, axis=1)

    c1, c2 = st.columns(2)
    with c1:
        metric_destaque("Pressão Média nos Dutos", f"{press_media_global:.1f} bar")
    with c2:
        st_an2 = "CRÍTICO" if n_anomalos_g > 0 else None
        metric_destaque("Dutos com Anomalia", str(int(n_anomalos_g)), st_an2)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        df_rank = latest_pipe_copy.sort_values("flow_rate_m3_h", ascending=True)
        df_rank["cor"] = df_rank["anomalo"].apply(lambda x: C_RED if x else C_CYAN)
        fig_rank = go.Figure()
        fig_rank.add_trace(go.Bar(
            x=df_rank["flow_rate_m3_h"], y=df_rank["pipe_id"], orientation="h",
            marker_color=df_rank["cor"].tolist(),
            text=df_rank["flow_rate_m3_h"].apply(lambda x: f"{x:.0f}"),
            textposition="outside", textfont=dict(color=C_TEXT)
        ))
        fig_rank.update_layout(**plotly_layout("Ranking de Vazão (m³/h)"))
        st.plotly_chart(fig_rank, width='stretch')

    with col_d2:
        normal_d = latest_pipe_copy[~latest_pipe_copy["anomalo"]]
        anomalo_d = latest_pipe_copy[latest_pipe_copy["anomalo"]]
        fig_sc = go.Figure()
        fig_sc.add_trace(go.Scatter(
            x=normal_d["pressure_bar"], y=normal_d["flow_rate_m3_h"],
            mode="markers+text", name="Normal",
            marker=dict(color=C_CYAN, size=12, opacity=0.8),
            text=normal_d["pipe_id"], textposition="top center",
            textfont=dict(color=C_SUBTEXT, size=9)
        ))
        if not anomalo_d.empty:
            fig_sc.add_trace(go.Scatter(
                x=anomalo_d["pressure_bar"], y=anomalo_d["flow_rate_m3_h"],
                mode="markers+text", name="Anômalo",
                marker=dict(color=C_RED, size=14, symbol="x"),
                text=anomalo_d["pipe_id"], textposition="top center",
                textfont=dict(color=C_RED, size=9)
            ))
        fig_sc.update_layout(**plotly_layout("Vazão vs Pressão — Obstrução"),
                             xaxis_title="Pressão (bar)", yaxis_title="Vazão (m³/h)")
        st.plotly_chart(fig_sc, width='stretch')

    tabela_pipes = []
    for _, row in latest_pipe_copy.iterrows():
        tabela_pipes.append({
            "Duto": row["pipe_id"], "Tanque": row["tank_id"],
            "Vazão (m³/h)": f"{row['flow_rate_m3_h']:.0f}",
            "Pressão (bar)": f"{row['pressure_bar']:.1f}",
            "Status": "CRÍTICO" if row["anomalo"] else "NORMAL"
        })

    df_pipes = pd.DataFrame(tabela_pipes)
    st.dataframe(
        df_pipes.style
            .apply(colorir_linha, axis=1)
            .applymap(colorir_status, subset=["Status"]),
        width='stretch',
        hide_index=True
    )

    st.markdown("---")

    st.markdown('<div class="section-title">Central de Anomalias (RTA)</div>', unsafe_allow_html=True)

    historico = []
    checkpoints = [now_ts - timedelta(hours=i) for i in range(0, 24, 2)]
    for cp in checkpoints:
        tank_cp = tank_df[tank_df["timestamp"] == min(tank_df["timestamp"], key=lambda t: abs((t-cp).total_seconds()))]
        for _, row in tank_cp.iterrows():
            lvl = row["tank_level_percent"]
            st_v, _, _ = get_status(lvl)
            if st_v != "NORMAL":
                historico.append({"timestamp": cp, "entidade": row["tank_id"], "tipo": st_v, "motivo": f"Nível: {lvl:.1f}%", "valor": lvl})
        pipe_cp = pipe_df[pipe_df["timestamp"] == min(pipe_df["timestamp"], key=lambda t: abs((t-cp).total_seconds()))]
        fm = pipe_cp["flow_rate_m3_h"].median()
        pm = pipe_cp["pressure_bar"].median()
        for _, row in pipe_cp.iterrows():
            if row["flow_rate_m3_h"] < fm * 0.5 and row["pressure_bar"] > pm * 1.5:
                historico.append({"timestamp": cp, "entidade": row["pipe_id"], "tipo": "CRÍTICO",
                                   "motivo": f"Obstrução: {row['flow_rate_m3_h']:.0f} m³/h @ {row['pressure_bar']:.0f} bar", "valor": row["pressure_bar"]})

    df_hist = pd.DataFrame(historico).sort_values("timestamp", ascending=False)

    fc1, fc2, fc3 = st.columns(3)
    with fc1: tipo_filtro = st.selectbox("Tipo de Alerta", ["Todos", "CRÍTICO", "ATENÇÃO", "NORMAL"], key="rta_tipo")
    with fc2:
        entidades_disp = ["Todas"] + sorted(df_hist["entidade"].unique().tolist())
        entidade_filtro = st.selectbox("Entidade", entidades_disp, key="rta_ent")
    with fc3: data_inicio = st.date_input("Data Início", value=(now_ts - timedelta(hours=24)).date(), key="rta_data")

    df_exib = df_hist.copy()
    if tipo_filtro != "Todos": df_exib = df_exib[df_exib["tipo"] == tipo_filtro]
    if entidade_filtro != "Todas": df_exib = df_exib[df_exib["entidade"] == entidade_filtro]
    df_exib = df_exib[df_exib["timestamp"].dt.date >= data_inicio]

    if df_exib.empty:
        st.info("Nenhum alerta encontrado com os filtros selecionados.")
    else:
        for i, (_, row) in enumerate(df_exib.iterrows()):
            cor = C_RED if row["tipo"] == "CRÍTICO" else C_YELLOW
            ts_fmt = row["timestamp"].strftime("%d/%m %H:%M")
            with st.expander(f"[{row['tipo']}] {row['entidade']} — {ts_fmt} — {row['motivo']}"):
                evento_ts = row["timestamp"]
                ent = row["entidade"]
                if ent.startswith("T"):
                    dados_evento = tank_df[
                        (tank_df["tank_id"] == ent) &
                        (tank_df["timestamp"] >= evento_ts - timedelta(hours=2)) &
                        (tank_df["timestamp"] <= evento_ts + timedelta(hours=2))
                    ]
                    fig_ev = go.Figure()
                    fig_ev.add_trace(go.Scatter(x=dados_evento["timestamp"], y=dados_evento["tank_level_percent"],
                                                name="Nível (%)", line=dict(color=C_CYAN, width=2)))
                    fig_ev.add_vline(x=evento_ts, line_dash="dash", line_color=cor)
                    fig_ev.update_layout(**plotly_layout(f"Contexto — {ent}"))
                    st.plotly_chart(fig_ev, width='stretch')
                else:
                    dados_evento = pipe_df[
                        (pipe_df["pipe_id"] == ent) &
                        (pipe_df["timestamp"] >= evento_ts - timedelta(hours=2)) &
                        (pipe_df["timestamp"] <= evento_ts + timedelta(hours=2))
                    ]
                    fig_ev = go.Figure()
                    fig_ev.add_trace(go.Scatter(x=dados_evento["timestamp"], y=dados_evento["flow_rate_m3_h"],
                                                name="Vazão (m³/h)", line=dict(color=C_CYAN, width=2)))
                    fig_ev.add_trace(go.Scatter(x=dados_evento["timestamp"], y=dados_evento["pressure_bar"],
                                                name="Pressão (bar)", line=dict(color=C_YELLOW, width=2), yaxis="y2"))
                    fig_ev.add_vline(x=evento_ts, line_dash="dash", line_color=cor)
                    fig_ev.update_layout(**plotly_layout(f"Contexto — {ent}"),
                                         yaxis2=dict(overlaying="y", side="right", gridcolor="#1E2530", tickfont=dict(color=C_SUBTEXT)))
                    st.plotly_chart(fig_ev, width='stretch')
                csv_ev = dados_evento.to_csv(index=False).encode("utf-8")
                ts_str_ev = evento_ts.strftime("%Y%m%d_%H%M")
                st.download_button(label="Exportar RTA deste Evento", data=csv_ev,
                                   file_name=f"RTA_{ent}_{ts_str_ev}.csv", mime="text/csv",
                                   key=f"rta_{i}_{ent}_{ts_str_ev}")

elif pagina == "Individual":
    st.markdown('<div class="page-title">DEEPWATCH<span>.</span> — ANÁLISE INDIVIDUAL</div>', unsafe_allow_html=True)

    tab_tank, tab_pipe = st.tabs(["Tanque", "Duto"])

    with tab_tank:
        tank_ids = sorted(tank_df["tank_id"].unique().tolist())
        default_idx = tank_ids.index(st.session_state.get("tanque_sel", tank_ids[0])) \
            if st.session_state.get("individual_tipo") == "Tanque" else 0
        tid = st.selectbox("Selecionar Tanque", tank_ids, index=default_idx, key="sel_tank_ind")
        st.session_state["tanque_sel"] = tid

        st.markdown('<div class="page-subtitle">Análise detalhada — ' + tid + '</div>', unsafe_allow_html=True)

        dados_tank = tank_filtered[tank_filtered["tank_id"] == tid].copy()
        dados_pipe_tank = pipe_filtered[pipe_filtered["tank_id"] == tid].copy()
        nivel_atual = dados_tank["tank_level_percent"].iloc[-1]
        vol_disp = (100 - nivel_atual) / 100 * TANK_CAPACITY_M3
        ttc = calcular_ttc(tid, tank_df, pipe_df)
        ttc_str = f"{int(ttc)}h {int((ttc%1)*60):02d}m" if ttc else "N/D"
        tank_1h = filtrar_periodo(tank_df[tank_df["tank_id"] == tid], 1)
        var_hora = tank_1h["tank_level_percent"].iloc[-1] - tank_1h["tank_level_percent"].iloc[0] if len(tank_1h) > 1 else 0
        status_t, _, cor_t = get_status(nivel_atual)

        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            metric_destaque("Nível Atual", f"{nivel_atual:.1f}%", status_t)
        with c2:
            metric_destaque("Vol. Disponível", f"{vol_disp:,.0f} m³")
        with c3:
            st_ttc = "CRÍTICO" if ttc and ttc < 4 else ("ATENÇÃO" if ttc and ttc < 10 else None)
            metric_destaque("TTC", ttc_str, st_ttc)
        with c4:
            st_var = "ATENÇÃO" if var_hora > 5 else None
            metric_destaque("Var. Última Hora", f"{var_hora:+.2f}%", st_var)
        with c5:
            metric_destaque("Status", status_t, status_t)

        st.markdown("---")
        periodo_t = st.radio("Período:", ["Última 1h", "Últimas 6h", "Últimas 24h"], horizontal=True, key="per_tank_i")
        h_t = {"Última 1h": 1, "Últimas 6h": 6, "Últimas 24h": 24}[periodo_t]
        dados_plot = filtrar_periodo(tank_df[tank_df["tank_id"] == tid], h_t).copy()
        dados_plot["suavizado"] = suavizar(dados_plot["tank_level_percent"])

        fig_t1 = go.Figure()
        fig_t1.add_trace(go.Scatter(x=dados_plot["timestamp"], y=dados_plot["tank_level_percent"],
                                    name="Bruto", line=dict(color=C_CYAN, width=1, dash="dot"), opacity=0.4))
        fig_t1.add_trace(go.Scatter(x=dados_plot["timestamp"], y=dados_plot["suavizado"],
                                    name="Suavizado", line=dict(color=C_CYAN, width=2.5)))
        fig_t1.add_hline(y=70, line_dash="dash", line_color=C_YELLOW, annotation_text="70% — Atenção", annotation_font_color=C_YELLOW)
        fig_t1.add_hline(y=85, line_dash="dash", line_color=C_RED, annotation_text="85% — Crítico", annotation_font_color=C_RED)
        fig_t1.update_layout(**plotly_layout(f"Histórico de Nível — {tid}"), yaxis_range=[0, 105])
        st.plotly_chart(fig_t1, width='stretch')

        if ttc and nivel_atual < 100:
            future_times = [dados_plot["timestamp"].iloc[-1] + timedelta(minutes=i*30) for i in range(1, int(ttc*2)+2)]
            future_levels = [min(nivel_atual + (100-nivel_atual)/len(future_times)*i, 100) for i in range(1, len(future_times)+1)]
            fig_t2 = go.Figure()
            fig_t2.add_trace(go.Scatter(x=dados_plot["timestamp"], y=dados_plot["suavizado"],
                                        name="Histórico", line=dict(color=C_CYAN, width=2)))
            fig_t2.add_trace(go.Scatter(x=future_times, y=future_levels,
                                        name="Projeção", line=dict(color=C_YELLOW, width=2, dash="dash")))
            fig_t2.add_hline(y=70, line_dash="dot", line_color=C_YELLOW)
            fig_t2.add_hline(y=85, line_dash="dot", line_color=C_RED)
            fig_t2.update_layout(**plotly_layout(f"Previsão de Enchimento — {tid}"), yaxis_range=[0, 105])
            st.plotly_chart(fig_t2, width='stretch')

        if not dados_pipe_tank.empty:
            pipe_agg = dados_pipe_tank.groupby("timestamp").agg(
                flow=("flow_rate_m3_h", "sum"), pressure=("pressure_bar", "mean")).reset_index()
            fig_t3 = go.Figure()
            fig_t3.add_trace(go.Scatter(x=pipe_agg["timestamp"], y=pipe_agg["flow"],
                                        name="Vazão Total (m³/h)", line=dict(color=C_CYAN, width=2)))
            fig_t3.add_trace(go.Scatter(x=pipe_agg["timestamp"], y=pipe_agg["pressure"],
                                        name="Pressão Média (bar)", line=dict(color=C_YELLOW, width=2), yaxis="y2"))
            fig_t3.update_layout(**plotly_layout(f"Vazão e Pressão dos Dutos — {tid}"),
                                  yaxis2=dict(overlaying="y", side="right", gridcolor="#1E2530", tickfont=dict(color=C_SUBTEXT)))
            st.plotly_chart(fig_t3, width='stretch')

        st.markdown("---")
        janela_rta = tank_df[tank_df["tank_id"] == tid].copy()
        janela_rta = janela_rta[(janela_rta["timestamp"] >= now_ts - timedelta(hours=2)) &
                                (janela_rta["timestamp"] <= now_ts + timedelta(hours=2))]
        pipes_rta = pipe_df[pipe_df["tank_id"] == tid].copy()
        pipes_rta = pipes_rta[(pipes_rta["timestamp"] >= now_ts - timedelta(hours=2)) &
                              (pipes_rta["timestamp"] <= now_ts + timedelta(hours=2))]
        rta_df = pd.merge(janela_rta, pipes_rta, on=["timestamp", "platform_id", "tank_id"], how="outer")
        ts_str = now_ts.strftime("%Y%m%d_%H%M")
        st.download_button(label="Gerar Pacote RTA", data=rta_df.to_csv(index=False).encode("utf-8"),
                           file_name=f"RTA_{tid}_{ts_str}.csv", mime="text/csv", key="rta_tank_ind")

    with tab_pipe:
        pipe_ids = sorted(pipe_df["pipe_id"].unique().tolist())
        default_pipe = pipe_ids.index(st.session_state.get("duto_sel", pipe_ids[0])) \
            if st.session_state.get("individual_tipo") == "Duto" else 0
        pid = st.selectbox("Selecionar Duto", pipe_ids, index=default_pipe, key="sel_pipe_ind")
        st.session_state["duto_sel"] = pid

        st.markdown('<div class="page-subtitle">Análise detalhada — ' + pid + '</div>', unsafe_allow_html=True)

        latest_pipe_row = latest_pipe[latest_pipe["pipe_id"] == pid].iloc[0]
        vazao_atual = latest_pipe_row["flow_rate_m3_h"]
        press_atual = latest_pipe_row["pressure_bar"]
        tank_assoc = latest_pipe_row["tank_id"]
        flow_med_p = latest_pipe["flow_rate_m3_h"].median()
        press_med_p = latest_pipe["pressure_bar"].median()
        anomalo_p = vazao_atual < flow_med_p * 0.5 and press_atual > press_med_p * 1.5
        status_p = "CRÍTICO" if anomalo_p else "NORMAL"

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st_vaz = "CRÍTICO" if anomalo_p else None
            metric_destaque("Vazão Atual", f"{vazao_atual:.0f} m³/h", st_vaz)
        with c2:
            st_press = "CRÍTICO" if anomalo_p else None
            metric_destaque("Pressão Atual", f"{press_atual:.1f} bar", st_press)
        with c3:
            metric_destaque("Tanque Associado", tank_assoc)
        with c4:
            metric_destaque("Status", status_p, status_p if anomalo_p else None)

        st.markdown("---")
        periodo_p = st.radio("Período:", ["Última 1h", "Últimas 6h", "Últimas 24h"], horizontal=True, key="per_pipe_i")
        h_p = {"Última 1h": 1, "Últimas 6h": 6, "Últimas 24h": 24}[periodo_p]
        dados_plot_pipe = filtrar_periodo(pipe_df[pipe_df["pipe_id"] == pid], h_p).copy()
        dados_plot_pipe["flow_suav"] = suavizar(dados_plot_pipe["flow_rate_m3_h"])
        dados_plot_pipe["press_suav"] = suavizar(dados_plot_pipe["pressure_bar"])

        fig_p1 = go.Figure()
        fig_p1.add_trace(go.Scatter(x=dados_plot_pipe["timestamp"], y=dados_plot_pipe["flow_rate_m3_h"],
                                    name="Bruto", line=dict(color=C_CYAN, width=1, dash="dot"), opacity=0.4))
        fig_p1.add_trace(go.Scatter(x=dados_plot_pipe["timestamp"], y=dados_plot_pipe["flow_suav"],
                                    name="Suavizado", line=dict(color=C_CYAN, width=2.5)))
        fig_p1.update_layout(**plotly_layout(f"Histórico de Vazão — {pid}"), yaxis_title="m³/h")
        st.plotly_chart(fig_p1, width='stretch')

        press_limite_p = press_med_p * 1.4
        fig_p2 = go.Figure()
        fig_p2.add_trace(go.Scatter(x=dados_plot_pipe["timestamp"], y=dados_plot_pipe["pressure_bar"],
                                    name="Bruto", line=dict(color=C_YELLOW, width=1, dash="dot"), opacity=0.4))
        fig_p2.add_trace(go.Scatter(x=dados_plot_pipe["timestamp"], y=dados_plot_pipe["press_suav"],
                                    name="Suavizado", line=dict(color=C_YELLOW, width=2.5)))
        fig_p2.add_hline(y=press_limite_p, line_dash="dash", line_color=C_RED,
                         annotation_text="Limite esperado", annotation_font_color=C_RED)
        fig_p2.update_layout(**plotly_layout(f"Histórico de Pressão — {pid}"), yaxis_title="bar")
        st.plotly_chart(fig_p2, width='stretch')
