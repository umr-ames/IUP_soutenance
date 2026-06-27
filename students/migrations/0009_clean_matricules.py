from django.db import migrations


def clean_matricules(apps, schema_editor):
    """Nettoie les matricules déjà stockés : retire espaces (dont insécables),
    caractères invisibles et uniformise la casse. Corrige les inscriptions
    bloquées par un caractère caché hérité d'un ancien import (ex. IUP21172)."""
    from students.models import normalize_matricule

    StudentReference = apps.get_model("students", "StudentReference")
    StudentProfile = apps.get_model("students", "StudentProfile")

    for model in (StudentReference, StudentProfile):
        # Index des matricules déjà présents (forme normalisée) pour éviter les
        # collisions d'unicité lors de la mise à jour.
        existing_normalized = set()
        for obj in model.objects.all():
            normalized = normalize_matricule(obj.matricule)
            existing_normalized.add(normalized)

        for obj in model.objects.all():
            normalized = normalize_matricule(obj.matricule)
            if normalized and normalized != obj.matricule:
                # Évite une collision si un autre enregistrement porte déjà la
                # forme normalisée (cas improbable : on laisse alors tel quel).
                clash = model.objects.filter(matricule__iexact=normalized).exclude(pk=obj.pk).exists()
                if clash:
                    continue
                obj.matricule = normalized
                obj.save(update_fields=["matricule"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0008_merge_encadrant_name_variants"),
    ]

    operations = [
        migrations.RunPython(clean_matricules, noop),
    ]
