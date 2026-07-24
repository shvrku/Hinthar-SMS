from django.contrib.auth import get_user_model
from django.db import transaction
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


class BulkOperationsMixin:
    """Provides reusable bulk_create and bulk_delete action endpoints."""

    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        items_data = request.data.get('items', request.data)
        if not isinstance(items_data, list):
            return Response(
                {'error': 'Expected a list of items or {"items": [...]}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        serializer = self.get_serializer(data=items_data, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_bulk_create(serializer)
        return Response(
            {'created_count': len(serializer.data), 'items': serializer.data},
            status=status.HTTP_201_CREATED
        )

    def perform_bulk_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {'error': 'Expected a non-empty list of IDs in {"ids": [...]}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        qs = self.get_queryset().filter(pk__in=ids)
        with transaction.atomic():
            deleted_count, _ = qs.delete()
        return Response(
            {'deleted_count': deleted_count, 'deleted_ids': ids},
            status=status.HTTP_200_OK
        )


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


class SubjectViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Subject.objects.order_by('id')
    serializer_class = SubjectSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']


class TeacherViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Teacher.objects.select_related('user').order_by('id')
    serializer_class = TeacherSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']

    @extend_schema(
        request=TeacherSerializer(many=True),
        responses={201: TeacherSerializer(many=True)},
        summary="Bulk create teachers",
    )
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        return super().bulk_create(request)


class StudentViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Student.objects.select_related('user').order_by('id')
    serializer_class = StudentSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']

    @extend_schema(
        request=StudentSerializer(many=True),
        responses={201: StudentSerializer(many=True)},
        summary="Bulk create students",
    )
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        return super().bulk_create(request)

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


class StaffViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Staff.objects.select_related('user').order_by('id')
    serializer_class = StaffSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']


class UserViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = User.objects.select_related(
        'teacher_profile', 'student_profile', 'staff_profile'
    ).order_by('id')
    serializer_class = UserSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']


class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').order_by('-timestamp')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    ordering = ['-timestamp']
