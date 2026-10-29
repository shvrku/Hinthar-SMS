from django.db.models import Q
from timetable.models import (
    Class,
    ClassStudent,
    Course,
    StudentSubjectEnrollment,
    TimetableSlot,
)


def get_student_active_course_pairs(student_id: int) -> set[tuple[int, int]]:
    """
    Returns the set of active (class_obj_id, subject_id) course pairs for a student.
    Combines:
      1. All courses offered in the student's Primary Cohort(s) (ClassStudent),
         minus any course explicitly marked status='dropped' in StudentSubjectEnrollment.
      2. All courses explicitly marked status='enrolled' in StudentSubjectEnrollment
         (whether in their Primary Cohort or an external Cohort).
    """
    primary_class_ids = set(
        ClassStudent.objects.filter(student_id=student_id).values_list('class_obj_id', flat=True)
    )

    active_pairs: set[tuple[int, int]] = set()
    if primary_class_ids:
        for cid, sid in Course.objects.filter(class_obj_id__in=primary_class_ids).values_list('class_obj_id', 'subject_id'):
            active_pairs.add((cid, sid))
        for cid, sid in TimetableSlot.objects.filter(class_obj_id__in=primary_class_ids).values_list('class_obj_id', 'subject_id'):
            active_pairs.add((cid, sid))

    for cid, sid, enrollment_status in StudentSubjectEnrollment.objects.filter(
        student_id=student_id
    ).values_list('class_obj_id', 'subject_id', 'status'):
        if enrollment_status == 'dropped':
            active_pairs.discard((cid, sid))
        else:
            active_pairs.add((cid, sid))

    return active_pairs


def get_student_timetable_slots(
    student_id: int,
    extra_pairs: set[tuple[int, int]] | None = None,
) -> list[TimetableSlot]:
    """
    Returns all weekly TimetableSlot objects for a student's active courses
    (plus any candidate extra_pairs for pre-enrollment conflict preview).
    """
    pairs = get_student_active_course_pairs(student_id)
    if extra_pairs:
        pairs = pairs | set(extra_pairs)
    if not pairs:
        return []

    query = Q()
    for cid, sid in pairs:
        query |= Q(class_obj_id=cid, subject_id=sid)

    return list(
        TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher', 'course')
        .filter(query)
        .order_by('day_of_week', 'start_time', 'id')
    )


def _serialize_conflict_slot(slot: TimetableSlot) -> dict:
    cohort_identifier = str(slot.class_obj) if slot.class_obj else ''
    subject_name = slot.subject.name if slot.subject else ''
    return {
        'slot_id': slot.id,
        'course_id': slot.course_id,
        'class_id': slot.class_obj_id,
        'cohort_identifier': cohort_identifier,
        'subject_id': slot.subject_id,
        'subject_name': subject_name,
        'course_label': f"{cohort_identifier} — {subject_name}" if cohort_identifier and subject_name else subject_name,
        'teacher_id': slot.teacher_id,
        'teacher_name': slot.teacher.name if slot.teacher else None,
        'day_of_week': slot.day_of_week,
        'day_name': slot.get_day_of_week_display(),
        'start_time': slot.start_time.strftime('%H:%M:%S') if slot.start_time else None,
        'end_time': slot.end_time.strftime('%H:%M:%S') if slot.end_time else None,
        'room': slot.room,
    }


def detect_slot_conflicts(slots: list[TimetableSlot]) -> list[dict]:
    """
    Given a list of TimetableSlot instances, returns all time-overlapping pairs
    on the same day_of_week.
    """
    conflicts: list[dict] = []
    n = len(slots)
    for i in range(n):
        slot_a = slots[i]
        for j in range(i + 1, n):
            slot_b = slots[j]
            if slot_a.id == slot_b.id:
                continue
            if slot_a.day_of_week != slot_b.day_of_week:
                continue
            if slot_a.start_time < slot_b.end_time and slot_a.end_time > slot_b.start_time:
                overlap_start = max(slot_a.start_time, slot_b.start_time)
                overlap_end = min(slot_a.end_time, slot_b.end_time)
                ser_a = _serialize_conflict_slot(slot_a)
                ser_b = _serialize_conflict_slot(slot_b)
                day_name = slot_a.get_day_of_week_display()
                conflicts.append({
                    'day_of_week': slot_a.day_of_week,
                    'day_name': day_name,
                    'overlap_start': overlap_start.strftime('%H:%M:%S'),
                    'overlap_end': overlap_end.strftime('%H:%M:%S'),
                    'slot_a': ser_a,
                    'slot_b': ser_b,
                    'message': (
                        f"Timetable conflict on {day_name} "
                        f"({overlap_start.strftime('%H:%M')}–{overlap_end.strftime('%H:%M')}): "
                        f"{ser_a['course_label']} overlaps with {ser_b['course_label']}."
                    ),
                })
    return conflicts


def detect_student_conflicts(
    student_id: int,
    candidate_pairs: set[tuple[int, int]] | None = None,
) -> dict:
    """
    Computes all timetable conflicts for a student across their enrolled courses
    (and optional candidate (class_obj_id, subject_id) pairs).
    Never raises an exception — conflicts are informational warnings.
    """
    slots = get_student_timetable_slots(student_id, extra_pairs=candidate_pairs)
    conflicts = detect_slot_conflicts(slots)
    conflicting_slot_ids: set[int] = set()
    conflicting_course_keys: set[str] = set()
    for c in conflicts:
        sa = c['slot_a']
        sb = c['slot_b']
        conflicting_slot_ids.add(sa['slot_id'])
        conflicting_slot_ids.add(sb['slot_id'])
        conflicting_course_keys.add(f"{sa['class_id']}:{sa['subject_id']}")
        conflicting_course_keys.add(f"{sb['class_id']}:{sb['subject_id']}")

    return {
        'has_conflicts': len(conflicts) > 0,
        'conflict_count': len(conflicts),
        'conflicting_slot_ids': sorted(conflicting_slot_ids),
        'conflicting_course_keys': sorted(conflicting_course_keys),
        'conflicts': conflicts,
    }


def get_enrolled_students_for_course(class_obj_id: int, subject_id: int | None = None) -> list:
    """
    Returns deduplicated Student instances enrolled in a specific (class_obj_id, subject_id) course,
    or across the whole cohort if subject_id is None.
    Respects status='dropped' for primary cohort students who opted out of a course.
    """
    student_map = {}
    for cs in ClassStudent.objects.filter(class_obj_id=class_obj_id).select_related('student'):
        student_map[cs.student_id] = cs.student

    sse_qs = StudentSubjectEnrollment.objects.filter(class_obj_id=class_obj_id).select_related('student')
    if subject_id is not None:
        sse_qs = sse_qs.filter(subject_id=subject_id)
        for sse in sse_qs:
            if sse.status == 'dropped':
                student_map.pop(sse.student_id, None)
            else:
                student_map[sse.student_id] = sse.student
    else:
        for sse in sse_qs.filter(status='enrolled'):
            student_map[sse.student_id] = sse.student

    return sorted(student_map.values(), key=lambda s: (s.name or '').lower())
