from datetime import timedelta
from class_sessions.models import SessionAttendance

def process_checkin_attendance(checkin):
    """
    Updates a student's session attendance records for the day of their check-in.
    
    Rules:
    - Only updates records that are currently 'absent' to prevent overwriting manual overrides.
    - Present: Check-in timestamp is <= session start time + 15 minutes grace period.
    - Late: Check-in timestamp is > start time + 15 mins, but <= session end time.
    - Absent: Check-in timestamp is > session end time (status remains untouched).
    """
    # Get all absent attendance records for this student on this check-in date
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
            to_update.append(attendance)
        elif checkin.timestamp <= session.end_time:
            attendance.status = 'late'
            to_update.append(attendance)
        # If checkin.timestamp > session.end_time, they are absent for this session

    if to_update:
        SessionAttendance.objects.bulk_update(to_update, ['status'])
