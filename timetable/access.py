from people.roles import is_active_account, is_staff_or_above
from timetable.models import ClassStudent, StudentSubjectEnrollment


def can_read_teacher_timetable(user, teacher_id: int) -> bool:
    """Staff+ any teacher; linked teacher only their own weekly slots."""
    if not is_active_account(user):
        return False
    if is_staff_or_above(user):
        return True
    if getattr(user, "role", None) != "teacher":
        return False
    profile = getattr(user, "teacher_profile", None)
    return profile is not None and profile.id == teacher_id


def can_read_class_timetable(user, class_id: int) -> bool:
    """Staff+ any class; linked student only classes/courses they are enrolled in."""
    if not is_active_account(user):
        return False
    if is_staff_or_above(user):
        return True
    if getattr(user, "role", None) != "student":
        return False
    profile = getattr(user, "student_profile", None)
    if profile is None:
        return False
    if ClassStudent.objects.filter(student_id=profile.id, class_obj_id=class_id).exists():
        return True
    return StudentSubjectEnrollment.objects.filter(
        student_id=profile.id, class_obj_id=class_id, status='enrolled'
    ).exists()
