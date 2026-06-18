# Deploiement

Checklist courte avant mise en ligne.

## 1. Reparer ou recreer l'environnement Python

Le dossier `venv` actuel a ete copie depuis un autre compte Windows et pointe
vers `C:\Users\hp\...`. Sur la machine de deploiement, recreer un environnement
propre :

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si `py` n'existe pas, installer Python 3.12 puis relancer les commandes.

## 2. Variables d'environnement obligatoires

Copier `.env.example` vers `.env` ou definir les variables dans le service
d'hebergement.

Minimum requis en production :

```powershell
$env:DJANGO_DEBUG="False"
$env:DJANGO_SECRET_KEY="une-cle-longue-et-secrete"
$env:DJANGO_ALLOWED_HOSTS="votre-domaine.com,127.0.0.1,localhost"
$env:DJANGO_CSRF_TRUSTED_ORIGINS="https://votre-domaine.com"
```

Pour un test en reseau local sans HTTPS, garder :

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

SQLite est acceptable pour un test interne limite. Avant ouverture :

```powershell
Copy-Item db.sqlite3 backups\db_before_deploy.sqlite3
python manage.py migrate
python manage.py collectstatic --noinput
```

Servir en production :

- `staticfiles/` pour les fichiers statiques collectes ;
- `media/` pour les rapports, autorisations et documents envoyes.

Avec `DEBUG=False`, Django ne sert plus les fichiers `media/` lui-meme. Le
serveur web doit les exposer.

## 4. Verification

```powershell
python manage.py check --deploy
python manage.py showmigrations --plan
```

`check --deploy` peut encore signaler des points lies au HTTPS selon le mode de
deploiement choisi. Pour un domaine public, corriger tous les avertissements
avant ouverture.

## 5. Lancement

Test local :

```powershell
python manage.py runserver 127.0.0.1:8000
```

Reseau local :

```powershell
python manage.py runserver 0.0.0.0:8000
```

Pour un deploiement public, placer Django derriere un vrai serveur HTTP(S)
ou un service d'hebergement compatible WSGI/ASGI.

Sur Windows, apres `collectstatic`, un lancement WSGI simple est possible avec
Waitress :

```powershell
waitress-serve --listen=0.0.0.0:8000 config.wsgi:application
```

## 6. Deploiement Render

Le projet contient maintenant les fichiers necessaires :

- `render.yaml` pour creer le service web et la base PostgreSQL en mode gratuit ;
- `build.sh` pour installer, collecter les fichiers statiques et migrer ;
- `requirements.txt` avec `gunicorn`, `dj-database-url`, `psycopg` et `whitenoise`.

Etapes :

1. Envoyer le projet sur GitHub.
2. Dans Render, choisir **New +** puis **Blueprint**.
3. Connecter le depot GitHub.
4. Render lit `render.yaml` et propose de creer :
   - le service web gratuit `iup-soutenance` ;
   - la base PostgreSQL gratuite `iup-soutenance-db`.
5. Lancer la creation.

Apres le premier deploiement, verifier l'URL Render, par exemple :

```text
https://iup-soutenance.onrender.com/login/
```

En mode gratuit, les fichiers envoyes par les etudiants (`media/`) sont stockes
dans `/tmp/media`. C'est suffisant pour un test, mais ce stockage est temporaire
et peut etre vide apres un redeploiement ou redemarrage.

Pour une vraie mise en ligne, passer le service web en plan payant, ajouter un
disque persistant, puis utiliser :

```text
DJANGO_MEDIA_ROOT=/var/data/media
Mount path: /var/data
```
