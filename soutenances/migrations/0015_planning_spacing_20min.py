from collections import defaultdict
from datetime import datetime, timedelta, date

from django.db import migrations

STEP = 20  # minutes


def respace_to_20min(apps, schema_editor):
    """Ré-espace les créneaux déjà planifiés en pas de 20 minutes.

    Pour chaque jury, on conserve l'heure du premier passage puis on enchaîne
    les passages toutes les 20 minutes (passage = 20 min). On ne fait que
    comprimer la plage d'un jury : aucun nouveau conflit de professeur n'est
    introduit par rapport au planning existant (déjà sans conflit)."""
    DefenseSchedule = apps.get_model("soutenances", "DefenseSchedule")

    groups = defaultdict(list)
    for schedule in DefenseSchedule.objects.all():
        if schedule.start_time is None:
            continue
        groups[schedule.jury_student.jury_id].append(schedule)

    anchor = date(2000, 1, 1)

    for schedules in groups.values():
        schedules.sort(key=lambda s: (s.start_time, s.pk))
        base = datetime.combine(anchor, schedules[0].start_time)

        for index, schedule in enumerate(schedules):
            start_dt = base + timedelta(minutes=index * STEP)
            end_dt = start_dt + timedelta(minutes=STEP)
            schedule.start_time = start_dt.time()
            schedule.end_time = end_dt.time()
            schedule.duration_minutes = STEP
            schedule.save(
                update_fields=["start_time", "end_time", "duration_minutes"]
            )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("soutenances", "0014_defense_duration_20min"),
    ]

    operations = [
        migrations.RunPython(respace_to_20min, noop),
    ]
