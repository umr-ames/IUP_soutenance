import re
import unicodedata
from collections import defaultdict

from django.db import migrations
from django.db.models import Count


def _normalize(name):
    """Clé de comparaison : sans accents, minuscules, espaces compactés."""
    text = unicodedata.normalize("NFKD", (name or "").strip())
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"\s+", " ", text)


def merge_variants(apps, schema_editor):
    """Fusionne les variantes d'orthographe d'un même encadrant dans la liste
    officielle (ex. « Yahya marega » et « Yahya Marega ») vers une seule
    orthographe canonique, pour que le décompte des professeurs soit exact."""
    StudentReference = apps.get_model("students", "StudentReference")

    counts = (
        StudentReference.objects.exclude(encadrant_name="")
        .values("encadrant_name")
        .annotate(n=Count("id"))
    )

    by_norm = defaultdict(list)
    for row in counts:
        by_norm[_normalize(row["encadrant_name"])].append(
            (row["encadrant_name"], row["n"])
        )

    for variants in by_norm.values():
        if len(variants) < 2:
            continue

        # Canonique = variante la plus utilisée ; à égalité, celle qui a une
        # majuscule (orthographe « propre »).
        canonical = sorted(
            variants,
            key=lambda v: (v[1], any(c.isupper() for c in v[0])),
        )[-1][0]

        for name, _count in variants:
            if name != canonical:
                StudentReference.objects.filter(encadrant_name=name).update(
                    encadrant_name=canonical
                )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("students", "0007_entreprise_field"),
    ]

    operations = [
        migrations.RunPython(merge_variants, noop),
    ]
