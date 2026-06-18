# Déploiement

Checklist courte avant mise en ligne.

## 1. Réparer ou recréer l'environnement Python

Le dossier `venv` actuel a été copié depuis un autre compte Windows et pointe
vers `C:\Users\hp\...`. Sur la machine de déploiement, recréer un environnement
propre :

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si `py` n'existe pas, installer Python 3.12 puis relancer les commandes.

## 2. Variables d'environnement obligatoires

Copier `.env.example` vers `.env` ou définir les variables dans le service
d'hébergement.

Minimum requis en production :

```powershell
$env:DJANGO_DEBUG="False"
$env:DJANGO_SECRET_KEY="une-cle-longue-et-secrete"
$env:DJANGO_ALLOWED_HOSTS="votre-domaine.com,127.0.0.1,localhost"
$env:DJANGO_CSRF_TRUSTED_ORIGINS="https://votre-domaine.com"
```

Pour un test en réseau local sans HTTPS, garder :

```powershell
$env:DJANGO_SECURE_SSL_REDIRECT="False"
$env:DJANGO_SESSION_COOKIE_SECURE="False"
$env:DJANGO_CSRF_COOKIE_SECURE="False"
```

Pour un vrai domaine en HTTPS, utiliser `True` pour ces trois variables.
Ajouter aussi HSTS seulement quand HTTPS est stable :

```powershell
$env:DJANGO_SECURE_HSTS_SECONDS="31536000"
$env:DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS="True"
$env:DJANGO_SECURE_HSTS_PRELOAD="False"
```

## 3. Base et fichiers

SQLite est acceptable pour un test interne limité. Avant ouverture :

```powershell
Copy-Item db.sqlite3 backups\db_before_deploy.sqlite3
python manage.py migrate
python manage.py collectstatic --noinput
```

Servir en production :

- `staticfiles/` pour les fichiers statiques collectés ;
- `media/` pour les rapports, autorisations et documents envoyés.

Avec `DEBUG=False`, Django ne sert plus les fichiers `media/` lui-même. Le
serveur web doit les exposer.

## 4. Vérification

```powershell
python manage.py check --deploy
python manage.py showmigrations --plan
```

`check --deploy` peut encore signaler des points liés au HTTPS selon le mode de
déploiement choisi. Pour un domaine public, corriger tous les avertissements
avant ouverture.

## 5. Lancement

Test local :

```powershell
python manage.py runserver 127.0.0.1:8000
```

Réseau local :

```powershell
python manage.py runserver 0.0.0.0:8000
```

Pour un déploiement public, placer Django derrière un vrai serveur HTTP(S)
ou un service d'hébergement compatible WSGI/ASGI.

Sur Windows, après `collectstatic`, un lancement WSGI simple est possible avec
Waitress :

```powershell
waitress-serve --listen=0.0.0.0:8000 config.wsgi:application
```

## 6. Déploiement Render

Le projet contient maintenant les fichiers nécessaires :

- `render.yaml` pour créer le service web, la base PostgreSQL et le disque media ;
- `build.sh` pour installer, collecter les fichiers statiques et migrer ;
- `requirements.txt` avec `gunicorn`, `dj-database-url`, `psycopg` et `whitenoise`.

Étapes :

1. Envoyer le projet sur GitHub.
2. Dans Render, choisir **New +** puis **Blueprint**.
3. Connecter le dépôt GitHub.
4. Render lit `render.yaml` et propose de créer :
   - le service web `isgi-soutenances` ;
   - la base PostgreSQL `iup-soutenance-db` ;
   - le disque persistant `media`.
5. Lancer la création.

Après le premier déploiement, vérifier l'URL Render, par exemple :

```text
https://isgi-soutenances.onrender.com/login/
```

Les fichiers envoyés par les étudiants (`media/`) sont conservés sur un disque
persistant attaché au service web :

```text
DJANGO_MEDIA_ROOT=/var/data/media
Mount path: /var/data
```
