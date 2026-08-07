from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes
from people.serializers import (
    UserSerializer, AdminUserSerializer, SubjectSerializer, TeacherSerializer, StudentSerializer, StaffSerializer, AuditLogSerializer
)
from people.models import Subject, Teacher, Student, Staff, AuditLog
from people.permissions import IsAdmin, IsStaffOrAbove, IsStudentOwnerOrStaffOrAdmin
from people.roles import ROLE_RANK
from people.student_analytics import VALID_RANGES, build_student_attendance_summary
from people.teacher_analytics import build_teacher_attendance_summary

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
    JIT-provisioned on token validation (role=pending for new users).
    Allowed for every authenticated role including pending.
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
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    pagination_class = None  # small catalog — used as dropdown options


class TeacherViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Teacher.objects.select_related('user').order_by('id')
    serializer_class = TeacherSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.query_params.get('q') or '').strip()
        school_code = self.request.query_params.get('school_code')
        employment_type = self.request.query_params.get('employment_type')

        if q:
            qs = qs.filter(
                Q(name__icontains=q) | Q(unique_code__icontains=q) | Q(contact__icontains=q)
            )
        if school_code and school_code != 'all':
            qs = qs.filter(school_code=school_code)
        if employment_type and employment_type != 'all':
            qs = qs.filter(employment_type=employment_type)

        return qs

    @extend_schema(
        request=TeacherSerializer(many=True),
        responses={201: TeacherSerializer(many=True)},
        summary="Bulk create teachers",
    )
    @action(detail=False, methods=['post'])
    def bulk_create(self, request):
        return super().bulk_create(request)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'range',
                OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Preset window: week | month | all',
                enum=sorted(VALID_RANGES),
            ),
        ],
        summary='Teacher accountability + personal attendance summary',
        description=(
            'Staff+. Accountability = student roll marks for sessions this teacher taught '
            '(assigned or actual). Personal = derived from session status + assigned vs actual_teacher.'
        ),
    )
    @action(detail=True, methods=['get'], url_path='attendance-summary',
            permission_classes=[IsStaffOrAbove])
    def attendance_summary(self, request, pk=None):
        teacher = self.get_object()
        range_key = (request.query_params.get('range') or '').strip().lower()
        if range_key not in VALID_RANGES:
            return Response(
                {'error': f'range must be one of: {", ".join(sorted(VALID_RANGES))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(build_teacher_attendance_summary(teacher, range_key))


class StudentViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Student.objects.select_related('user').order_by('id')
    serializer_class = StudentSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']

    # SEC-H2: only detail retrieve + dedicated token actions may include the secret
    _TOKEN_ACTIONS = frozenset({
        'retrieve',
        'check_in_token',
        'regenerate_check_in_token',
    })

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        action = getattr(self, 'action', None)
        if action in self._TOKEN_ACTIONS:
            ctx['include_check_in_token'] = True
        return ctx

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('enrolled_classes__class_obj')
        q = (self.request.query_params.get('q') or '').strip()
        school_code = self.request.query_params.get('school_code')
        class_id = self.request.query_params.get('class_id')

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(unique_code__icontains=q)
                | Q(exam_candidate_number__icontains=q)
                | Q(contact__icontains=q)
            )
        if school_code and school_code != 'all':
            qs = qs.filter(school_code=school_code)
        if class_id and class_id != 'all':
            try:
                qs = qs.filter(enrolled_classes__class_obj_id=int(class_id)).distinct()
            except (TypeError, ValueError):
                pass

        return qs

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

    @extend_schema(
        summary='Regenerate student check-in QR token',
        description='Staff+. Rotates the secret and sets check_in_token_active=true.',
    )
    @action(detail=True, methods=['post'],
            permission_classes=[IsStaffOrAbove])
    def regenerate_check_in_token(self, request, pk=None):
        """Regenerate a student's check-in token. Staff or admin only."""
        student = self.get_object()
        student.regenerate_check_in_token()
        return Response({
            'check_in_token': student.check_in_token,
            'check_in_token_active': student.check_in_token_active,
        })

    @extend_schema(
        summary='Activate student check-in QR token',
        description='Staff+. Soft-enables an existing token without rotating it.',
    )
    @action(detail=True, methods=['post'], url_path='activate_check_in_token',
            permission_classes=[IsStaffOrAbove])
    def activate_check_in_token(self, request, pk=None):
        student = self.get_object()
        if not student.check_in_token_active:
            student.check_in_token_active = True
            student.save(update_fields=['check_in_token_active'])
        return Response({'check_in_token_active': True})

    @extend_schema(
        summary='Deactivate student check-in QR token',
        description='Staff+. Soft-disables QR check-in without rotating the secret.',
    )
    @action(detail=True, methods=['post'], url_path='deactivate_check_in_token',
            permission_classes=[IsStaffOrAbove])
    def deactivate_check_in_token(self, request, pk=None):
        student = self.get_object()
        if student.check_in_token_active:
            student.check_in_token_active = False
            student.save(update_fields=['check_in_token_active'])
        return Response({'check_in_token_active': False})

    @extend_schema(
        parameters=[
            OpenApiParameter(
                'range',
                OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description='Preset window: week | month | all (since enrollment)',
                enum=sorted(VALID_RANGES),
            ),
        ],
        summary='Student campus + lesson attendance summary',
        description=(
            'Staff+. Campus check-in and lesson roll are returned as separate objects. '
            'Never blend them into a single rate.'
        ),
    )
    @action(detail=True, methods=['get'], url_path='attendance-summary',
            permission_classes=[IsStaffOrAbove])
    def attendance_summary(self, request, pk=None):
        student = self.get_object()
        range_key = (request.query_params.get('range') or '').strip().lower()
        if range_key not in VALID_RANGES:
            return Response(
                {'error': f'range must be one of: {", ".join(sorted(VALID_RANGES))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_student_attendance_summary(student, range_key)
        return Response(payload)


class StaffViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Staff.objects.select_related('user').order_by('id')
    serializer_class = StaffSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']


class UserViewSet(BulkOperationsMixin, ModelViewSet):
    """
    Account / role administration. Admin only.
    Staff operate the school but cannot elevate privileges.
    """
    queryset = User.objects.select_related(
        'teacher_profile', 'student_profile', 'staff_profile'
    ).order_by('id')
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdmin]
    ordering = ['id']
    http_method_names = ['get', 'head', 'options', 'patch', 'put']

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.query_params.get('q') or '').strip()
        role = self.request.query_params.get('role')

        if q:
            qs = qs.filter(
                Q(username__icontains=q) | Q(email__icontains=q) | Q(clerk_id__icontains=q)
            )
        if role and role != 'all':
            qs = qs.filter(role=role)

        return qs

    def _validate_role_change(self, instance, data):
        """Shared guards for PATCH and PUT (SEC-M3)."""
        new_role = data.get('role', instance.role)
        if instance.role == 'admin' and new_role != 'admin':
            other_admins = User.objects.filter(role='admin').exclude(pk=instance.pk).count()
            if other_admins == 0:
                return Response(
                    {'error': 'Cannot demote the last admin user.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if new_role is not None and new_role not in ROLE_RANK:
            return Response(
                {'error': f'Invalid role. Must be one of: {sorted(ROLE_RANK.keys())}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def partial_update(self, request, *args, **kwargs):
        """Only allow role / is_active changes; never clerk_id or self-demotion traps."""
        instance = self.get_object()
        error = self._validate_role_change(instance, request.data)
        if error is not None:
            return error
        return super().partial_update(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """PUT must apply the same last-admin / role-validity guards as PATCH."""
        instance = self.get_object()
        error = self._validate_role_change(instance, request.data)
        if error is not None:
            return error
        return super().update(request, *args, **kwargs)


class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').order_by('-timestamp')
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]
    ordering = ['-timestamp']
