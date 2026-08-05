from rest_framework import permissions

from people.roles import (
    can_check_in,
    is_admin,
    is_staff_or_above,
    is_terminal_or_above,
)


class IsAuthenticatedNonTerminal(permissions.BasePermission):
    """
    Legacy default: staff+ full access; terminal SAFE only.
    Prefer IsStaffOrAbove for new views — terminal should not get broad reads (E1).
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_staff_or_above(request.user):
            return True
        if request.user.role == 'terminal':
            return request.method in permissions.SAFE_METHODS
        return False


class IsStaffOrAbove(permissions.BasePermission):
    """Admin or staff — day-to-day school operations."""

    def has_permission(self, request, view):
        return is_staff_or_above(request.user)


# Alias kept for existing imports
IsStaffOrAdmin = IsStaffOrAbove


class IsAdmin(permissions.BasePermission):
    """Admin only."""

    def has_permission(self, request, view):
        return is_admin(request.user)


class IsTerminalOrAbove(permissions.BasePermission):
    """Admin, staff, or terminal."""

    def has_permission(self, request, view):
        return is_terminal_or_above(request.user)


class CanCheckIn(permissions.BasePermission):
    """
    Check-in write access: terminal, staff, admin.
    Teachers are excluded until a teacher portal exists (D1).
    """

    def has_permission(self, request, view):
        return can_check_in(request.user)


class IsOwnerTeacher(permissions.BasePermission):
    """Teacher role + object ownership (for future teacher portal)."""

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'teacher'
        )

    def has_object_permission(self, request, view, obj):
        if not hasattr(request.user, 'teacher_profile') or not request.user.teacher_profile:
            return False
        if obj == request.user.teacher_profile:
            return True
        teacher_attr = getattr(obj, 'teacher', None)
        return teacher_attr == request.user.teacher_profile


class IsOwnerStudent(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'student'
        )

    def has_object_permission(self, request, view, obj):
        if not hasattr(request.user, 'student_profile') or not request.user.student_profile:
            return False
        if obj == request.user.student_profile:
            return True
        student_attr = getattr(obj, 'student', None)
        return student_attr == request.user.student_profile


class IsOwnerStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == 'staff'
        )

    def has_object_permission(self, request, view, obj):
        if not hasattr(request.user, 'staff_profile') or not request.user.staff_profile:
            return False
        if obj == request.user.staff_profile:
            return True
        staff_attr = getattr(obj, 'staff', None)
        return staff_attr == request.user.staff_profile


class IsStudentOwnerOrStaffOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if is_staff_or_above(request.user):
            return True
        if request.user.role == 'student' and obj.user == request.user:
            return True
        return False


class IsAdminOrReadOnlyAuthenticated(permissions.BasePermission):
    """
    Deprecated for operational data — too broad (any auth user can read).
    Prefer IsStaffOrAbove. Kept for tests / gradual migration.
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_admin(request.user):
            return True
        return request.method in permissions.SAFE_METHODS


class IsStaffOrAdminOrReadOnlyAuthenticated(permissions.BasePermission):
    """Deprecated — prefer IsStaffOrAbove for both read and write."""

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if is_staff_or_above(request.user):
            return True
        return request.method in permissions.SAFE_METHODS
