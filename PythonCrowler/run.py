"""
Oil Spill Offshore News Monitor
================================
Script principal — executa crawler, análise léxica e gera dashboard.

Uso:
    python run.py               # roda tudo
    python run.py --only-dash   # só regenera o dashboard (usa dados existentes)
"""

import os
import sys
import json
import webbrowser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "oil_crawler", "data")
NEWS_JSON = os.path.join(DATA_DIR, "news_data.json")
ANALYSIS_JSON = os.path.join(DATA_DIR, "lexical_analysis.json")
DASHBOARD_HTML = os.path.join(BASE_DIR, "dashboard.html")

os.makedirs(DATA_DIR, exist_ok=True)

# Adiciona oil_crawler ao path
sys.path.insert(0, os.path.join(BASE_DIR, "oil_crawler"))


def step_crawl():
    print("\n" + "═" * 60)
    print("  ETAPA 1 — WEB CRAWLER")
    print("═" * 60)
    from crawler import run_crawler
    articles = run_crawler(output_path=NEWS_JSON)
    return articles


def step_analyze(articles=None):
    print("\n" + "═" * 60)
    print("  ETAPA 2 — ANALISADOR LÉXICO")
    print("═" * 60)
    from lexer import analyze_corpus

    if articles is None:
        with open(NEWS_JSON, "r", encoding="utf-8") as f:
            articles = json.load(f)

    result = analyze_corpus(articles)

    with open(ANALYSIS_JSON, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[Léxico] {result['total_articles']} artigos analisados")
    print(f"[Léxico] Tipos de incidente:")
    for t, c in result["incident_distribution"].items():
        print(f"         {t}: {c}")
    return result


def step_dashboard(analysis=None):
    print("\n" + "═" * 60)
    print("  ETAPA 3 — DASHBOARD")
    print("═" * 60)
    from dashboard import generate_dashboard

    if analysis is None:
        with open(ANALYSIS_JSON, "r", encoding="utf-8") as f:
            analysis = json.load(f)

    generate_dashboard(analysis, DASHBOARD_HTML)
    return DASHBOARD_HTML


def main():
    only_dash = "--only-dash" in sys.argv

    if only_dash:
        if not os.path.exists(ANALYSIS_JSON):
            print("[ERRO] Nenhum dado de análise encontrado. Execute sem --only-dash primeiro.")
            sys.exit(1)
        analysis = step_dashboard()
    else:
        articles = step_crawl()

        if not articles:
            # Tenta carregar dados existentes
            if os.path.exists(NEWS_JSON):
                print("\n[!] Nenhum artigo novo coletado. Usando dados existentes.")
                with open(NEWS_JSON, "r", encoding="utf-8") as f:
                    articles = json.load(f)
            else:
                print("\n[!] Nenhum artigo coletado e nenhum dado existente.")
                print("    Verifique sua conexão com a internet.")
                sys.exit(1)

        analysis = step_analyze(articles)
        step_dashboard(analysis)

    print("\n" + "═" * 60)
    print("  CONCLUÍDO!")
    print(f"  Dashboard: {DASHBOARD_HTML}")
    print("═" * 60)

    # Abre o dashboard no navegador
    try:
        webbrowser.open(f"file:///{DASHBOARD_HTML.replace(os.sep, '/')}")
        print("\n  [✓] Dashboard aberto no navegador.")
    except Exception:
        print(f"\n  Abra manualmente: {DASHBOARD_HTML}")


if __name__ == "__main__":
    main()
