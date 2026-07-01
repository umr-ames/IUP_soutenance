"""Créneaux de disponibilité / soutenance : deux créneaux par jour (matin et
après-midi), avec une exception le vendredi.

- Matin      : 9h00 – 14h00  (vendredi : 9h00 – 12h00)
- Après-midi : 15h00 – 19h00 (vendredi : 16h00 – 19h00)

Une disponibilité de matin/après-midi couvre TOUT le créneau (pas de saisie
horaire fine).
"""

import datetime

MORNING = "morning"
AFTERNOON = "afternoon"

FRIDAY = 4  # date.weekday()


def morning_slot(date):
    if date.weekday() == FRIDAY:
        return datetime.time(9, 0), datetime.time(12, 0)
    return datetime.time(9, 0), datetime.time(14, 0)


def afternoon_slot(date):
    if date.weekday() == FRIDAY:
        return datetime.time(16, 0), datetime.time(19, 0)
    return datetime.time(15, 0), datetime.time(19, 0)


def slot_bounds(date, slot):
    return morning_slot(date) if slot == MORNING else afternoon_slot(date)


def slots_for(date):
    """Liste ordonnée [(start, end), ...] des créneaux du jour."""
    return [morning_slot(date), afternoon_slot(date)]


def _overlaps(a_start, a_end, b_start, b_end):
    return a_start < b_end and b_start < a_end


def slots_touched(date, start_time, end_time):
    """Renvoie l'ensemble des créneaux ({MORNING, AFTERNOON}) qu'un intervalle
    horaire [start_time, end_time] recoupe ce jour-là."""
    touched = set()
    ms, me = morning_slot(date)
    as_, ae = afternoon_slot(date)
    if _overlaps(start_time, end_time, ms, me):
        touched.add(MORNING)
    if _overlaps(start_time, end_time, as_, ae):
        touched.add(AFTERNOON)
    return touched
