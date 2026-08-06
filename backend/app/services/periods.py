"""Abrechnungsmonat ("Finanzmonat") – zentrale Zeitraum-Einteilung (4.9).

Wer sein Gehalt am 27. bekommt, lebt von diesem Geld bis zum nächsten 27. Der
Kalendermonat ist dafür das falsche Raster: bis zum Gehaltseingang sähe jeder
laufende Monat tiefrot aus, obwohl nichts aus dem Ruder läuft.

Mit `start_day = 27` läuft der Abrechnungsmonat vom 27. bis zum 26. und heißt
nach dem Monat, in dem er **endet**: 27.01.–26.02. ist der Februar. Damit ist
das Gehalt das erste Ereignis der Periode statt des letzten.

`start_day = 1` (Voreinstellung) ergibt exakt den Kalendermonat – bestehende
Installationen ändern sich dadurch nicht.

WICHTIG: Diese Einteilung betrifft ausschließlich Auswertungen. Buchungsdatum,
Betrag, Kontostand und der Saldo-Abgleich gegen die Bank rechnen immer mit dem
echten Datum, damit die Abstimmbarkeit mit dem Kontoauszug erhalten bleibt.
"""
import calendar
from datetime import date, timedelta

from sqlalchemy.orm import Session

from ..models import AppSetting

SETTING_KEY = "period"
DEFAULT_START_DAY = 1
# Über 28 hinaus gäbe es Monate ohne diesen Tag – die Grenze bliebe uneindeutig.
MAX_START_DAY = 28


def get_start_day(db: Session) -> int:
    setting = db.get(AppSetting, SETTING_KEY)
    if setting is None:
        return DEFAULT_START_DAY
    return normalize_start_day(setting.value.get("start_day", DEFAULT_START_DAY))


def normalize_start_day(value) -> int:
    try:
        day = int(value)
    except (TypeError, ValueError):
        return DEFAULT_START_DAY
    return max(1, min(MAX_START_DAY, day))


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1


def period_key(d: date, start_day: int = DEFAULT_START_DAY) -> str:
    """Abrechnungsmonat eines Datums als "YYYY-MM"."""
    if start_day <= 1:
        return f"{d.year:04d}-{d.month:02d}"
    year, month = (_shift_month(d.year, d.month, 1) if d.day >= start_day
                   else (d.year, d.month))
    return f"{year:04d}-{month:02d}"


def period_bounds(key: str, start_day: int = DEFAULT_START_DAY) -> tuple[date, date]:
    """Erster und letzter Tag eines Abrechnungsmonats (beide einschließlich)."""
    year, month = int(key[:4]), int(key[5:7])
    if start_day <= 1:
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    prev_year, prev_month = _shift_month(year, month, -1)
    start = date(prev_year, prev_month,
                 min(start_day, calendar.monthrange(prev_year, prev_month)[1]))
    end = date(year, month, min(start_day, calendar.monthrange(year, month)[1])) - timedelta(days=1)
    return start, end


def period_range(date_from: date, date_to: date, start_day: int = DEFAULT_START_DAY) -> list[str]:
    """Alle Abrechnungsmonate, die den Zeitraum berühren."""
    first, last = period_key(date_from, start_day), period_key(date_to, start_day)
    year, month = int(first[:4]), int(first[5:7])
    keys = []
    while f"{year:04d}-{month:02d}" <= last:
        keys.append(f"{year:04d}-{month:02d}")
        year, month = _shift_month(year, month, 1)
    return keys


def current_period(start_day: int = DEFAULT_START_DAY) -> str:
    return period_key(date.today(), start_day)


def period_year(key: str) -> int:
    """Jahr, unter dem ein Abrechnungsmonat im Jahresvergleich zählt."""
    return int(key[:4])


def effective_period(tx, start_day: int = DEFAULT_START_DAY) -> str:
    """Abrechnungsmonat einer Buchung – manuelle Zuordnung schlägt die Regel.

    Gespeichert wird nur die Abweichung: ändert sich später der Starttag,
    rechnen sich alle übrigen Buchungen automatisch neu ein.
    """
    return tx.financial_month or period_key(tx.booking_date, start_day)
