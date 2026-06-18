# Scénario de test manuel — workflow complet

Checklist à suivre dans l'ordre, avec des comptes réels ou les comptes démo
(`docs/LANCEMENT_TEST.md`).

- [ ] **Admin** importe les étudiants (`docs/IMPORT_ETUDIANTS.md`).
- [ ] **Étudiant** crée son compte sur `/register/` en saisissant son
      matricule (le nom doit se pré-remplir si le matricule est connu).
- [ ] **Étudiant** se connecte et envoie sa demande de soutenance
      (autorisation + rapport de stage).
- [ ] **Professeur encadrant** se connecte, ouvre "Demandes de soutenance"
      et accepte la demande de l'étudiant.
- [ ] **Admin** ouvre "Demandes de soutenance" et accepte à son tour la
      demande (statut passe à "Acceptée").
- [ ] **Professeurs** (les 3 membres potentiels du futur jury) ajoutent des
      disponibilités futures dans "Disponibilités".
- [ ] **Admin** va dans "Jurys" → "Générer automatiquement".
- [ ] **Admin** vérifie que le jury créé est marqué "Non publié" et reste
      invisible côté étudiant/professeur.
- [ ] **Admin** ouvre le détail du jury, vérifie les 3 membres et le
      président désigné, puis clique "Publier".
- [ ] **Étudiant** se reconnecte et vérifie qu'il voit désormais son jury,
      sa date et son horaire de passage.
- [ ] **Président de soutenance** (le professeur désigné, pas forcément
      l'encadrant) se connecte, va dans "Mes jurys" et clique
      "Démarrer la soutenance" pour cet étudiant.
- [ ] **Chaque professeur du jury** (les 3) se connecte, ouvre
      "Évaluations", saisit ses 3 notes (rapport, présentation, questions)
      et clique "Envoyer définitivement".
- [ ] **Admin** va dans "Résultats", vérifie que la moyenne s'est calculée
      automatiquement, puis clique "Publier" pour cet étudiant.
- [ ] **Étudiant** se reconnecte et vérifie que son résultat final (moyenne
      sur 20) est visible sur son tableau de bord.

## Points d'attention pendant le test

- Si un professeur essaie de noter avant que le président ait cliqué
  "Démarrer la soutenance" : la saisie doit être refusée avec un message
  clair.
- Si un professeur qui n'est pas président essaie de démarrer la
  soutenance : l'action doit être refusée.
- Un jury non publié ne doit jamais apparaître côté étudiant ou professeur,
  seulement côté admin.
