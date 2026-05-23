from __future__ import annotations

import json
import os
import random
import re
import unicodedata
from datetime import date
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
OUT_FILE = ROOT / "docs" / "today.json"

START_DATE = date(2026, 1, 1)
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

HEADERS = {"User-Agent": "Mozilla/5.0"}

VIDAL_URL = "https://www.vidal.fr/parapharmacie/phytotherapie-plantes.html"
FERME_URL = "https://www.fermedelours.fr/guide-des-plantes/"
HERBO_URL = "https://www.herboristerie.bzh/blog/comment-profiter-des-bienfaits-des-plantes-sur-la-sante"

PLANTS = [
    "Pissenlit",
    "Romarin",
    "Menthe poivrée",
    "Thym",
    "Sauge",
    "Camomille",
    "Lavande",
    "Ortie",
    "Basilic",
    "Mélisse",
    "Fenouil",
    "Verveine",
]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def clean_text(node) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", unescape(node.get_text(" ", strip=True))).strip()


def fetch_html(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=25)
    response.raise_for_status()
    return response.text


def extract_general_text_from_html(html: str, max_chars: int = 2800) -> str:
    soup = BeautifulSoup(html, "html.parser")
    container = soup.find("main") or soup.find("article") or soup.body or soup
    texts: list[str] = []

    for tag in container.find_all(["p", "li"], recursive=True):
        txt = clean_text(tag)
        if len(txt) > 40:
            texts.append(txt)
        if len(" ".join(texts)) >= max_chars:
            break

    return " ".join(texts)[:max_chars]


def extract_section_for_plant(url: str, plant: str, max_chars: int = 2400) -> str:
    try:
        html = fetch_html(url)
    except Exception:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    target = normalize(plant)

    for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
        heading_text = normalize(clean_text(heading))
        if not heading_text:
            continue

        if heading_text == target or target in heading_text or heading_text in target:
            parts: list[str] = []
            for sib in heading.next_siblings:
                if getattr(sib, "name", None) in ("h1", "h2", "h3", "h4"):
                    break
                if hasattr(sib, "get_text"):
                    txt = clean_text(sib)
                else:
                    txt = str(sib).strip()
                if txt:
                    parts.append(txt)
                if len(" ".join(parts)) >= max_chars:
                    break

            snippet = " ".join(parts).strip()
            if snippet:
                return snippet[:max_chars]

    paras: list[str] = []
    for tag in soup.find_all(["p", "li"]):
        txt = clean_text(tag)
        if len(txt) > 40 and target in normalize(txt):
            paras.append(txt)

    if paras:
        return " ".join(paras)[:max_chars]

    return extract_general_text_from_html(html, max_chars=max_chars)


def extract_keywords_from_page(url: str, keywords: list[str], max_chars: int = 2600) -> str:
    try:
        html = fetch_html(url)
    except Exception:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    paras: list[str] = []

    for tag in soup.find_all(["p", "li"]):
        txt = clean_text(tag)
        if len(txt) < 35:
            continue
        norm = normalize(txt)
        if any(k in norm for k in keywords):
            paras.append(txt)

    if paras:
        return " ".join(paras)[:max_chars]

    return extract_general_text_from_html(html, max_chars=max_chars)


def fetch_wikipedia_summary(title: str) -> dict[str, str]:
    url = f"https://fr.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        image = (
            data.get("originalimage", {}).get("source")
            or data.get("thumbnail", {}).get("source", "")
        )

        return {
            "title": data.get("title", title),
            "extract": data.get("extract", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "image": image,
        }
    except Exception:
        return {"title": title, "extract": "", "url": "", "image": ""}


def choose_plant() -> str:
    days = (date.today() - START_DATE).days
    return PLANTS[days % len(PLANTS)]


def build_source_pack(plant: str) -> dict[str, str]:
    wiki = fetch_wikipedia_summary(plant)

    vidal = extract_section_for_plant(VIDAL_URL, plant)
    ferme = extract_section_for_plant(FERME_URL, plant)
    herbo = extract_keywords_from_page(
        HERBO_URL,
        [
            "bienfaits",
            "régularité",
            "dose",
            "dosage",
            "contre-indication",
            "interactions",
            "professionnel",
            "plante",
            "plantes",
            "santé",
        ],
    )

    return {
        "wiki_title": wiki.get("title", plant),
        "wiki_extract": wiki.get("extract", ""),
        "wiki_image": wiki.get("image", ""),
        "wiki_url": wiki.get("url", ""),
        "vidal": vidal,
        "ferme": ferme,
        "herbo": herbo,
    }


def build_prompt(plant: str, sources: dict[str, str]) -> str:
    return f"""
Tu écris en français pour un site d'apprentissage des plantes.

Objectif:
Produire une fiche originale, claire, agréable à lire et utile.
Évite de répéter les mêmes phrases entre les sections.
Le quiz doit porter sur la plante du jour et sur ses caractéristiques réelles.

Règles:
- N'invente pas de faits précis si les sources sont floues.
- Si une info est incertaine, reste prudent.
- Pas de conseil médical.
- Réponds UNIQUEMENT avec un JSON valide.
- N'utilise pas de Markdown.
- Garde des formulations différentes entre:
  where_grows, culinary_uses, traditional_benefits, precautions.

Tu peux t'appuyer sur ces sources:

[WIKIPEDIA]
Titre: {sources["wiki_title"]}
Résumé: {sources["wiki_extract"]}
Image: {sources["wiki_image"]}
Lien: {sources["wiki_url"]}

[VIDAL]
{sources["vidal"] or "Aucun extrait pertinent trouvé."}

[LA FERME DE L'OURS]
{sources["ferme"] or "Aucun extrait pertinent trouvé."}

[HERBORISTERIE]
{sources["herbo"] or "Aucun extrait pertinent trouvé."}

Format JSON attendu:
{{
  "date": "YYYY-MM-DD",
  "plant_name": "{plant}",
  "latin_name": "",
  "where_grows": "",
  "culinary_uses": "",
  "traditional_benefits": "",
  "precautions": "",
  "image": ""
}}

Consignes par champ:
- latin_name: nom latin ou nom scientifique si connu.
- where_grows: 2 à 3 phrases sur l'habitat, le climat, les sols, les régions.
- culinary_uses: 2 à 4 idées concrètes, seulement si la plante s'y prête.
- traditional_benefits: 4 à 6 phrases, plus riche et plus détaillé que le reste.
- precautions: 2 à 4 phrases prudentes, avec contre-indications ou interactions si pertinent.
- image: laisse vide si tu n'es pas sûr.

Réponds maintenant avec uniquement le JSON.
""".strip()


def call_gemini(prompt: str) -> dict:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY manquante")

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL}:generateContent?key={API_KEY}"
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.6,
            "responseMimeType": "application/json",
            "maxOutputTokens": 2048,
        },
    }

    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urlopen(req, timeout=60) as resp:
        raw = json.loads(resp.read().decode("utf-8"))

    text = raw["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def sentence_snippet(text: str, max_words: int = 10) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return "Information non précisée"
    text = text.split(".")[0].strip()
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",;:") + "…"


