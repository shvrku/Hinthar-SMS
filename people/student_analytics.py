"""Student attendance analytics.

`range=all` remains enrollment→today (intentional). Aggregation is pushed to the
DB where possible so long histories stay correct without Python row loops.
"""
from datetime import timedelta

from django.db.models import Count, F
from django.db.models.functions import TruncDate
from django.utils import timezone

from class_sessions.models import CheckIn, SessionAttendance, AdHocSessionAttendance


VALID_RANGES = frozenset({'week', 'month', 'all'})
_STATUS_KEYS = ('present', 'late', 'absent', 'excused')


def resolve_student_analytics_range(range_key: str, enrollment_date):
    """Return (date_from, date_to) for preset analytics windows."""
    today = timezone.localdate()
    if range_key == 'week':
        date_from = today - timedelta(days=today.weekday())
    elif range_key == 'month':
        date_from = today.replace(day=1)
    elif range_key == 'all':
        date_from = enrollment_date
    else:
        raise ValueError(f'Invalid range: {range_key}')
    if date_from < enrollment_date:
        date_from = enrollment_date
    return date_from, today


def _iter_dates(date_from, date_to):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def _empty_status():
    return {k: 0 for k in _STATUS_KEYS}


def _bump(bucket: dict, status: str, n: int = 1):
    key = status if status in bucket else 'absent'
    bucket[key] += n


def _class_label(education_level, cohort_identifier, cohort_sub_category):
    if cohort_sub_category:
        return f"{education_level} {cohort_identifier}{cohort_sub_category}"
    return f"{education_level} {cohort_identifier}"


def build_student_attendance_summary(student, range_key: str):
    if range_key not in VALID_RANGES:
        raise ValueError(f'range must be one of: {", ".join(sorted(VALID_RANGES))}')

    date_from, date_to = resolve_student_analytics_range(range_key, student.enrollment_date)

    check_in_dates = set(
        CheckIn.objects.filter(
            student=student,
            date__gte=date_from,
            date__lte=date_to,
        ).values_list('date', flat=True)
    )

    # Keep full since-enrollment daily series (range=all semantics unchanged).
    calendar_days = list(_iter_dates(date_from, date_to))
    campus_daily = [
        {'date': d.isoformat(), 'checked_in': d in check_in_dates}
        for d in calendar_days
    ]
    days_in_range = len(calendar_days)
    days_checked_in = len(check_in_dates)

    status_counts = _empty_status()
    trend_map = {}
    by_class_map = {}
    by_subject_map = {}

    session_base = SessionAttendance.objects.filter(
        student=student,
        session__start_time__date__gte=date_from,
        session__start_time__date__lte=date_to,
    )

    for row in session_base.values('status').annotate(c=Count('id')):
        _bump(status_counts, row['status'], row['c'])

    for row in (
        session_base
        .values(
            'status',
            class_id=F('session__class_obj_id'),
            education_level=F('session__class_obj__education_level'),
            cohort_identifier=F('session__class_obj__cohort_identifier'),
            cohort_sub_category=F('session__class_obj__cohort_sub_category'),
        )
        .annotate(c=Count('id'))
    ):
        class_key = row['class_id']
        entry = by_class_map.setdefault(
            class_key,
            {
                'class_id': class_key,
                'class_label': _class_label(
                    row['education_level'],
                    row['cohort_identifier'],
                    row['cohort_sub_category'],
                ),
                **_empty_status(),
                'total': 0,
            },
        )
        _bump(entry, row['status'], row['c'])
        entry['total'] += row['c']

    for row in (
        session_base
        .values(
            'status',
            subject_id=F('session__timetable_slot__subject_id'),
            subject_name=F('session__timetable_slot__subject__name'),
        )
        .annotate(c=Count('id'))
    ):
        subject_key = row['subject_id'] or 0
        entry = by_subject_map.setdefault(
            subject_key,
            {
                'subject_id': row['subject_id'],
                'subject_label': row['subject_name'] or 'Unknown',
                **_empty_status(),
                'total': 0,
            },
        )
        _bump(entry, row['status'], row['c'])
        entry['total'] += row['c']

    for row in (
        session_base
        .annotate(session_date=TruncDate('session__start_time'))
        .values('session_date', 'status')
        .annotate(c=Count('id'))
    ):
        if row['session_date'] is None:
            continue
        day_key = row['session_date'].isoformat()
        bucket = trend_map.setdefault(day_key, _empty_status())
        _bump(bucket, row['status'], row['c'])

    adhoc_base = AdHocSessionAttendance.objects.filter(
        student=student,
        ad_hoc_session__date__gte=date_from,
        ad_hoc_session__date__lte=date_to,
    )

    for row in adhoc_base.values('status').annotate(c=Count('id')):
        _bump(status_counts, row['status'], row['c'])

    for row in (
        adhoc_base
        .values(
            'status',
            subject_id=F('ad_hoc_session__subject_id'),
            subject_name=F('ad_hoc_session__subject__name'),
        )
        .annotate(c=Count('id'))
    ):
        subject_key = row['subject_id'] or 0
        entry = by_subject_map.setdefault(
            subject_key,
            {
                'subject_id': row['subject_id'],
                'subject_label': row['subject_name'] or 'Ad-hoc',
                **_empty_status(),
                'total': 0,
            },
        )
        _bump(entry, row['status'], row['c'])
        entry['total'] += row['c']

    for row in (
        adhoc_base
        .values('status', session_date=F('ad_hoc_session__date'))
        .annotate(c=Count('id'))
    ):
        if row['session_date'] is None:
            continue
        day_key = row['session_date'].isoformat()
        bucket = trend_map.setdefault(day_key, _empty_status())
        _bump(bucket, row['status'], row['c'])

    total_sessions = sum(status_counts.values())
    attended = status_counts['present'] + status_counts['late']
    countable = total_sessions - status_counts['excused']
    lesson_rate = (attended / countable) if countable else None

    # Only emit trend days that have marks (same as prior behavior).
    lesson_trend = [
        {'date': day_key, **counts}
        for day_key, counts in sorted(trend_map.items())
        if any(counts.values())
    ]

    return {
        'range': range_key,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'campus': {
            'days_in_range': days_in_range,
            'days_checked_in': days_checked_in,
            'rate': (days_checked_in / days_in_range) if days_in_range else None,
            'daily': campus_daily,
        },
        'lesson': {
            'total_sessions': total_sessions,
            'present': status_counts['present'],
            'late': status_counts['late'],
            'absent': status_counts['absent'],
            'excused': status_counts['excused'],
            'rate_attended': lesson_rate,
            'by_status': [
                {'status': k, 'count': status_counts[k]}
                for k in _STATUS_KEYS
            ],
            'by_class': sorted(by_class_map.values(), key=lambda x: x['class_label']),
            'by_subject': sorted(by_subject_map.values(), key=lambda x: x['subject_label']),
            'trend': lesson_trend,
        },
    }
