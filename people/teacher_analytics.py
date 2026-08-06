from datetime import date, timedelta

from django.db.models import Min, Q
from django.utils import timezone

from class_sessions.models import AdHocSession, AdHocSessionAttendance, Session, SessionAttendance
from people.student_analytics import VALID_RANGES, _iter_dates


def resolve_teacher_analytics_range(range_key: str, teacher) -> tuple[date, date]:
    today = timezone.localdate()
    if range_key == 'week':
        date_from = today - timedelta(days=today.weekday())
    elif range_key == 'month':
        date_from = today.replace(day=1)
    elif range_key == 'all':
        candidates = []
        if teacher.join_date:
            candidates.append(teacher.join_date)
        earliest_session = teacher.sessions.aggregate(earliest=Min('start_time'))['earliest']
        if earliest_session is not None:
            candidates.append(timezone.localtime(earliest_session).date())
        earliest_adhoc = teacher.adhoc_sessions.aggregate(earliest=Min('date'))['earliest']
        if earliest_adhoc is not None:
            candidates.append(earliest_adhoc)
        date_from = min(candidates) if candidates else today - timedelta(days=365)
    else:
        raise ValueError(f'Invalid range: {range_key}')
    return date_from, today


def _effective_teacher_id(session):
    return session.actual_teacher_id or session.teacher_id


def _personal_outcome(status: str, assigned_id: int, actual_id: int | None, teacher_id: int) -> str | None:
    """
    Derive personal attendance label for this teacher on one session.
    Returns None if this teacher is not involved as assigned or actual.
    """
    is_assigned = assigned_id == teacher_id
    is_actual = actual_id == teacher_id if actual_id else False

    if status == 'scheduled':
        if is_assigned:
            return 'unmarked'
        return None

    if status == 'completed':
        if is_assigned and (actual_id is None or actual_id == assigned_id):
            return 'present'
        if is_assigned and actual_id and actual_id != assigned_id:
            return 'covered'
        if is_actual and assigned_id != teacher_id:
            return 'cover_taught'
        return None

    if status == 'no_show':
        if is_assigned:
            return 'no_show'
        return None

    if status == 'cancelled':
        if is_assigned:
            return 'cancelled'
        return None

    return None


def build_teacher_attendance_summary(teacher, range_key: str):
    if range_key not in VALID_RANGES:
        raise ValueError(f'range must be one of: {", ".join(sorted(VALID_RANGES))}')

    date_from, date_to = resolve_teacher_analytics_range(range_key, teacher)
    calendar_days = list(_iter_dates(date_from, date_to))
    teacher_id = teacher.id

    sessions = list(
        Session.objects.filter(
            Q(teacher_id=teacher_id) | Q(actual_teacher_id=teacher_id),
            start_time__date__gte=date_from,
            start_time__date__lte=date_to,
        ).select_related('class_obj', 'teacher', 'actual_teacher', 'timetable_slot__subject')
    )
    adhoc_sessions = list(
        AdHocSession.objects.filter(
            Q(teacher_id=teacher_id) | Q(actual_teacher_id=teacher_id),
            date__gte=date_from,
            date__lte=date_to,
        ).select_related('teacher', 'actual_teacher', 'subject')
    )

    # --- Accountability: student rolls for sessions this teacher taught ---
    taught_session_ids = [
        s.id for s in sessions if _effective_teacher_id(s) == teacher_id
    ]
    taught_adhoc_ids = [
        s.id for s in adhoc_sessions if _effective_teacher_id(s) == teacher_id
    ]

    status_counts = {'present': 0, 'late': 0, 'absent': 0, 'excused': 0}
    by_class_map = {}
    by_subject_map = {}

    for row in SessionAttendance.objects.filter(session_id__in=taught_session_ids).select_related(
        'session__class_obj',
        'session__timetable_slot__subject',
    ):
        status = row.status if row.status in status_counts else 'absent'
        status_counts[status] += 1
        class_obj = row.session.class_obj
        entry = by_class_map.setdefault(
            class_obj.id,
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
        entry[status] += 1
        entry['total'] += 1

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

    for row in AdHocSessionAttendance.objects.filter(
        ad_hoc_session_id__in=taught_adhoc_ids
    ).select_related('ad_hoc_session__subject'):
        status = row.status if row.status in status_counts else 'absent'
        status_counts[status] += 1
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

    total_marks = sum(status_counts.values())
    attended = status_counts['present'] + status_counts['late']
    countable = total_marks - status_counts['excused']
    lesson_rate = (attended / countable) if countable else None

    # --- Personal: derived from status + assigned vs actual ---
    personal_counts = {
        'unmarked': 0,
        'present': 0,
        'covered': 0,
        'cover_taught': 0,
        'no_show': 0,
        'cancelled': 0,
    }
    recent = []
    cover_history = []

    def push_personal(session_like, session_date, kind, class_label, subject_label):
        outcome = _personal_outcome(
            session_like.status,
            session_like.teacher_id,
            session_like.actual_teacher_id,
            teacher_id,
        )
        if outcome is None:
            return
        personal_counts[outcome] += 1
        item = {
            'kind': kind,
            'session_id': session_like.id,
            'date': session_date.isoformat() if hasattr(session_date, 'isoformat') else str(session_date),
            'status': session_like.status,
            'outcome': outcome,
            'class_label': class_label,
            'subject_label': subject_label,
            'assigned_teacher_id': session_like.teacher_id,
            'assigned_teacher_name': session_like.teacher.name if session_like.teacher else None,
            'actual_teacher_id': session_like.actual_teacher_id,
            'actual_teacher_name': (
                session_like.actual_teacher.name if session_like.actual_teacher else None
            ),
        }
        recent.append(item)
        if outcome in ('covered', 'cover_taught'):
            cover_history.append(item)

    for s in sessions:
        subject = getattr(s.timetable_slot, 'subject', None)
        push_personal(
            s,
            s.start_time.date(),
            'session',
            str(s.class_obj),
            subject.name if subject else None,
        )

    for s in adhoc_sessions:
        push_personal(
            s,
            s.date,
            'adhoc',
            None,
            s.subject.name if s.subject else None,
        )

    recent.sort(key=lambda x: x['date'], reverse=True)
    cover_history.sort(key=lambda x: x['date'], reverse=True)

    return {
        'range': range_key,
        'date_from': date_from.isoformat(),
        'date_to': date_to.isoformat(),
        'accountability': {
            'sessions_taught': len(taught_session_ids) + len(taught_adhoc_ids),
            'total_marks': total_marks,
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
        },
        'personal': {
            'by_outcome': [
                {'outcome': k, 'count': personal_counts[k]}
                for k in (
                    'unmarked',
                    'present',
                    'covered',
                    'cover_taught',
                    'no_show',
                    'cancelled',
                )
            ],
            'unmarked': personal_counts['unmarked'],
            'present': personal_counts['present'],
            'covered': personal_counts['covered'],
            'cover_taught': personal_counts['cover_taught'],
            'no_show': personal_counts['no_show'],
            'cancelled': personal_counts['cancelled'],
            'recent_sessions': recent[:40],
            'cover_history': cover_history[:40],
        },
    }
