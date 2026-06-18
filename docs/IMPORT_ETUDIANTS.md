# Import des étudiants de référence (StudentReference)

Ce mécanisme permet à un étudiant qui s'inscrit de voir son nom se remplir
automatiquement quand il saisit son matricule. Il ne crée pas de compte :
c'est juste une liste de référence officielle.

## Format CSV attendu

- Séparateur : virgule `,`
- Encodage recommandé : UTF-8 (avec ou sans BOM)
- Colonnes acceptées (insensibles à la casse, au choix) :
  - `matricule` ou `Matricule`
  - `full_name` ou `Nom complet`
  - `filiere` ou `Filière`
  - `encadrant_name` ou `Encadrant`

## Exemple

Fichier `data/student_references_template.csv` déjà présent dans le projet :

```
matricule,full_name,filiere,encadrant_name
IUP23441,Mohamed Ould Ahmed,DS,Sidi Mohamed Lemine
IUP23442,Aïcha Mint Soueilim,FINTECH,Fatimetou Bint Ahmed
IUP23443,Cheikh Ould Brahim,MAN,Mohamed Lemine Ould Cheikh
```

## Commande d'import

```
python manage.py import_student_references data/student_references_template.csv
```

Pour importer la vraie liste, remplacer le chemin par le fichier réel,
par exemple :
```
python manage.py import_student_references data/liste_officielle_2026.csv
```

La commande est relançable sans créer de doublons : un matricule déjà
présent est mis à jour, pas dupliqué. Elle affiche un résumé : créés, mis à
jour, ignorés, erreurs.

## Vérifier que l'autocomplétion fonctionne

1. Importer le CSV (commande ci-dessus).
2. Ouvrir `/register/` (inscription étudiant).
3. Saisir un matricule présent dans le CSV (ex : `IUP23441`) puis sortir du
   champ (clic ailleurs).
4. Le champ "Nom complet" doit se remplir automatiquement.

Vérification technique directe (sans navigateur) :
```
python manage.py shell -c "from students.models import StudentReference; print(StudentReference.objects.filter(matricule='IUP23441').first())"
```

## Si un matricule n'apparaît pas

- Vérifier la casse et les espaces : la recherche se fait sur le matricule
  exact (insensible à la casse, mais pas aux espaces internes).
- Vérifier que le CSV a bien été importé sans erreur (regarder le résumé
  affiché par la commande : "X ignoré(s)", "X erreur(s)").
- Vérifier que la ligne dans le CSV avait bien une colonne matricule non
  vide (les lignes sans matricule sont ignorées automatiquement).
- Réimporter le fichier corrigé : pas de risque de doublon.
- En dernier recours, vérifier en base :
  ```
  python manage.py shell -c "from students.models import StudentReference; print(StudentReference.objects.filter(matricule__icontains='PARTIE_DU_MATRICULE'))"
  ```
