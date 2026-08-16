"""Timezone-aware day/month windows so `start_time` filters can use indexes."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta

from django.utils import timezone


def parse_iso_date(value) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def aware_day_range(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Inclusive local dates as a half-open [start, end) datetime window."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    end = timezone.make_aware(datetime.combine(date_to + timedelta(days=1), time.min), tz)
    return start, end


def month_day_range(year: int, month: int) -> tuple[date, date]:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)
