from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from drf_spectacular.utils import extend_schema
from people.serializers import (
    UserSerializer, SubjectSerializer, TeacherSerializer, StudentSerializer, StaffSerializer, AuditLogSerializer
)
from people.models import Subject, Teacher, Student, Staff, AuditLog
from people.permissions import IsAdmin, IsStaffOrAdmin, IsStudentOwnerOrStaffOrAdmin, IsAdminOrReadOnlyAuthenticated

User = get_user_model()

class MeView(APIView):
    """
    Returns the authenticated user's profile info.
    This endpoint is JIT provisioned automatically upon token validation.
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        responses={200: UserSerializer},
        summary="Get current user details",
        description="Retrieve profile details for the currently logged in user based on Clerk access token validation."
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

class SubjectViewSet(ModelViewSet):
    queryset = Subject.objects.all()
    serializer_class = SubjectSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]

class TeacherViewSet(ModelViewSet):
    queryset = Teacher.objects.select_related('user').all()
    serializer_class = TeacherSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]

class StudentViewSet(ModelViewSet):
    queryset = Student.objects.select_related('user').all()
    serializer_class = StudentSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]

    @action(detail=True, methods=['get'],
            permission_classes=[IsStudentOwnerOrStaffOrAdmin])
    def check_in_token(self, request, pk=None):
        """Retrieve a student's check-in token. Owner (student), staff, or admin only."""
        student = self.get_object()
        self.check_object_permissions(request, student)
        return Response({'check_in_token': student.check_in_token})

    @action(detail=True, methods=['post'],
            permission_classes=[IsStaffOrAdmin])
    def regenerate_check_in_token(self, request, pk=None):
        """Regenerate a student's check-in token. Staff or admin only."""
        student = self.get_object()
        student.regenerate_check_in_token()
        return Response({'check_in_token': student.check_in_token})

class StaffViewSet(ModelViewSet):
    queryset = Staff.objects.select_related('user').all()
    serializer_class = StaffSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]


class UserViewSet(ModelViewSet):
    queryset = User.objects.select_related(
        'teacher_profile', 'student_profile', 'staff_profile'
    ).all()
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]


class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