def unique_options(correct: str, distractors: list[str]) -> list[str]:
    seen = set()
    options = []
    for item in [correct] + distractors:
        item = item.strip()
        if item and item not in seen:
            options.append(item)
            seen.add(item)
    while len(options) < 4:
        filler = f"Option {len(options) + 1}"
        if filler not in seen:
            options.append(filler)
            seen.add(filler)
    return options[:4]


def build_quiz(data: dict) -> list[dict]:
    rng = random.Random(date.today().isoformat())

    habitat_correct = sentence_snippet(data.get("where_grows", ""), 12)
    culinary_correct = sentence_snippet(data.get("culinary_uses", ""), 12)
    benefit_correct = sentence_snippet(data.get("traditional_benefits", ""), 12)
    precaution_correct = sentence_snippet(data.get("precautions", ""), 12)

    habitat_distractors = [
        "Sols secs et très ensoleillés",
        "Zones humides et ombragées",
        "Milieux tropicaux très chauds",
        "Régions alpines très froides",
        "Bords de chemins et prairies",
    ]
    culinary_distractors = [
        "À consommer en salade ou en infusion",
        "En soupe, en tisane ou en condiment",
        "En dessert ou en boisson aromatique",
        "En assaisonnement de plats simples",
        "En macération ou en huile parfumée",
    ]
    benefit_distractors = [
        "Traditionnellement associée au confort digestif",
        "Souvent utilisée pour la détente et l'apaisement",
        "Appréciée pour son côté tonique ou stimulant",
        "Connu pour ses usages populaires en tisane",
        "Réputée pour un emploi traditionnel varié",
    ]
    precaution_distractors = [
        "Peut interagir avec certains traitements",
        "À éviter en cas de grossesse sans avis médical",
        "Demande prudence si elle est très concentrée",
        "Contenu informatif, pas un conseil médical",
        "Toujours tester les usages avec prudence",
    ]

    quiz = []

    q1 = unique_options(habitat_correct, rng.sample(habitat_distractors, 3))
    q1 = rng.sample(q1, len(q1))
    quiz.append({
        "question": "Où pousse surtout cette plante ?",
        "choices": q1,
        "answer": habitat_correct,
    })

    q2 = unique_options(culinary_correct, rng.sample(culinary_distractors, 3))
    q2 = rng.sample(q2, len(q2))
    quiz.append({
        "question": "Quel usage culinaire correspond le mieux à cette plante ?",
        "choices": q2,
        "answer": culinary_correct,
    })

    q3 = unique_options(benefit_correct, rng.sample(benefit_distractors, 3))
    q3 = rng.sample(q3, len(q3))
    quiz.append({
        "question": "Quel bienfait traditionnel est le mieux mis en avant ?",
        "choices": q3,
        "answer": benefit_correct,
    })

    q4 = unique_options(precaution_correct, rng.sample(precaution_distractors, 3))
    q4 = rng.sample(q4, len(q4))
    quiz.append({
        "question": "Quelle précaution doit être retenue ?",
        "choices": q4,
        "answer": precaution_correct,
    })

    return quiz


def fallback_result(plant: str, sources: dict[str, str]) -> dict:
    today = date.today().isoformat()

    wiki_extract = sources.get("wiki_extract", "").strip()
    return {
        "date": today,
        "plant_name": plant,
        "latin_name": "",
        "where_grows": wiki_extract or "Information non récupérée automatiquement.",
        "culinary_uses": "La plante peut parfois être utilisée en tisane, en cuisine ou en condiment, selon l'espèce.",
        "traditional_benefits": wiki_extract or "Contenu informatif non disponible pour le moment.",
        "precautions": "Contenu informatif uniquement. En cas de doute, demande l'avis d'un professionnel de santé.",
        "image": sources.get("wiki_image", ""),
    }


def main() -> None:
    plant = choose_plant()
    sources = build_source_pack(plant)
    prompt = build_prompt(plant, sources)

    try:
        data = call_gemini(prompt)
    except Exception:
        data = fallback_result(plant, sources)
    else:
        data.setdefault("date", date.today().isoformat())
        data.setdefault("plant_name", plant)
        data.setdefault("image", sources.get("wiki_image", ""))
        if not data.get("image"):
            data["image"] = sources.get("wiki_image", "")

    data["quiz"] = build_quiz(data)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
