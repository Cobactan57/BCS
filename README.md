# BCS Cattle – Application d'acquisition

Prototype Streamlit pour constituer un jeu de données photographiques destiné à l'estimation automatique du Body Condition Score (BCS).

## Fonctions
- Acquisition photo + métadonnées
- Scoring indépendant par plusieurs évaluateurs
- Export CSV
- Calcul d'une synthèse par médiane/moyenne des scores

## Installation
1. Installer Python 3.10+
2. Ouvrir un terminal dans le dossier
3. Exécuter :

    pip install -r requirements.txt
    streamlit run app.py

## Smartphone
Sur le même réseau Wi-Fi que le PC :

    streamlit run app.py --server.address 0.0.0.0

Puis ouvrir l'adresse IP locale du PC suivie de :8501.

## Structure
- photos/ : photographies
- data/acquisitions.csv : métadonnées
- data/scores.csv : scores indépendants

Pour une vraie étude multicentrique, l'étape suivante sera de remplacer les CSV par une base SQL et d'ajouter authentification, contrôle qualité automatique et sauvegarde serveur.
