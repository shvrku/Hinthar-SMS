from people.roles import is_staff_or_above
from timetable.models import ClassStudent


def can_read_teacher_timetable(user, teacher_id: int) -> bool:
    """Staff+ any teacher; linked teacher only their own weekly slots."""
    if not user or not user.is_authenticated:
        return False
    if is_staff_or_above(user):
        return True
    if getattr(user, "role", None) != "teacher":
        return False
    profile = getattr(user, "teacher_profile", None)
    return profile is not None and profile.id == teacher_id


def can_read_class_timetable(user, class_id: int) -> bool:
    """Staff+ any class; linked student only classes they are enrolled in."""
    if not user or not user.is_authenticated:
        return False
    if is_staff_or_above(user):
        return True
    if getattr(user, "role", None) != "student":
        return False
    profile = getattr(user, "student_profile", None)
    if profile is None:
        return False
    return ClassStudent.objects.filter(student_id=profile.id, class_obj_id=class_id).exists()
