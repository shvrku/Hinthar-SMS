from datetime import date, datetime, timedelta
import calendar

from django.utils import timezone

from class_sessions.models import Session, SessionAttendance
from timetable.models import TimetableSlot, ClassStudent


def get_month_end(reference_date=None):
    """Return the last day of the month for the given date (defaults to today)."""
    if reference_date is None:
        reference_date = timezone.localdate()
    last_day = calendar.monthrange(reference_date.year, reference_date.month)[1]
    return reference_date.replace(day=last_day)


def generate_sessions_for_slots(slots, start_date=None, end_date=None):
    """
    Generate sessions for the given timetable slots within a date range.
    
    Args:
        slots: queryset or list of TimetableSlot instances
        start_date: first day to consider (defaults to today)
        end_date: last day to consider (defaults to end of current month)
    
    Returns:
        tuple of (created_sessions, existing_sessions) — both are lists of Session instances
    """
    if start_date is None:
        start_date = timezone.localdate()
    if end_date is None:
        end_date = get_month_end(start_date)

    # Pre-fetch class student rosters keyed by class_obj_id
    class_ids = set()
    for slot in slots:
        if slot.class_obj_id:
            class_ids.add(slot.class_obj_id)

    class_students_map = {}
    if class_ids:
        for cs in ClassStudent.objects.filter(class_obj_id__in=class_ids).select_related('student'):
            class_students_map.setdefault(cs.class_obj_id, []).append(cs.student)

    created_sessions = []
    existing_sessions = []

    for slot in slots:
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() == slot.day_of_week:
                start_dt = timezone.make_aware(datetime.combine(current_date, slot.start_time))
                end_dt = timezone.make_aware(datetime.combine(current_date, slot.end_time))

                session, created = Session.objects.get_or_create(
                    timetable_slot=slot,
                    start_time=start_dt,
                    defaults={
                        'end_time': end_dt,
                        'teacher': slot.teacher,
                        'class_obj': slot.class_obj,
                        'status': 'scheduled',
                    }
                )

                if created:
                    created_sessions.append(session)
                    # Auto-create attendance rows from the class roster
                    students = class_students_map.get(slot.class_obj_id, [])
                    if students:
                        SessionAttendance.objects.bulk_create(
                            [SessionAttendance(session=session, student=s, status='absent')
                             for s in students],
                            ignore_conflicts=True,
                        )
                else:
                    existing_sessions.append(session)

            current_date += timedelta(days=1)

    return created_sessions, existing_sessions
