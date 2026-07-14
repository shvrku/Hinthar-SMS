from rest_framework import permissions

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
