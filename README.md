# IUP Soutenance

Plateforme Django de gestion des soutenances IUP : inscriptions, demandes PFE,
validation encadrant/administration, jurys, planning, evaluations et resultats.

## Deploiement Render

Le projet est prepare pour Render avec :

- `render.yaml` : service web, PostgreSQL et disque persistant ;
- `build.sh` : installation, `collectstatic`, migrations ;
- `gunicorn`, `dj-database-url`, `psycopg` et `whitenoise` dans `requirements.txt`.

Etapes rapides :

1. Creer le depot sur GitHub.
2. Dans Render : **New +** -> **Blueprint**.
3. Selectionner ce depot.
4. Laisser Render creer le service web et la base PostgreSQL.
5. Apres deploiement, ouvrir `/django-admin/` ou `/login/`.

Documentation detaillee : `docs/DEPLOIEMENT.md`.

## Donnees sensibles

Ne pas committer `.env`, `db.sqlite3`, `media/`, `backups/`, `venv/` ni les
fichiers reels d'import etudiants. Ils sont ignores par `.gitignore`.
