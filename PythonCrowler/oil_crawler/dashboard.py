"""
Dashboard HTML interativo com Plotly
Visualiza estatísticas da análise léxica de notícias offshore.
"""

import json
import os
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import plotly.offline as pyo


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
COLORS = {
    "Explosão / Incêndio": "#e74c3c",
    "Afundamento / Colapso": "#8e44ad",
    "Vazamento / Derramamento": "#e67e22",
    "Impacto Ambiental": "#27ae60",
    "Incidente Offshore (geral)": "#2980b9",
    "Outro": "#95a5a6",
}

CATEGORY_COLORS = {
    "VAZAMENTO": "#e67e22",
    "EXPLOSÃO": "#e74c3c",
    "AFUNDAMENTO": "#8e44ad",
    "PLATAFORMA": "#2980b9",
    "IMPACTO_AMBIENTAL": "#27ae60",
    "VÍTIMAS": "#c0392b",
    "EMPRESA": "#f39c12",
    "LOCALIZAÇÃO": "#16a085",
}


def filter_last_year(monthly: dict) -> dict:
    """Filtra apenas os últimos 12 meses."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m")
    return {k: v for k, v in monthly.items() if k >= cutoff}


# ─────────────────────────────────────────────
# FIGURAS
# ─────────────────────────────────────────────
def fig_incident_pie(incident_dist: dict) -> go.Figure:
    labels = list(incident_dist.keys())
    values = list(incident_dist.values())
    colors = [COLORS.get(l, "#bdc3c7") for l in labels]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker_colors=colors,
        hole=0.4,
        textinfo="label+percent",
        hovertemplate="<b>%{label}</b><br>Notícias: %{value}<br>%{percent}<extra></extra>"
    ))
    fig.update_layout(
        title="Distribuição por Tipo de Incidente",
        font=dict(family="Arial", size=13),
        margin=dict(t=60, b=20, l=20, r=20),
        legend=dict(orientation="v", x=1.02)
    )
    return fig


def fig_monthly_bar(monthly_dist: dict) -> go.Figure:
    monthly_year = filter_last_year(monthly_dist)

    if not monthly_year:
        # Usa todos os dados se não há dados do último ano
        monthly_year = monthly_dist

    months = sorted(monthly_year.keys())
    counts = [monthly_year[m] for m in months]

    # Formata labels de mês
    labels = []
    for m in months:
        try:
            dt = datetime.strptime(m, "%Y-%m")
            labels.append(dt.strftime("%b/%Y"))
        except Exception:
            labels.append(m)

    fig = go.Figure(go.Bar(
        x=labels,
        y=counts,
        marker_color="#2980b9",
        hovertemplate="<b>%{x}</b><br>Notícias: %{y}<extra></extra>",
        text=counts,
        textposition="outside"
    ))
    fig.update_layout(
        title="Notícias por Mês (último ano)",
        xaxis_title="Mês",
        yaxis_title="Nº de Notícias",
        xaxis_tickangle=-45,
        font=dict(family="Arial", size=12),
        margin=dict(t=60, b=80, l=50, r=20),
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#ececec")
    )
    return fig


def fig_source_bar(source_dist: dict) -> go.Figure:
    sources = sorted(source_dist, key=source_dist.get, reverse=True)
    counts = [source_dist[s] for s in sources]

    fig = go.Figure(go.Bar(
        y=sources,
        x=counts,
        orientation="h",
        marker_color="#27ae60",
        hovertemplate="<b>%{y}</b><br>Notícias: %{x}<extra></extra>",
        text=counts,
        textposition="outside"
    ))
    fig.update_layout(
        title="Notícias por Fonte",
        xaxis_title="Nº de Notícias",
        yaxis_title="",
        font=dict(family="Arial", size=12),
        margin=dict(t=60, b=40, l=120, r=60),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#ececec")
    )
    return fig


def fig_category_radar(cat_dist: dict) -> go.Figure:
    cats = list(cat_dist.keys())
    vals = list(cat_dist.values())
    # Fecha o polígono
    cats_closed = cats + [cats[0]]
    vals_closed = vals + [vals[0]]

    fig = go.Figure(go.Scatterpolar(
        r=vals_closed,
        theta=cats_closed,
        fill="toself",
        fillcolor="rgba(41,128,185,0.3)",
        line=dict(color="#2980b9", width=2),
        hovertemplate="<b>%{theta}</b><br>Artigos: %{r}<extra></extra>"
    ))
    fig.update_layout(
        title="Cobertura por Categoria Léxica",
        polar=dict(
            radialaxis=dict(visible=True, gridcolor="#ddd"),
            angularaxis=dict(gridcolor="#ddd")
        ),
        font=dict(family="Arial", size=12),
        margin=dict(t=70, b=40, l=60, r=60)
    )
    return fig


def fig_top_tokens(global_tokens: list) -> go.Figure:
    tokens = [t[0] for t in global_tokens[:20]]
    freqs = [t[1] for t in global_tokens[:20]]

    fig = go.Figure(go.Bar(
        y=tokens[::-1],
        x=freqs[::-1],
        orientation="h",
        marker=dict(
            color=freqs[::-1],
            colorscale="Oranges",
            showscale=True,
            colorbar=dict(title="Freq.")
        ),
        hovertemplate="<b>%{y}</b><br>Frequência: %{x}<extra></extra>"
    ))
    fig.update_layout(
        title="Top 20 Tokens Mais Frequentes",
        xaxis_title="Frequência",
        yaxis_title="",
        font=dict(family="Arial", size=12),
        margin=dict(t=60, b=40, l=120, r=80),
        plot_bgcolor="white",
        xaxis=dict(gridcolor="#ececec")
    )
    return fig


def fig_incident_timeline(analyzed: list) -> go.Figure:
    """Linha do tempo por tipo de incidente."""
    from collections import defaultdict

    # Agrupa por mês e tipo
    data = defaultdict(lambda: defaultdict(int))
    for a in analyzed:
        pub = a.get("published", "")
        itype = a.get("incident_type", "Outro")
        if pub:
            try:
                month = pub[:7]
                data[month][itype] += 1
            except Exception:
                pass

    months = sorted(data.keys())
    cutoff = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m")
    months = [m for m in months if m >= cutoff] or months

    incident_types = list(COLORS.keys())

    fig = go.Figure()
    for itype in incident_types:
        y_vals = [data[m].get(itype, 0) for m in months]
        if sum(y_vals) == 0:
            continue
        labels = []
        for m in months:
            try:
                dt = datetime.strptime(m, "%Y-%m")
                labels.append(dt.strftime("%b/%Y"))
            except Exception:
                labels.append(m)

        fig.add_trace(go.Scatter(
            x=labels,
            y=y_vals,
            name=itype,
            mode="lines+markers",
            line=dict(color=COLORS.get(itype, "#999"), width=2),
            marker=dict(size=7),
            hovertemplate=f"<b>{itype}</b><br>%{{x}}<br>Notícias: %{{y}}<extra></extra>"
        ))

    fig.update_layout(
        title="Evolução Temporal por Tipo de Incidente",
        xaxis_title="Mês",
        yaxis_title="Nº de Notícias",
        xaxis_tickangle=-45,
        font=dict(family="Arial", size=12),
        legend=dict(orientation="h", yanchor="bottom", y=-0.4, x=0),
        margin=dict(t=60, b=120, l=50, r=20),
        plot_bgcolor="white",
        yaxis=dict(gridcolor="#ececec"),
        xaxis=dict(gridcolor="#ececec")
    )
    return fig


def fig_lang_pie(lang_dist: dict) -> go.Figure:
    labels = ["Inglês" if l == "en" else "Português" for l in lang_dist.keys()]
    values = list(lang_dist.values())

    fig = go.Figure(go.Pie(
        labels=labels,
        values=values,
        marker_colors=["#3498db", "#2ecc71"],
        hole=0.4,
        textinfo="label+percent+value"
    ))
    fig.update_layout(
        title="Distribuição por Idioma",
        font=dict(family="Arial", size=13),
        margin=dict(t=60, b=20, l=20, r=20)
    )
    return fig


# ─────────────────────────────────────────────
# GERAÇÃO DO DASHBOARD HTML
# ─────────────────────────────────────────────
def generate_dashboard(analysis: dict, output_path: str):
    total = analysis["total_articles"]
    incident_dist = analysis["incident_distribution"]
    source_dist = analysis["source_distribution"]
    monthly_dist = analysis["monthly_distribution"]
    cat_dist = analysis["category_distribution"]
    global_tokens = analysis["global_top_tokens"]
    analyzed_articles = analysis["analyzed_articles"]
    lang_dist = analysis["lang_distribution"]

    # Cria figuras
    figs = {
        "pie_incident": fig_incident_pie(incident_dist),
        "bar_monthly": fig_monthly_bar(monthly_dist),
        "bar_source": fig_source_bar(source_dist),
        "radar_cat": fig_category_radar(cat_dist) if len(cat_dist) >= 3 else None,
        "bar_tokens": fig_top_tokens(global_tokens),
        "timeline": fig_incident_timeline(analyzed_articles),
        "pie_lang": fig_lang_pie(lang_dist),
    }

    # Converte figuras para HTML div
    def to_div(fig, div_id):
        if fig is None:
            return ""
        return pyo.plot(fig, output_type="div", include_plotlyjs=False,
                        config={"displayModeBar": True, "responsive": True})

    divs = {k: to_div(v, k) for k, v in figs.items()}

    # ── Tabela de artigos recentes ──
    recent = sorted(
        analyzed_articles,
        key=lambda a: a.get("published", ""),
        reverse=True
    )[:20]

    table_rows = ""
    for a in recent:
        pub = a.get("published", "")[:10]
        itype = a.get("incident_type", "—")
        color = COLORS.get(itype, "#999")
        cats = ", ".join(a.get("categories_found", []))
        title = a.get("title", "—")[:90]
        url = a.get("url", "#")
        source = a.get("source", "—")
        table_rows += f"""
        <tr>
          <td>{pub}</td>
          <td><a href="{url}" target="_blank">{title}…</a></td>
          <td>{source}</td>
          <td><span class="badge" style="background:{color}">{itype}</span></td>
          <td class="cats">{cats}</td>
        </tr>"""

    # ── Estatísticas de destaque ──
    top_incident = max(incident_dist, key=incident_dist.get) if incident_dist else "—"
    top_incident_count = incident_dist.get(top_incident, 0)
    top_source = max(source_dist, key=source_dist.get) if source_dist else "—"
    top_source_count = source_dist.get(top_source, 0)
    recent_month_count = sum(filter_last_year(monthly_dist).values()) if monthly_dist else 0

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Oil Spill Monitor — Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', Arial, sans-serif;
      background: #f0f2f5;
      color: #2c3e50;
    }}
    header {{
      background: linear-gradient(135deg, #1a252f 0%, #2c3e50 100%);
      color: white;
      padding: 24px 40px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; }}
    header h1 span {{ color: #e74c3c; }}
    header p {{ font-size: 0.85rem; opacity: 0.7; margin-top: 4px; }}
    .updated {{ font-size: 0.8rem; opacity: 0.6; text-align: right; }}

    .kpi-row {{
      display: flex;
      gap: 16px;
      padding: 24px 40px 8px;
      flex-wrap: wrap;
    }}
    .kpi {{
      background: white;
      border-radius: 10px;
      padding: 18px 24px;
      flex: 1;
      min-width: 160px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      border-left: 4px solid #2980b9;
    }}
    .kpi.red {{ border-left-color: #e74c3c; }}
    .kpi.green {{ border-left-color: #27ae60; }}
    .kpi.orange {{ border-left-color: #e67e22; }}
    .kpi .num {{ font-size: 2rem; font-weight: 700; color: #2c3e50; }}
    .kpi .label {{ font-size: 0.8rem; color: #7f8c8d; margin-top: 4px; }}

    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
      padding: 16px 40px;
    }}
    .grid.triple {{
      grid-template-columns: 1fr 1fr 1fr;
    }}
    .card {{
      background: white;
      border-radius: 10px;
      padding: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .card.full {{
      grid-column: 1 / -1;
    }}

    .section-title {{
      font-size: 1rem;
      font-weight: 600;
      color: #2c3e50;
      padding: 16px 40px 4px;
      border-left: 4px solid #e74c3c;
      margin: 8px 40px 0;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }}
    th {{
      background: #2c3e50;
      color: white;
      padding: 10px 12px;
      text-align: left;
      font-weight: 600;
    }}
    td {{
      padding: 8px 12px;
      border-bottom: 1px solid #f0f0f0;
      vertical-align: top;
    }}
    tr:hover td {{ background: #fafafa; }}
    td a {{ color: #2980b9; text-decoration: none; }}
    td a:hover {{ text-decoration: underline; }}
    .badge {{
      display: inline-block;
      padding: 2px 8px;
      border-radius: 12px;
      color: white;
      font-size: 0.75rem;
      font-weight: 600;
      white-space: nowrap;
    }}
    .cats {{ color: #7f8c8d; font-size: 0.78rem; }}

    footer {{
      text-align: center;
      padding: 24px;
      font-size: 0.78rem;
      color: #95a5a6;
      margin-top: 8px;
    }}
  </style>
</head>
<body>

<header>
  <div>
    <h1>Oil Spill <span>&amp; Offshore</span> Disaster Monitor</h1>
    <p>Crawler + Analisador Léxico de Notícias sobre Tragédias em Plataformas Offshore</p>
  </div>
  <div class="updated">Atualizado em:<br>{now_str}</div>
</header>

<!-- KPIs -->
<div class="kpi-row">
  <div class="kpi">
    <div class="num">{total}</div>
    <div class="label">Total de notícias coletadas</div>
  </div>
  <div class="kpi red">
    <div class="num">{recent_month_count}</div>
    <div class="label">Notícias no último ano</div>
  </div>
  <div class="kpi orange">
    <div class="num">{top_incident_count}</div>
    <div class="label">Tipo mais comum:<br>{top_incident}</div>
  </div>
  <div class="kpi green">
    <div class="num">{top_source_count}</div>
    <div class="label">Fonte mais ativa:<br>{top_source}</div>
  </div>
  <div class="kpi">
    <div class="num">{len(source_dist)}</div>
    <div class="label">Fontes monitoradas</div>
  </div>
</div>

<!-- Gráficos principais -->
<p class="section-title">Distribuição e Temporalidade</p>
<div class="grid">
  <div class="card">{divs['pie_incident']}</div>
  <div class="card">{divs['pie_lang']}</div>
  <div class="card full">{divs['bar_monthly']}</div>
  <div class="card full">{divs['timeline']}</div>
</div>

<p class="section-title">Análise Léxica</p>
<div class="grid triple">
  <div class="card">{divs['bar_source']}</div>
  <div class="card">{divs['bar_tokens']}</div>
  <div class="card">{divs['radar_cat'] if divs['radar_cat'] else '<p style="padding:40px;color:#999">Dados insuficientes para radar</p>'}</div>
</div>

<!-- Tabela de artigos recentes -->
<p class="section-title">Notícias Mais Recentes</p>
<div style="padding: 8px 40px 16px;">
  <div class="card" style="overflow-x:auto;">
    <table>
      <thead>
        <tr>
          <th>Data</th>
          <th>Título</th>
          <th>Fonte</th>
          <th>Tipo</th>
          <th>Categorias Léxicas</th>
        </tr>
      </thead>
      <tbody>
        {table_rows}
      </tbody>
    </table>
  </div>
</div>

<footer>
  Oil Spill Monitor &bull; Web Crawler + Analisador Léxico &bull; Python / Plotly
</footer>

</body>
</html>
"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Dashboard] Salvo em: {output_path}")
    return output_path


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    analysis_path = os.path.join(base, "data", "lexical_analysis.json")
    output_path = os.path.join(base, "dashboard.html")

    with open(analysis_path, "r", encoding="utf-8") as f:
        analysis = json.load(f)

    generate_dashboard(analysis, output_path)
