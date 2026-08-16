from datetime import date, timedelta

from django.db.models import Count, F, Min, Q
from django.utils import timezone

from class_sessions.datetime_bounds import aware_day_range
from class_sessions.models import AdHocSession, AdHocSessionAttendance, Session, SessionAttendance
from people.student_analytics import VALID_RANGES, _bump, _class_label, _empty_status, _STATUS_KEYS


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
    start_dt, end_dt = aware_day_range(date_from, date_to)
    teacher_id = teacher.id

    sessions = list(
        Session.objects.filter(
            Q(teacher_id=teacher_id) | Q(actual_teacher_id=teacher_id),
            start_time__gte=start_dt,
            start_time__lt=end_dt,
        ).select_related('class_obj', 'teacher', 'actual_teacher', 'timetable_slot__subject')
    )
    adhoc_sessions = list(
        AdHocSession.objects.filter(
            Q(teacher_id=teacher_id) | Q(actual_teacher_id=teacher_id),
            date__gte=date_from,
            date__lte=date_to,
        ).select_related('teacher', 'actual_teacher', 'subject')
    )

    taught_session_ids = [
        s.id for s in sessions if _effective_teacher_id(s) == teacher_id
    ]
    taught_adhoc_ids = [
        s.id for s in adhoc_sessions if _effective_teacher_id(s) == teacher_id
    ]

    status_counts = _empty_status()
    by_class_map = {}
    by_subject_map = {}

    session_att_base = SessionAttendance.objects.filter(session_id__in=taught_session_ids)
    for row in session_att_base.values('status').annotate(c=Count('id')):
        _bump(status_counts, row['status'], row['c'])

    for row in (
        session_att_base
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
        session_att_base
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

    adhoc_att_base = AdHocSessionAttendance.objects.filter(
        ad_hoc_session_id__in=taught_adhoc_ids
    )
    for row in adhoc_att_base.values('status').annotate(c=Count('id')):
        _bump(status_counts, row['status'], row['c'])

    for row in (
        adhoc_att_base
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

    total_marks = sum(status_counts.values())
    attended = status_counts['present'] + status_counts['late']
    countable = total_marks - status_counts['excused']
    lesson_rate = (attended / countable) if countable else None

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
                for k in _STATUS_KEYS
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
