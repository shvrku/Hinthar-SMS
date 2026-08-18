"""Guards for admin user delete / deactivate. Shared by serializer and UserViewSet."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist

User = get_user_model()


def _has_profile(user, rel_name: str) -> bool:
    try:
        return getattr(user, rel_name, None) is not None
    except ObjectDoesNotExist:
        return False


def linked_profile_labels(user) -> list[str]:
    labels = []
    for attr, label in (
        ('student_profile', 'student'),
        ('teacher_profile', 'teacher'),
        ('staff_profile', 'staff'),
    ):
        if _has_profile(user, attr):
            labels.append(label)
    return labels


def delete_blockers(user, *, actor=None, other_admin_count=None) -> list[str]:
    reasons = []
    if actor is not None and getattr(actor, 'is_authenticated', False) and actor.pk == user.pk:
        reasons.append('You cannot delete your own account.')
    if user.role == 'admin':
        if other_admin_count is None:
            other_admin_count = User.objects.filter(role='admin').exclude(pk=user.pk).count()
        if other_admin_count == 0:
            reasons.append('Cannot delete the last admin.')
    labels = linked_profile_labels(user)
    if labels:
        joined = ' and '.join(labels)
        reasons.append(f'Unlink the {joined} profile first.')
    return reasons


def deactivate_blockers(user, *, actor=None, other_active_admin_count=None) -> list[str]:
    """Reasons the account cannot be turned inactive."""
    reasons = []
    if actor is not None and getattr(actor, 'is_authenticated', False) and actor.pk == user.pk:
        reasons.append('You cannot deactivate your own account.')
    if user.role == 'admin' and user.is_active:
        if other_active_admin_count is None:
            other_active_admin_count = User.objects.filter(
                role='admin', is_active=True
            ).exclude(pk=user.pk).count()
        if other_active_admin_count == 0:
            reasons.append('Cannot deactivate the last active admin.')
    return reasons
