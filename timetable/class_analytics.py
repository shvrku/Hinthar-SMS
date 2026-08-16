from datetime import date, timedelta

from django.db.models import Count, F, Min
from django.db.models.functions import TruncDate
from django.utils import timezone

from class_sessions.datetime_bounds import aware_day_range
from class_sessions.models import CheckIn, SessionAttendance
from people.student_analytics import VALID_RANGES, _bump, _empty_status, _iter_dates, _STATUS_KEYS


def resolve_class_analytics_range(range_key: str, class_obj) -> tuple[date, date]:
    """Return (date_from, date_to) for class attendance windows."""
    today = timezone.localdate()
    if range_key == 'week':
        date_from = today - timedelta(days=today.weekday())
    elif range_key == 'month':
        date_from = today.replace(day=1)
    elif range_key == 'all':
        earliest = (
            class_obj.sessions.aggregate(earliest=Min('start_time'))['earliest']
        )
        if earliest is not None:
            date_from = timezone.localtime(earliest).date()
        else:
            date_from = today - timedelta(days=365)
    else:
        raise ValueError(f'Invalid range: {range_key}')
    return date_from, today


def build_class_attendance_summary(class_obj, range_key: str):
    if range_key not in VALID_RANGES:
        raise ValueError(f'range must be one of: {", ".join(sorted(VALID_RANGES))}')

    date_from, date_to = resolve_class_analytics_range(range_key, class_obj)
    # Keep full since-first-session daily series (range=all semantics unchanged).
    calendar_days = list(_iter_dates(date_from, date_to))
    start_dt, end_dt = aware_day_range(date_from, date_to)

    enrolled_count = class_obj.class_students.count()

    check_ins_by_date = {
        row['date']: row['c']
        for row in (
            CheckIn.objects.filter(
                student__enrolled_classes__class_obj=class_obj,
                date__gte=date_from,
                date__lte=date_to,
            )
            .values('date')
            .annotate(c=Count('student_id', distinct=True))
        )
    }

    campus_daily = [
        {
            'date': d.isoformat(),
            'checked_in': check_ins_by_date.get(d, 0),
            'enrolled': enrolled_count,
        }
        for d in calendar_days
    ]
    total_campus_slots = enrolled_count * len(calendar_days)
    total_check_ins = sum(check_ins_by_date.values())

    session_base = SessionAttendance.objects.filter(
        session__class_obj=class_obj,
        session__start_time__gte=start_dt,
        session__start_time__lt=end_dt,
    )

    status_counts = _empty_status()
    for row in session_base.values('status').annotate(c=Count('id')):
        _bump(status_counts, row['status'], row['c'])

    by_subject_map = {}
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

    by_teacher_map = {}
    for row in (
        session_base
        .values(
            'status',
            assigned_id=F('session__teacher_id'),
            actual_id=F('session__actual_teacher_id'),
            assigned_name=F('session__teacher__name'),
            actual_name=F('session__actual_teacher__name'),
        )
        .annotate(c=Count('id'))
    ):
        teacher_id = row['actual_id'] or row['assigned_id']
        teacher_name = row['actual_name'] or row['assigned_name'] or 'Unknown'
        teacher_key = teacher_id or 0
        entry = by_teacher_map.setdefault(
            teacher_key,
            {
                'teacher_id': teacher_id,
                'teacher_name': teacher_name,
                **_empty_status(),
                'total': 0,
            },
        )
        _bump(entry, row['status'], row['c'])
        entry['total'] += row['c']

    trend_map = {}
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

    total_sessions = sum(status_counts.values())
    attended = status_counts['present'] + status_counts['late']
    countable = total_sessions - status_counts['excused']
    lesson_rate = (attended / countable) if countable else None

    lesson_trend = [
        {
            'date': d.isoformat(),
            **trend_map.get(d.isoformat(), _empty_status()),
        }
        for d in calendar_days
        if any(trend_map.get(d.isoformat(), {}).values())
    ]

    return {
        'range': range_key,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'campus': {
            'enrolled_students': enrolled_count,
            'days_in_range': len(calendar_days),
            'check_ins': total_check_ins,
            'rate': (total_check_ins / total_campus_slots) if total_campus_slots else None,
            'daily': campus_daily,
        },
        'lesson': {
            'total_marks': total_sessions,
            'present': status_counts['present'],
            'late': status_counts['late'],
            'absent': status_counts['absent'],
            'excused': status_counts['excused'],
            'rate_attended': lesson_rate,
            'by_status': [
                {'status': k, 'count': status_counts[k]}
                for k in _STATUS_KEYS
            ],
            'by_subject': sorted(by_subject_map.values(), key=lambda x: x['subject_label']),
            'by_teacher': sorted(by_teacher_map.values(), key=lambda x: x['teacher_name']),
            'trend': lesson_trend,
        },
    }
