from datetime import timedelta, datetime
from django.utils import timezone
from class_sessions.models import SessionAttendance, AdHocSessionAttendance

def process_checkin_attendance(checkin):
    """
    Updates a student's session attendance records for the day of their check-in.
    
    Rules:
    - Only updates records that are currently 'absent' to prevent overwriting manual overrides.
    - Present: Check-in timestamp is <= session start time + 15 minutes grace period.
    - Late: Check-in timestamp is > start time + 15 mins, but <= session end time.
    - Absent: Check-in timestamp is > session end time (status remains untouched).
    """
    # 1. Regular Sessions
    attendances = SessionAttendance.objects.select_related('session').filter(
        student=checkin.student,
        session__start_time__date=checkin.date,
        status='absent'
    )

    to_update = []
    for attendance in attendances:
        session = attendance.session
        grace_period_end = session.start_time + timedelta(minutes=15)
        
        if checkin.timestamp <= grace_period_end:
            attendance.status = 'present'
            attendance.auto_marked_by_checkin = checkin
            to_update.append(attendance)
        elif checkin.timestamp <= session.end_time:
            attendance.status = 'late'
            attendance.auto_marked_by_checkin = checkin
            to_update.append(attendance)

    if to_update:
        SessionAttendance.objects.bulk_update(
            to_update, ['status', 'auto_marked_by_checkin']
        )

    # 2. Ad-Hoc Sessions
    adhoc_attendances = AdHocSessionAttendance.objects.select_related('ad_hoc_session').filter(
        student=checkin.student,
        ad_hoc_session__date=checkin.date,
        status='absent'
    )

    adhoc_to_update = []
    current_tz = timezone.get_current_timezone()

    for att in adhoc_attendances:
        session = att.ad_hoc_session
        
        # Combine date and time to create timezone-aware datetime objects
        session_start = timezone.make_aware(datetime.combine(session.date, session.start_time), current_tz)
        session_end = timezone.make_aware(datetime.combine(session.date, session.end_time), current_tz)
        
        grace_period_end = session_start + timedelta(minutes=15)
        
        if checkin.timestamp <= grace_period_end:
            att.status = 'present'
            att.auto_marked_by_checkin = checkin
            adhoc_to_update.append(att)
        elif checkin.timestamp <= session_end:
            att.status = 'late'
            att.auto_marked_by_checkin = checkin
            adhoc_to_update.append(att)

    if adhoc_to_update:
        AdHocSessionAttendance.objects.bulk_update(
            adhoc_to_update, ['status', 'auto_marked_by_checkin']
        )
