"""
Analisador Léxico para notícias de vazamento de petróleo offshore.

Realiza:
  - Tokenização do texto
  - Classificação dos tokens por categoria semântica
  - Contagem de frequências
  - Categorização das notícias (tipo de incidente)
  - Extração de entidades geográficas simples
"""

import re
import json
from collections import Counter, defaultdict
from typing import List, Dict, Tuple


# ─────────────────────────────────────────────
# LÉXICO: categorias semânticas
# ─────────────────────────────────────────────
LEXICON = {
    "VAZAMENTO": [
        "spill", "leak", "leakage", "seepage", "discharge",
        "vazamento", "derramamento", "escape", "extravasamento"
    ],
    "EXPLOSÃO": [
        "explosion", "blast", "blowout", "fire", "ignition", "combustion",
        "explosão", "incêndio", "detonação", "chama", "queima"
    ],
    "AFUNDAMENTO": [
        "sinking", "capsizing", "collapse", "structural failure", "foundering",
        "afundamento", "naufrágio", "colapso", "submersão"
    ],
    "PLATAFORMA": [
        "offshore", "platform", "rig", "drilling", "deepwater", "subsea",
        "well", "pipeline", "fpso", "semisubmersible",
        "plataforma", "poço", "duto", "submarino", "perfuração"
    ],
    "IMPACTO_AMBIENTAL": [
        "contamination", "pollution", "environmental", "ecosystem", "wildlife",
        "cleanup", "remediation", "toxic", "marine", "coast",
        "contaminação", "poluição", "ambiental", "ecossistema", "fauna",
        "limpeza", "tóxico", "marinho", "costa", "litoral"
    ],
    "VÍTIMAS": [
        "death", "dead", "killed", "injured", "missing", "workers", "crew",
        "rescue", "survivors", "casualties", "fatalities",
        "morte", "morto", "ferido", "desaparecido", "trabalhadores",
        "resgate", "sobreviventes", "vítimas", "tripulação"
    ],
    "EMPRESA": [
        "petrobras", "bp", "shell", "exxon", "chevron", "total", "equinor",
        "halliburton", "transocean", "schlumberger", "saipem"
    ],
    "LOCALIZAÇÃO": [
        "gulf of mexico", "north sea", "amazon", "santos basin", "campos basin",
        "atlantic", "pacific", "arabian sea", "persian gulf", "nigeria", "brazil",
        "golfo do méxico", "mar do norte", "bacia de santos", "bacia de campos",
        "atlântico", "brasil", "nigéria"
    ],
}

# Mapa inverso token → categoria
TOKEN_MAP: Dict[str, str] = {}
for category, terms in LEXICON.items():
    for term in terms:
        TOKEN_MAP[term.lower()] = category


# ─────────────────────────────────────────────
# FUNÇÕES DE TOKENIZAÇÃO
# ─────────────────────────────────────────────
def tokenize(text: str) -> List[str]:
    """
    Tokenizador léxico simples:
    - Converte para minúsculas
    - Remove pontuação (mantém hífens dentro de palavras)
    - Divide por espaços e separadores
    """
    text = text.lower()
    # Normaliza caracteres especiais comuns
    text = re.sub(r"[''`]", "", text)
    text = re.sub(r"[^\w\s\-]", " ", text)
    tokens = re.split(r"[\s\-]+", text)
    return [t for t in tokens if len(t) > 2]  # descarta tokens muito curtos


def match_phrases(text: str) -> List[Tuple[str, str]]:
    """
    Tenta casar expressões multipalavra do léxico antes da tokenização simples.
    Retorna lista de (termo, categoria) encontrados no texto.
    """
    text_lower = text.lower()
    matches = []
    # Ordena por comprimento decrescente (prioriza frases mais longas)
    for term in sorted(TOKEN_MAP.keys(), key=len, reverse=True):
        if " " in term and term in text_lower:
            matches.append((term, TOKEN_MAP[term]))
    return matches


def classify_tokens(tokens: List[str]) -> Dict[str, List[str]]:
    """Classifica cada token em sua categoria léxica."""
    classified = defaultdict(list)
    for token in tokens:
        category = TOKEN_MAP.get(token)
        if category:
            classified[category].append(token)
    return dict(classified)


