# BCS Cattle Acquisition — v4

Cette version remplace le stockage local éphémère de Streamlit par un stockage permanent :

- **Supabase PostgreSQL** pour les acquisitions et les scores ;
- **Supabase Storage** pour les photographies ;
- **Streamlit Community Cloud** uniquement pour exécuter l'interface.

## 1. Préparer Supabase

### 1.1 Tables
Dans Supabase : **SQL Editor > New query**. Copier le contenu de `setup_supabase.sql`, puis **Run**.

### 1.2 Bucket photos
Dans Supabase : **Storage > New bucket**.

Nom exact :

`bcs-photos`

Laisser le bucket **Private**.

## 2. Configurer les secrets Streamlit

Dans Streamlit Community Cloud : **App > Settings > Secrets** :

```toml
SUPABASE_URL = "https://xxxxxxxxxxxx.supabase.co"
SUPABASE_KEY = "sb_secret_xxxxxxxxxxxxxxxxx"
```

Utiliser une **clé secrète serveur** (`sb_secret_...`, ou l'ancienne `service_role`).
Ne jamais placer cette clé dans GitHub.

## 3. GitHub

Remplacer `app.py` et `requirements.txt` de la v3 par les fichiers de cette v4. Ajouter également `setup_supabase.sql` et ce README.

La structure minimale du dépôt :

```
app.py
requirements.txt
setup_supabase.sql
README.md
```

Streamlit redéploiera automatiquement après le commit sur `main`.

## 4. Persistance

Une nouvelle acquisition effectue deux écritures :

1. photo -> bucket privé `bcs-photos` ;
2. métadonnées -> table `acquisitions`.

Le scoring indépendant est enregistré dans `scores`.

Les photos ne dépendent plus du disque local Streamlit et restent disponibles après veille, redémarrage ou redéploiement de l'application.

## 5. Suppression

Une acquisition rejetée reste conservée pour la traçabilité. La suppression définitive :

- supprime la ligne `acquisitions` ;
- supprime automatiquement ses scores grâce à `ON DELETE CASCADE` ;
- supprime la photo du bucket Supabase.

## 6. Migration des anciennes données

La v4 ne lit plus les anciens CSV comme source principale. Conserver une copie des anciens dossiers `data/` et `photos/` tant que les anciennes acquisitions n'ont pas été migrées.

Un script de migration peut être utilisé séparément si nécessaire.
