from calendar import monthrange
from datetime import date, timedelta

from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from django.utils import timezone

from class_sessions.datetime_bounds import aware_day_range
from class_sessions.models import CheckIn, Session, SessionAttendance
from people.models import AuditLog, Staff, Student, Subject, Teacher, User
from people.serializers import AuditLogSerializer
from timetable.models import Class, ClassStudent, TimetableSlot

STATS_CACHE_KEY = 'stats_overview_v2'
STATS_CACHE_TTL = 300
TREND_WINDOW_DAYS = 30
RECENT_ACTIVITY_LIMIT = 8
SERIES_MONTHS = 12

# Per-session creates from timetable generate (and old signal noise) are not
# overview material — keep the one "Generated N sessions" summary instead.
_SESSION_CREATE_NOISE = (
    Q(model_name__in=['Session', 'AdHocSession'], action='create')
    & ~Q(summary__istartswith='Generated')
)


def _trend(current, previous):
    delta = current - previous
    if delta > 0:
        direction = 'up'
    elif delta < 0:
        direction = 'down'
    else:
        direction = 'stable'
    return {
        'current': current,
        'previous': previous,
        'delta': delta,
        'direction': direction,
    }


def _table_counts():
    models = {
        'users': User,
        'students': Student,
        'teachers': Teacher,
        'staff': Staff,
        'subjects': Subject,
        'classes': Class,
        'class_students': ClassStudent,
        'timetable_slots': TimetableSlot,
        'sessions': Session,
        'session_attendances': SessionAttendance,
        'check_ins': CheckIn,
    }
    select_parts = []
    keys = []
    for key, model in models.items():
        table = connection.ops.quote_name(model._meta.db_table)
        select_parts.append(f'(SELECT COUNT(*) FROM {table})')
        keys.append(key)
    with connection.cursor() as cursor:
        cursor.execute('SELECT ' + ', '.join(select_parts))
        row = cursor.fetchone()
    return {key: int(row[i] or 0) for i, key in enumerate(keys)}


def _build_trends(counts):
    today = timezone.localdate()
    cutoff = today - timedelta(days=TREND_WINDOW_DAYS)
    prev_start = cutoff - timedelta(days=TREND_WINDOW_DAYS)

    students_prev = Student.objects.filter(enrollment_date__lte=cutoff).count()
    teachers_prev = Teacher.objects.filter(join_date__lte=cutoff).count()

    window_start, _ = aware_day_range(cutoff, cutoff)
    prev_window_start, _ = aware_day_range(prev_start, prev_start)

    sessions_current = Session.objects.filter(start_time__gte=window_start).count()
    sessions_previous = Session.objects.filter(
        start_time__gte=prev_window_start,
        start_time__lt=window_start,
    ).count()

    checkins_current = CheckIn.objects.filter(date__gte=cutoff).count()
    checkins_previous = CheckIn.objects.filter(
        date__gte=prev_start,
        date__lt=cutoff,
    ).count()

    class_count = counts['classes']
    return {
        'students': _trend(counts['students'], students_prev),
        'teachers': _trend(counts['teachers'], teachers_prev),
        'classes': _trend(class_count, class_count),
        'sessions': _trend(sessions_current, sessions_previous),
        'check_ins': _trend(checkins_current, checkins_previous),
    }


def student_enrollment_series(months=SERIES_MONTHS):
    """Cumulative enrolled students at each month-end for the last `months` months."""
    today = timezone.localdate()
    month_ends = []
    year, month = today.year, today.month
    for _ in range(months):
        last_day = monthrange(year, month)[1]
        month_ends.append(date(year, month, last_day))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    month_ends.reverse()

    by_month = {}
    for row in (
        Student.objects
        .annotate(month=TruncMonth('enrollment_date'))
        .values('month')
        .annotate(n=Count('id'))
    ):
        stamped = row['month']
        if stamped is None:
            continue
        if hasattr(stamped, 'date'):
            stamped = stamped.date()
        by_month[date(stamped.year, stamped.month, 1)] = row['n']

    first_start = date(month_ends[0].year, month_ends[0].month, 1)
    running = Student.objects.filter(enrollment_date__lt=first_start).count()
    series = []
    for month_end in month_ends:
        month_start = date(month_end.year, month_end.month, 1)
        added = by_month.get(month_start, 0)
        running += added
        series.append({
            'date': month_end.isoformat(),
            'count': running,
            'new': added,
        })
    return _trim_leading_empty_months(series)


def _trim_leading_empty_months(series):
    """Drop the empty prefix so a recent import is not a 12-month flat line."""
    first_idx = next((i for i, point in enumerate(series) if point['count'] > 0), None)
    if first_idx is None:
        return series[-3:] if len(series) > 3 else series
    start = max(0, first_idx - 1)
    return series[start:]


def _recent_activity():
    logs = (
        AuditLog.objects
        .exclude(_SESSION_CREATE_NOISE)
        .select_related('user')
        .order_by('-timestamp')[:RECENT_ACTIVITY_LIMIT]
    )
    return AuditLogSerializer(logs, many=True).data


def build_overview_stats():
    payload = cache.get(STATS_CACHE_KEY)
    if payload is None or 'trends' not in payload or 'student_series' not in payload:
        counts = _table_counts()
        payload = {
            **counts,
            'trends': _build_trends(counts),
            'student_series': student_enrollment_series(),
        }
        cache.set(STATS_CACHE_KEY, payload, STATS_CACHE_TTL)

    data = dict(payload)
    data['recent_activity'] = _recent_activity()
    return data