# ─────────────────────────────────────────────
# ANÁLISE DE UM ARTIGO
# ─────────────────────────────────────────────
def analyze_article(article: dict) -> dict:
    """
    Realiza análise léxica completa de um artigo.
    Retorna dicionário com tokens, categorias e tipo de incidente.
    """
    text = f"{article.get('title', '')} {article.get('summary', '')}"

    tokens = tokenize(text)
    phrase_matches = match_phrases(text)
    classified = classify_tokens(tokens)

    # Adiciona matches de frases às categorias
    for term, cat in phrase_matches:
        if term not in classified.get(cat, []):
            classified.setdefault(cat, []).append(term)

    # Determina tipo principal de incidente
    incident_type = determine_incident_type(classified)

    # Frequência de todos os tokens (excluindo stopwords comuns)
    stopwords = {
        "the", "and", "for", "are", "was", "has", "have", "been",
        "with", "that", "this", "from", "will", "its", "not",
        "uma", "para", "com", "que", "dos", "das", "por", "seu",
        "sua", "mais", "sobre", "após", "como", "após"
    }
    freq = Counter(t for t in tokens if t not in stopwords)

    return {
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "source": article.get("source", ""),
        "lang": article.get("lang", ""),
        "published": article.get("published", ""),
        "incident_type": incident_type,
        "categories_found": list(classified.keys()),
        "classified_tokens": classified,
        "top_tokens": freq.most_common(10),
        "token_count": len(tokens),
        "keywords_found": article.get("keywords_found", [])
    }


def determine_incident_type(classified: Dict[str, List[str]]) -> str:
    """
    Define o tipo principal do incidente com base nas categorias detectadas.
    Prioridade: EXPLOSÃO > AFUNDAMENTO > VAZAMENTO > IMPACTO_AMBIENTAL > OUTRO
    """
    if "EXPLOSÃO" in classified:
        return "Explosão / Incêndio"
    if "AFUNDAMENTO" in classified:
        return "Afundamento / Colapso"
    if "VAZAMENTO" in classified:
        return "Vazamento / Derramamento"
    if "IMPACTO_AMBIENTAL" in classified:
        return "Impacto Ambiental"
    if "PLATAFORMA" in classified:
        return "Incidente Offshore (geral)"
    return "Outro"


# ─────────────────────────────────────────────
# ANÁLISE DO CORPUS COMPLETO
# ─────────────────────────────────────────────
def analyze_corpus(articles: List[dict]) -> dict:
    """
    Analisa todos os artigos e retorna estatísticas agregadas.
    """
    analyzed = [analyze_article(a) for a in articles]

    # Frequência global de tokens
    global_freq: Counter = Counter()
    for a in analyzed:
        global_freq.update(dict(a["top_tokens"]))

    # Distribuição por tipo de incidente
    incident_dist = Counter(a["incident_type"] for a in analyzed)

    # Distribuição por fonte
    source_dist = Counter(a["source"] for a in analyzed)

    # Distribuição por idioma
    lang_dist = Counter(a["lang"] for a in analyzed)

    # Distribuição por categoria léxica
    cat_dist = Counter()
    for a in analyzed:
        for cat in a["categories_found"]:
            cat_dist[cat] += 1

    # Distribuição temporal (por mês)
    monthly_dist: Dict[str, int] = defaultdict(int)
    for a in analyzed:
        pub = a.get("published", "")
        if pub:
            try:
                month = pub[:7]  # "YYYY-MM"
                monthly_dist[month] += 1
            except Exception:
                pass

    return {
        "total_articles": len(analyzed),
        "analyzed_articles": analyzed,
        "global_top_tokens": global_freq.most_common(30),
        "incident_distribution": dict(incident_dist),
        "source_distribution": dict(source_dist),
        "lang_distribution": dict(lang_dist),
        "category_distribution": dict(cat_dist),
        "monthly_distribution": dict(sorted(monthly_dist.items())),
    }


# ─────────────────────────────────────────────
# MAIN (uso standalone)
# ─────────────────────────────────────────────
def run_analysis(input_path: str, output_path: str = None) -> dict:
    with open(input_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    print(f"[Léxico] Analisando {len(articles)} artigos...")
    result = analyze_corpus(articles)

    print(f"[Léxico] Tipos de incidente encontrados:")
    for itype, count in result["incident_distribution"].items():
        print(f"  {itype}: {count}")

    if output_path:
        import os
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[Léxico] Análise salva em: {output_path}")

    return result


if __name__ == "__main__":
    import os
    base = os.path.dirname(os.path.abspath(__file__))
    run_analysis(
        input_path=os.path.join(base, "data", "news_data.json"),
        output_path=os.path.join(base, "data", "lexical_analysis.json")
    )
