"""
Date-range filtering on DateTime columns without `__date` lookups.

On MySQL with USE_TZ=True, Django's `__date` / Trunc* functions call CONVERT_TZ(), which silently returns NULL
unless the server's time-zone tables are loaded. Converting the local calendar days into an aware datetime
range keeps filters correct on any MySQL installation (and lets MySQL use the index on the column).
"""
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone


def parse_day(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValidationError({"date": [f"Invalid date '{value}'. Use YYYY-MM-DD."]})


def day_range_q(field, date_from=None, date_to=None):
    q = Q()
    tz = timezone.get_current_timezone()
    start, end = parse_day(date_from), parse_day(date_to)
    if start:
        q &= Q(**{f"{field}__gte": timezone.make_aware(datetime.combine(start, time.min), tz)})
    if end:
        q &= Q(**{f"{field}__lt": timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)})
    return q
