# IUP Soutenance

Plateforme Django de gestion des soutenances IUP : inscriptions, demandes PFE,
validation encadrant/administration, jurys, planning, évaluations et résultats.

## Déploiement Render

Le projet est préparé pour Render avec :

- `render.yaml` : service web et PostgreSQL ;
- `build.sh` : installation, `collectstatic`, migrations ;
- `gunicorn`, `dj-database-url`, `psycopg` et `whitenoise` dans `requirements.txt`.

Étapes rapides :

1. Créer le dépôt sur GitHub.
2. Dans Render : **New +** -> **Blueprint**.
3. Sélectionner ce dépôt.
4. Laisser Render créer le service web et la base PostgreSQL.
5. Après déploiement, ouvrir `/django-admin/` ou `/login/`.

URL Render attendue :

```text
https://isgi-soutenances.onrender.com
```

Documentation détaillée : `docs/DEPLOIEMENT.md`.

## Données sensibles

Ne pas committer `.env`, `db.sqlite3`, `media/`, `backups/`, `venv/` ni les
fichiers réels d'import étudiants. Ils sont ignorés par `.gitignore`.

## Mode production Render

Le Blueprint utilise une configuration stable :

- web service `starter` ;
- PostgreSQL `basic-256mb` ;
- disque persistant 1 GB pour les fichiers uploadés dans `media/`.
