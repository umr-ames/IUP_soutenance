from collections import defaultdict
from datetime import datetime, timedelta, date

from django.db import migrations

STEP = 20  # minutes


def make_contiguous(apps, schema_editor):
    """Rend les passages d'une même journée parfaitement contigus (pas de
    20 min, sans aucun espacement entre les jurys).

    Pour chaque date de soutenance : on trie les passages par heure de début,
    puis on les enchaîne à partir du premier horaire, toutes les 20 minutes.
    Tout devient séquentiel : aucun professeur ne peut être doublement
    réservé (aucun chevauchement)."""
    DefenseSchedule = apps.get_model("soutenances", "DefenseSchedule")

    by_date = defaultdict(list)
    for schedule in DefenseSchedule.objects.all():
        if schedule.start_time is None:
            continue
        defense_date = schedule.jury_student.jury.defense_date
        by_date[defense_date].append(schedule)

    anchor = date(2000, 1, 1)

    for schedules in by_date.values():
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
        ("soutenances", "0015_planning_spacing_20min"),
    ]

    operations = [
        migrations.RunPython(make_contiguous, noop),
    ]
