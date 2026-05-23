# Apothicaire du jour

Petit site gratuit pour apprendre une plante par jour avec quiz.

## À faire après avoir créé le dépôt GitHub
1. Copier tous ces fichiers dans le dépôt.
2. Aller dans **Settings > Secrets and variables > Actions**.
3. Créer un secret nommé **GEMINI_API_KEY**.
4. Aller dans **Settings > Pages**.
5. Mettre **Deploy from a branch**.
6. Choisir **Branch: main** et **Folder: /docs**.
7. Aller dans l'onglet **Actions** et lancer le workflow **Daily plant update** une première fois.

## Ce que fait le projet
- `docs/index.html` affiche la plante du jour.
- `docs/today.json` contient le contenu du jour.
- `generate.py` appelle Gemini avec la recherche Google.
- `.github/workflows/daily.yml` exécute le script tous les jours.

## Important
- Le site peut être gratuit.
- L'API Gemini a une offre gratuite et Google AI Studio est sans frais dans les régions disponibles.
- GitHub Pages peut publier depuis une branche ou via GitHub Actions.
