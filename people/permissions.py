from rest_framework import permissions


class IsAuthenticatedNonTerminal(permissions.BasePermission):
    """
    Default DRF permission: admin/staff get full access,
    terminal gets read-only. Student and teacher are blocked
    by default — they can only access views with explicit permissions.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin and staff get full read + write
        if request.user.role in ('admin', 'staff'):
            return True

        # Terminal gets read-only
        if request.user.role == 'terminal':
            return request.method in permissions.SAFE_METHODS

        # Student and teacher are blocked by default
        return False


class CanCheckIn(permissions.BasePermission):
    """
    Allows access to terminal accounts for check-in operations,
    plus staff, admin, and teachers who may process manual check-ins.
    """
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in ('terminal', 'admin', 'staff', 'teacher')
        )


class IsAdmin(permissions.BasePermission):
    """
    Allows access only to Admin users.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'admin'
        )


class IsOwnerTeacher(permissions.BasePermission):
    """
    Allows access to Teachers, and checks object-level ownership if needed.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'teacher'
        )

    def has_object_permission(self, request, view, obj):
        # Checks if user has a teacher record and matches the object
        if not hasattr(request.user, 'teacher_profile') or not request.user.teacher_profile:
            return False
            
        # If the object is the Teacher record itself
        if obj == request.user.teacher_profile:
            return True
            
        # Or if the object references a teacher
        teacher_attr = getattr(obj, 'teacher', None)
        return teacher_attr == request.user.teacher_profile


class IsOwnerStudent(permissions.BasePermission):
    """
    Allows access to Students, and checks object-level ownership if needed.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'student'
        )

    def has_object_permission(self, request, view, obj):
        # Checks if user has a student record and matches the object
        if not hasattr(request.user, 'student_profile') or not request.user.student_profile:
            return False
            
        if obj == request.user.student_profile:
            return True
            
        student_attr = getattr(obj, 'student', None)
        return student_attr == request.user.student_profile


class IsOwnerStaff(permissions.BasePermission):
    """
    Allows access to Staff, and checks object-level ownership if needed.
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role == 'staff'
        )

    def has_object_permission(self, request, view, obj):
        if not hasattr(request.user, 'staff_profile') or not request.user.staff_profile:
            return False
            
        if obj == request.user.staff_profile:
            return True
            
        staff_attr = getattr(obj, 'staff', None)
        return staff_attr == request.user.staff_profile


class IsStaffOrAdmin(permissions.BasePermission):
    """Allows access only to Staff or Admin users."""
    def has_permission(self, request, view):
        return (
            request.user and
            request.user.is_authenticated and
            request.user.role in ('admin', 'staff')
        )


class IsStudentOwnerOrStaffOrAdmin(permissions.BasePermission):
    """
    Allows access if the user is:
    - the student themselves (the Student's linked User == request.user), or
    - Staff, or
    - Admin.
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        if request.user.role in ('admin', 'staff'):
            return True
        if request.user.role == 'student' and obj.user == request.user:
            return True
        return False
