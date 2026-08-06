from datetime import timedelta

from django.utils import timezone

from class_sessions.models import CheckIn, SessionAttendance, AdHocSessionAttendance


VALID_RANGES = frozenset({'week', 'month', 'all'})


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

    calendar_days = list(_iter_dates(date_from, date_to))
    campus_daily = [
        {'date': d.isoformat(), 'checked_in': d in check_in_dates}
        for d in calendar_days
    ]
    days_in_range = len(calendar_days)
    days_checked_in = len(check_in_dates)

    session_rows = (
        SessionAttendance.objects.filter(
            student=student,
            session__start_time__date__gte=date_from,
            session__start_time__date__lte=date_to,
        )
        .select_related('session__class_obj', 'session__timetable_slot__subject')
    )

    adhoc_rows = (
        AdHocSessionAttendance.objects.filter(
            student=student,
            ad_hoc_session__date__gte=date_from,
            ad_hoc_session__date__lte=date_to,
        )
        .select_related('ad_hoc_session__subject')
    )

    status_counts = {'present': 0, 'late': 0, 'absent': 0, 'excused': 0}
    trend_map = {}
    by_class_map = {}
    by_subject_map = {}

    for row in session_rows:
        status = row.status if row.status in status_counts else 'absent'
        status_counts[status] += 1
        session_date = row.session.start_time.date().isoformat()
        bucket = trend_map.setdefault(session_date, {'present': 0, 'late': 0, 'absent': 0, 'excused': 0})
        bucket[status] += 1

        class_obj = row.session.class_obj
        class_key = class_obj.id
        class_entry = by_class_map.setdefault(
            class_key,
            {
                'class_id': class_obj.id,
                'class_label': str(class_obj),
                'present': 0,
                'late': 0,
                'absent': 0,
                'excused': 0,
                'total': 0,
            },
        )
        class_entry[status] += 1
        class_entry['total'] += 1

        subject = getattr(row.session.timetable_slot, 'subject', None)
        subject_key = subject.id if subject else 0
        subject_entry = by_subject_map.setdefault(
            subject_key,
            {
                'subject_id': subject.id if subject else None,
                'subject_label': subject.name if subject else 'Unknown',
                'present': 0,
                'late': 0,
                'absent': 0,
                'excused': 0,
                'total': 0,
            },
        )
        subject_entry[status] += 1
        subject_entry['total'] += 1

    for row in adhoc_rows:
        status = row.status if row.status in status_counts else 'absent'
        status_counts[status] += 1
        session_date = row.ad_hoc_session.date.isoformat()
        bucket = trend_map.setdefault(session_date, {'present': 0, 'late': 0, 'absent': 0, 'excused': 0})
        bucket[status] += 1

        subject = row.ad_hoc_session.subject
        subject_key = subject.id if subject else 0
        subject_entry = by_subject_map.setdefault(
            subject_key,
            {
                'subject_id': subject.id if subject else None,
                'subject_label': subject.name if subject else 'Ad-hoc',
                'present': 0,
                'late': 0,
                'absent': 0,
                'excused': 0,
                'total': 0,
            },
        )
        subject_entry[status] += 1
        subject_entry['total'] += 1

    total_sessions = sum(status_counts.values())
    attended = status_counts['present'] + status_counts['late']
    countable = total_sessions - status_counts['excused']
    lesson_rate = (attended / countable) if countable else None

    lesson_trend = [
        {
            'date': d.isoformat(),
            **trend_map.get(d.isoformat(), {'present': 0, 'late': 0, 'absent': 0, 'excused': 0}),
        }
        for d in calendar_days
        if any(trend_map.get(d.isoformat(), {}).values())
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
                for k in ('present', 'late', 'absent', 'excused')
            ],
            'by_class': sorted(by_class_map.values(), key=lambda x: x['class_label']),
            'by_subject': sorted(by_subject_map.values(), key=lambda x: x['subject_label']),
            'trend': lesson_trend,
        },
    }
