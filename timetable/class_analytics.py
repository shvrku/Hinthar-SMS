from datetime import date, timedelta

from django.db.models import Min
from django.utils import timezone

from class_sessions.models import CheckIn, SessionAttendance
from people.student_analytics import VALID_RANGES, _iter_dates


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
    calendar_days = list(_iter_dates(date_from, date_to))

    enrolled_ids = list(
        class_obj.class_students.values_list('student_id', flat=True)
    )
    enrolled_count = len(enrolled_ids)

    check_in_qs = CheckIn.objects.filter(
        student_id__in=enrolled_ids,
        date__gte=date_from,
        date__lte=date_to,
    )
    check_ins_by_date = {}
    for d, student_id in check_in_qs.values_list('date', 'student_id'):
        check_ins_by_date.setdefault(d, set()).add(student_id)

    campus_daily = [
        {
            'date': d.isoformat(),
            'checked_in': len(check_ins_by_date.get(d, ())),
            'enrolled': enrolled_count,
        }
        for d in calendar_days
    ]
    total_campus_slots = enrolled_count * len(calendar_days)
    total_check_ins = sum(len(s) for s in check_ins_by_date.values())

    session_rows = (
        SessionAttendance.objects.filter(
            session__class_obj=class_obj,
            session__start_time__date__gte=date_from,
            session__start_time__date__lte=date_to,
        )
        .select_related(
            'session__teacher',
            'session__timetable_slot__subject',
            'session__actual_teacher',
        )
    )

    status_counts = {'present': 0, 'late': 0, 'absent': 0, 'excused': 0}
    trend_map = {}
    by_subject_map = {}
    by_teacher_map = {}

    for row in session_rows:
        status = row.status if row.status in status_counts else 'absent'
        status_counts[status] += 1
        session_date = row.session.start_time.date().isoformat()
        bucket = trend_map.setdefault(
            session_date, {'present': 0, 'late': 0, 'absent': 0, 'excused': 0}
        )
        bucket[status] += 1

        subject = getattr(row.session.timetable_slot, 'subject', None)
        subject_key = subject.id if subject else 0
        subject_label = subject.name if subject else 'Unknown'
        subject_entry = by_subject_map.setdefault(
            subject_key,
            {
                'subject_id': subject.id if subject else None,
                'subject_label': subject_label,
                'present': 0,
                'late': 0,
                'absent': 0,
                'excused': 0,
                'total': 0,
            },
        )
        subject_entry[status] += 1
        subject_entry['total'] += 1

        teacher = row.session.actual_teacher or row.session.teacher
        teacher_key = teacher.id if teacher else 0
        teacher_entry = by_teacher_map.setdefault(
            teacher_key,
            {
                'teacher_id': teacher.id if teacher else None,
                'teacher_name': teacher.name if teacher else 'Unknown',
                'present': 0,
                'late': 0,
                'absent': 0,
                'excused': 0,
                'total': 0,
            },
        )
        teacher_entry[status] += 1
        teacher_entry['total'] += 1

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
                for k in ('present', 'late', 'absent', 'excused')
            ],
            'by_subject': sorted(by_subject_map.values(), key=lambda x: x['subject_label']),
            'by_teacher': sorted(by_teacher_map.values(), key=lambda x: x['teacher_name']),
            'trend': lesson_trend,
        },
    }
