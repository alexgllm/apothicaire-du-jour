from __future__ import annotations

import json
import os
import random
from datetime import date
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

ROOT = Path(__file__).parent
PLANTS_FILE = ROOT / "data" / "plants.json"
OUT_FILE = ROOT / "docs" / "today.json"
START_DATE = date(2026, 1, 1)
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")


def load_plants() -> list[str]:
    return json.loads(PLANTS_FILE.read_text(encoding="utf-8"))


def choose_plant(plants: list[str]) -> str:
    days = (date.today() - START_DATE).days
    return plants[days % len(plants)]


def fallback_payload(plant: str) -> dict[str, Any]:
    rng = random.Random(plant)
    return {
        "date": date.today().isoformat(),
        "plant_name": plant,
        "latin_name": "À compléter",
        "where_grows": "À compléter",
        "culinary_uses": "À compléter",
        "traditional_benefits": "À compléter",
        "precautions": "Contenu informatif uniquement.",
        "quiz": [
            {
                "question": f"Quel est le point à retenir sur {plant} ?",
                "choices": ["Réponse A", "Réponse B", "Réponse C", "Réponse D"],
                "answer": "Réponse A"
            },
            {
                "question": "Quelle donnée dois-tu relire ?",
                "choices": ["Où ça pousse", "La couleur du ciel", "Le code postal", "Le nom du chat"],
                "answer": "Où ça pousse"
            },
            {
                "question": "Quel format doit rester la sortie ?",
                "choices": ["JSON", "PDF", "PNG", "DOCX"],
                "answer": "JSON"
            }
        ]
    }


def build_prompt(plant: str) -> str:
    return f"""
Tu es un assistant pédagogique spécialisé dans les plantes.

Utilise l'outil de recherche Google pour vérifier les informations à jour sur cette plante : {plant}.

Réponds uniquement en JSON valide, sans texte autour.
Le JSON doit contenir exactement ces clés :
- date
- plant_name
- latin_name
- where_grows
- culinary_uses
- traditional_benefits
- precautions
- quiz

Le champ quiz doit être un tableau de 3 objets.
Chaque objet doit contenir :
- question
- choices (4 réponses)
- answer (une seule des 4 réponses)

Règles de rédaction :
- français simple
- prudence sur les bienfaits : pas de promesse médicale
- si une info est incertaine, formule-la avec prudence
- garde des réponses courtes et claires
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


def main() -> None:
    plants = load_plants()
    plant = choose_plant(plants)

    client = genai.Client()
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(
        tools=[grounding_tool],
        temperature=0.4,
        response_mime_type="application/json",
    )

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=build_prompt(plant),
            config=config,
        )
        data = parse_json(response.text)
    except Exception:
        data = fallback_payload(plant)

    data.setdefault("date", date.today().isoformat())
    data.setdefault("plant_name", plant)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
