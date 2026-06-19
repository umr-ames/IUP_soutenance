from datetime import datetime, timedelta, date

from django.db import migrations

NEW_DURATION = 20


def set_durations_to_20(apps, schema_editor):
    """Recalcule les créneaux déjà planifiés à 20 minutes (au lieu de 30) :
    on garde l'heure de début et on recalcule l'heure de fin = début + 20 min."""
    DefenseSchedule = apps.get_model("soutenances", "DefenseSchedule")

    for schedule in DefenseSchedule.objects.all():
        if schedule.start_time is None:
            continue

        start_dt = datetime.combine(date(2000, 1, 1), schedule.start_time)
        schedule.end_time = (start_dt + timedelta(minutes=NEW_DURATION)).time()
        schedule.duration_minutes = NEW_DURATION
        schedule.save(update_fields=["end_time", "duration_minutes"])


def noop(apps, schema_editor):
    # Pas de retour en arrière automatique sur les durées.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("soutenances", "0013_alter_defenseschedule_duration_minutes"),
    ]

    operations = [
        migrations.RunPython(set_durations_to_20, noop),
    ]
