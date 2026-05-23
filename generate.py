from __future__ import annotations

import json
import os
import random
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

ROOT = Path(__file__).parent
PLANTS_FILE = ROOT / "data" / "plants.json"
OUT_FILE = ROOT / "docs" / "today.json"
START_DATE = date(2026, 1, 1)
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


def load_plants() -> list[str]:
    return json.loads(PLANTS_FILE.read_text(encoding="utf-8"))


def choose_plant(plants: list[str]) -> str:
    days = (date.today() - START_DATE).days
    return plants[days % len(plants)]


def fetch_wikipedia_summary(query: str) -> dict[str, str]:
    """Find a French Wikipedia summary for the plant name."""
    search_url = "https://fr.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
        "srlimit": 1,
    }
    try:
        r = requests.get(search_url, params=params, timeout=20)
        r.raise_for_status()
        payload = r.json()
        hits = payload.get("query", {}).get("search", [])
        if not hits:
            return {"title": query, "extract": ""}

        title = hits[0]["title"]
        summary_url = f"https://fr.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
        s = requests.get(summary_url, timeout=20)
        s.raise_for_status()
        data = s.json()
        return {
            "title": data.get("title", title),
            "extract": data.get("extract", ""),
            "description": data.get("description", ""),
            "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        }
    except Exception:
        return {"title": query, "extract": ""}


def fallback_payload(plant: str) -> dict[str, Any]:
    return {
        "date": date.today().isoformat(),
        "plant_name": plant,
        "latin_name": "A completer",
        "where_grows": "A completer",
        "culinary_uses": "A completer",
        "traditional_benefits": "A completer",
        "precautions": "Contenu informatif uniquement.",
        "quiz": [
            {
                "question": f"Quel est le point a retenir sur {plant} ?",
                "choices": ["Reponse A", "Reponse B", "Reponse C", "Reponse D"],
                "answer": "Reponse A",
            },
            {
                "question": "Quelle donnee dois-tu relire ?",
                "choices": ["Ou ca pousse", "La couleur du ciel", "Le code postal", "Le nom du chat"],
                "answer": "Ou ca pousse",
            },
            {
                "question": "Quel format doit rester la sortie ?",
                "choices": ["JSON", "PDF", "PNG", "DOCX"],
                "answer": "JSON",
            },
        ],
    }


def build_prompt(plant: str, wiki: dict[str, str]) -> str:
    wiki_text = wiki.get("extract", "") or "Aucune description Wikipedia trouvee."
    wiki_title = wiki.get("title", plant)
    wiki_url = wiki.get("url", "")

    return f"""
Tu es un assistant pedagogique specialise dans les plantes.

Tu dois produire une fiche en francais simple, prudente et utile pour apprendre.
Base-toi sur les notes ci-dessous, puis complete avec prudence si besoin.
N'invente pas de proprietes medicales fortes.
Si une info est incertaine, reste vague.

Plante: {plant}
Source Wikipedia: {wiki_title}
URL: {wiki_url}

Notes:
{wiki_text}

Reponds uniquement en JSON valide, sans texte autour.
Le JSON doit contenir exactement ces cles :
- date
- plant_name
- latin_name
- where_grows
- culinary_uses
- traditional_benefits
- precautions
- quiz

Le champ quiz doit etre un tableau de 3 objets.
Chaque objet doit contenir :
- question
- choices (4 reponses)
- answer (une seule des 4 reponses)

Règles:
- francais simple
- prudence sur les bienfaits
- si une info est incertaine, formule-la avec prudence
- garde des reponses courtes et claires
""".strip()


def parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start : end + 1])
        raise


def gemini_generate(prompt: str) -> dict[str, Any]:
    if not API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }

    r = requests.post(
        GEMINI_ENDPOINT,
        headers={
            "x-goog-api-key": API_KEY,
            "Content-Type": "application/json",
        },
        json=body,
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("No candidates returned from Gemini")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(part.get("text", "") for part in parts)
    if not text:
        raise RuntimeError("Empty Gemini response text")
    return parse_json(text)


def main() -> None:
    plants = load_plants()
    plant = choose_plant(plants)
    wiki = fetch_wikipedia_summary(plant)

    try:
        data = gemini_generate(build_prompt(plant, wiki))
    except Exception:
        data = fallback_payload(plant)

    data.setdefault("date", date.today().isoformat())
    data.setdefault("plant_name", plant)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
