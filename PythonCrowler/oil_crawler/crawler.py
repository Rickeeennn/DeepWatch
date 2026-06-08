"""
Oil Spill & Offshore Disaster News Crawler
Fontes: Google News RSS, Reuters RSS, BBC RSS, Agência Brasil, G1
"""

import feedparser
import requests
from bs4 import BeautifulSoup
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus, urljoin
import time

# ─────────────────────────────────────────────
# CONFIGURAÇÃO DE PALAVRAS-CHAVE
# ─────────────────────────────────────────────
KEYWORDS_EN = [
    "oil spill", "oil leak", "offshore disaster", "offshore accident",
    "oil platform explosion", "blowout offshore", "oil rig explosion",
    "petroleum spill", "deepwater disaster", "oil contamination sea",
    "oil platform fire", "offshore oil incident"
]

KEYWORDS_PT = [
    "vazamento de petróleo", "derramamento de petróleo", "desastre offshore",
    "acidente plataforma petróleo", "explosão plataforma petróleo",
    "blowout offshore", "óleo mar", "contaminação petróleo",
    "plataforma petróleo acidente", "derramamento óleo offshore",
    "incêndio plataforma offshore", "vazamento offshore"
]

ALL_KEYWORDS = KEYWORDS_EN + KEYWORDS_PT

# ─────────────────────────────────────────────
# FONTES RSS
# ─────────────────────────────────────────────
def build_google_news_urls():
    urls = []
    for kw in KEYWORDS_EN[:4]:
        encoded = quote_plus(kw)
        urls.append({
            "source": "Google News (EN)",
            "url": f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en",
            "lang": "en"
        })
    for kw in KEYWORDS_PT[:4]:
        encoded = quote_plus(kw)
        urls.append({
            "source": "Google News (PT)",
            "url": f"https://news.google.com/rss/search?q={encoded}&hl=pt-BR&gl=BR&ceid=BR:pt-419",
            "lang": "pt"
        })
    return urls

STATIC_FEEDS = [
    {
        "source": "Reuters",
        "url": "https://feeds.reuters.com/reuters/environmentNews",
        "lang": "en"
    },
    {
        "source": "BBC Environment",
        "url": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "lang": "en"
    },
    {
        "source": "Agência Brasil",
        "url": "https://agenciabrasil.ebc.com.br/rss/meio-ambiente/feed.xml",
        "lang": "pt"
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ─────────────────────────────────────────────
# FUNÇÕES AUXILIARES
# ─────────────────────────────────────────────
def parse_date(entry):
    """Tenta extrair data do entry do feedparser."""
    for attr in ("published_parsed", "updated_parsed"):
        t = getattr(entry, attr, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def is_relevant(text: str) -> bool:
    """Verifica se o texto contém pelo menos uma palavra-chave relevante."""
    low = text.lower()
    for kw in ALL_KEYWORDS:
        if kw.lower() in low:
            return True
    return False


def clean_html(raw: str) -> str:
    """Remove tags HTML de uma string."""
    return BeautifulSoup(raw or "", "html.parser").get_text(separator=" ").strip()


# ─────────────────────────────────────────────
# CRAWLER PRINCIPAL
# ─────────────────────────────────────────────
def fetch_feed(feed_info: dict, seen_urls: set) -> list:
    """Busca e filtra artigos de um feed RSS."""
    articles = []
    try:
        feed = feedparser.parse(
            feed_info["url"],
            request_headers=HEADERS,
            agent=HEADERS["User-Agent"]
        )
        for entry in feed.entries:
            link = getattr(entry, "link", "")
            if link in seen_urls:
                continue

            title = getattr(entry, "title", "")
            summary = clean_html(getattr(entry, "summary", ""))
            combined = f"{title} {summary}"

            if not is_relevant(combined):
                continue

            seen_urls.add(link)
            articles.append({
                "title": title,
                "url": link,
                "summary": summary,
                "source": feed_info["source"],
                "lang": feed_info["lang"],
                "published": parse_date(entry),
                "keywords_found": [kw for kw in ALL_KEYWORDS if kw.lower() in combined.lower()]
            })
    except Exception as e:
        print(f"  [ERRO] {feed_info['source']}: {e}")
    return articles


def fetch_g1_offshore(seen_urls: set) -> list:
    """Scraping direto do G1 via busca."""
    articles = []
    queries = ["vazamento petróleo offshore", "acidente plataforma petróleo"]
    for q in queries:
        try:
            url = f"https://g1.globo.com/busca/?q={quote_plus(q)}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            # Cards de notícia do G1
            for card in soup.select("div.widget--info__text-container, div.feed-post-body"):
                a_tag = card.find("a", href=True)
                title_tag = card.find(["h2", "a"])
                if not a_tag or not title_tag:
                    continue
                link = a_tag["href"]
                if not link.startswith("http"):
                    link = urljoin("https://g1.globo.com", link)
                if link in seen_urls:
                    continue
                title = title_tag.get_text(strip=True)
                if not is_relevant(title):
                    continue
                seen_urls.add(link)
                articles.append({
                    "title": title,
                    "url": link,
                    "summary": "",
                    "source": "G1",
                    "lang": "pt",
                    "published": datetime.now(timezone.utc).isoformat(),
                    "keywords_found": [kw for kw in ALL_KEYWORDS if kw.lower() in title.lower()]
                })
            time.sleep(1)
        except Exception as e:
            print(f"  [ERRO] G1 scraping: {e}")
    return articles


def run_crawler(output_path: str = None) -> list:
    """Executa o crawler completo e retorna lista de artigos."""
    print("=" * 60)
    print("  OIL SPILL OFFSHORE NEWS CRAWLER")
    print(f"  Iniciado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    seen_urls = set()
    all_articles = []

    # 1. Feeds estáticos
    feeds = STATIC_FEEDS + build_google_news_urls()
    for feed_info in feeds:
        print(f"\n[+] Buscando: {feed_info['source']} ...")
        articles = fetch_feed(feed_info, seen_urls)
        all_articles.extend(articles)
        print(f"    → {len(articles)} artigos relevantes encontrados")
        time.sleep(0.5)

    # 2. G1 scraping direto
    print("\n[+] Buscando: G1 (scraping direto) ...")
    g1_articles = fetch_g1_offshore(seen_urls)
    all_articles.extend(g1_articles)
    print(f"    → {len(g1_articles)} artigos relevantes encontrados")

    print(f"\n{'=' * 60}")
    print(f"  TOTAL DE ARTIGOS COLETADOS: {len(all_articles)}")
    print("=" * 60)

    # Salvar JSON
    if output_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(script_dir, "data", "news_data.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Mesclar com dados existentes se houver
    existing = []
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_urls = {a["url"] for a in existing}
            new_only = [a for a in all_articles if a["url"] not in existing_urls]
            merged = existing + new_only
            print(f"\n  Novos artigos adicionados: {len(new_only)}")
            print(f"  Total acumulado: {len(merged)}")
        except Exception:
            merged = all_articles
    else:
        merged = all_articles

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    print(f"\n  Dados salvos em: {output_path}")
    return merged


if __name__ == "__main__":
    run_crawler()
