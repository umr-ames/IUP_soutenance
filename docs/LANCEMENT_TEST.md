# Lancement pour test utilisateur

## 1. Installer les dépendances

```
pip install -r requirements.txt
```

## 2. Lancer les migrations

```
python manage.py migrate
```

## 3. Créer un superuser/admin (optionnel)

La commande `create_demo_soutenance_data` crée déjà un admin de démo
(`admin.demo@iup.local` / `Demo@2026`). Pour un admin séparé avec accès
`/django-admin/` complet :

```
python manage.py createsuperuser
```

## 4. (Optionnel) Charger les données de démo

```
python manage.py create_demo_soutenance_data
```

Voir `docs/SCENARIO_TEST_MANUEL.md` pour le déroulé complet.

## 5. Lancer le serveur

En local uniquement :
```
python manage.py runserver
```

Pour le rendre accessible depuis d'autres machines du même réseau (étudiants
sur leur propre PC/téléphone, même Wi-Fi) :
```
python manage.py runserver 0.0.0.0:8000
```
Il faudra alors ajouter l'IP locale de la machine à `ALLOWED_HOSTS` dans
`config/settings.py` (voir section précautions ci-dessous).

## 6. URLs à utiliser

- Connexion : `/login/`
- Inscription étudiant : `/register/`
- Inscription professeur : `/prof/`
- Tableau de bord (redirige selon le rôle) : `/`
- Admin Django (technique) : `/django-admin/`

## 7. Comptes démo disponibles

Voir `docs/SCENARIO_TEST_MANUEL.md`. Mot de passe commun : `Demo@2026`.

| Rôle | Email |
|---|---|
| Admin | admin.demo@iup.local |
| Professeur 1, 2, 3 | prof1.demo@iup.local, prof2.demo@iup.local, prof3.demo@iup.local |
| Étudiant 1, 2, 3 | etudiant1.demo@iup.local, etudiant2.demo@iup.local, etudiant3.demo@iup.local |

## 8. Précautions avant de donner le lien aux étudiants

- `DEBUG = True` actuellement : pratique pour déboguer pendant le test, mais
  affiche des informations techniques en cas d'erreur. Acceptable pour un
  test interne court avec un public restreint et de confiance ; à repasser
  à `False` avant toute mise en ligne publique réelle.
- `ALLOWED_HOSTS` ne contient que `127.0.0.1` et `localhost`. Si les
  étudiants doivent accéder depuis leur propre appareil sur le même réseau,
  ajouter l'adresse IP (ou le nom de domaine) utilisée dans
  `config/settings.py` avant de lancer le serveur, sinon Django renverra une
  erreur 400 "DisallowedHost".
- La base est SQLite (`db.sqlite3`) : suffisante pour un test avec un petit
  groupe, mais ne supporte pas une forte charge simultanée. Faire une
  sauvegarde du fichier `db.sqlite3` avant le test (copie simple) pour
  pouvoir revenir en arrière si besoin.
- Les dossiers `media/` et `static/` existent déjà et sont utilisés pour les
  fichiers envoyés (rapports, autorisations) et les fichiers statiques.
  Vérifier qu'il y a de la place disque suffisante si plusieurs étudiants
  envoient des PDF.
- Aucun envoi d'email n'est configuré (`EMAIL_BACKEND` non défini) : ce
  n'est pas bloquant, l'application n'envoie pas d'email actuellement.
- Ne pas exécuter `reset_demo_data` pendant que des étudiants/professeurs
  utilisent la plateforme : cela supprime les profils étudiant/professeur.
