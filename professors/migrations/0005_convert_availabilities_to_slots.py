from django.db import migrations


def to_slots(apps, schema_editor):
    """Convertit les disponibilités horaires existantes en créneaux matin /
    après-midi complets (toute dispo touchant un créneau => créneau entier)."""
    from professors import slots as slot_utils

    ProfessorAvailability = apps.get_model("professors", "ProfessorAvailability")

    # Regrouper par (professor, date).
    by_key = {}
    for av in ProfessorAvailability.objects.all():
        by_key.setdefault((av.professor_id, av.date), []).append(av)

    for (professor_id, date), records in by_key.items():
        touched = set()
        for av in records:
            touched |= slot_utils.slots_touched(date, av.start_time, av.end_time)

        # Supprimer les anciens enregistrements de ce jour.
        ProfessorAvailability.objects.filter(
            professor_id=professor_id, date=date
        ).delete()

        # Recréer un enregistrement par créneau touché (aligné sur le créneau).
        for slot in touched:
            start_time, end_time = slot_utils.slot_bounds(date, slot)
            ProfessorAvailability.objects.create(
                professor_id=professor_id,
                date=date,
                start_time=start_time,
                end_time=end_time,
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("professors", "0004_alter_professoravailability_id_and_more"),
    ]

    operations = [
        migrations.RunPython(to_slots, noop),
    ]
