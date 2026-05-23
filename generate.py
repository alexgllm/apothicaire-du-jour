from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
OUT_FILE = ROOT / "docs" / "today.json"
START_DATE = date(2026, 1, 1)
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

PLANTS = [
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
    "Pissenlit",
    "Verveine",
]


def choose_plant() -> str:
    days = (date.today() - START_DATE).days
    return PLANTS[days % len(PLANTS)]


def fetch_wikipedia_summary(title: str) -> dict[str, str]:
    url = f"https://fr.wikipedia.org/api/rest_v1/page/summary/{quote(title)}"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
return {
    "title": data.get("title", title),
    "extract": data.get("extract", ""),
    "url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    "image": data.get("thumbnail", {}).get("source", "")
        }
    except Exception:
        return {"title": title, "extract": "", "url": ""}


def build_prompt(plant: str, wiki: dict[str, str]) -> str:
    source = wiki["extract"].strip() or "Aucun extrait Wikipedia n'a pu être récupéré."
    return f"""
Tu écris en français, avec prudence, sur les plantes.

Plante du jour: {plant}
Source de contexte:
{source}

Tâche:
Retourne UNIQUEMENT un JSON valide, sans texte autour, avec exactement ces clés:
- date
- plant_name
- latin_name
- where_grows
- culinary_uses
- traditional_benefits
- precautions
- image
- quiz

Contraintes:
- Si une information n'est pas certaine, indique-le avec prudence.
- Pas de promesse médicale.
- Ton clair, simple, pédagogique.
- Le champ quiz doit être un tableau de 3 objets.
- Chaque objet quiz doit contenir:
  - question
  - choices (4 chaînes)
  - answer (une seule des choices)

Format JSON attendu:
{{
  "date": "YYYY-MM-DD",
  "plant_name": "{plant}",
  "latin_name": "",
  "where_grows": "",
  "culinary_uses": "",
  "traditional_benefits": "",
  "precautions": "",
"image": "",
  "quiz": [
    {{"question": "", "choices": ["", "", "", ""], "answer": ""}},
    {{"question": "", "choices": ["", "", "", ""], "answer": ""}},
    {{"question": "", "choices": ["", "", "", ""], "answer": ""}}
  ]
}}
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
            "temperature": 0.4,
            "responseMimeType": "application/json",
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


def fallback_result(plant: str) -> dict:
    today = date.today().isoformat()
    return {
        "date": today,
        "plant_name": plant,
        "latin_name": "",
        "where_grows": "",
        "culinary_uses": "",
        "traditional_benefits": "",
        "precautions": "",
        "image": "",
        "quiz": [
            {
                "question": "Quelle est la plante du jour ?",
                "choices": [plant, "Carotte", "Tomate", "Poireau"],
                "answer": plant,
            },
            {
                "question": "Cette fiche a-t-elle pu être générée par Gemini ?",
                "choices": ["Oui", "Non", "Peut-être", "Je ne sais pas"],
                "answer": "Non",
            },
            {
                "question": "Quel est l'objectif principal de cette application ?",
                "choices": [
                    "Apprendre les plantes",
                    "Jouer aux échecs",
                    "Gérer des emails",
                    "Faire des mathématiques",
                ],
                "answer": "Apprendre les plantes",
            },
        ],
    }


def main() -> None:
    plant = choose_plant()
    wiki = fetch_wikipedia_summary(plant)
    prompt = build_prompt(plant, wiki)

    try:
        data = call_gemini(prompt)
    except Exception:
        data = fallback_result(plant)
    else:
        data.setdefault("date", date.today().isoformat())
        data.setdefault("plant_name", plant)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
