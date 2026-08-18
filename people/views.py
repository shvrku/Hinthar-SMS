from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework import status
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes, inline_serializer
from rest_framework import serializers as drf_serializers
from people.serializers import (
    UserSerializer, AdminUserSerializer, SubjectSerializer, TeacherSerializer, StudentSerializer, StaffSerializer, AuditLogSerializer
)
from people.models import Subject, Teacher, Student, Staff, AuditLog
from people.audit import (
    CATEGORY_STUDENT,
    CATEGORY_USER,
    AuditActorMixin,
    AuditedViewSetMixin,
    log_event,
)
from people.permissions import IsAdmin, IsStaffOrAbove, IsStudentOwnerOrStaffOrAdmin
from people.roles import ROLE_RANK
from people.student_analytics import VALID_RANGES, build_student_attendance_summary
from people.teacher_analytics import build_teacher_attendance_summary

User = get_user_model()

LINKABLE_USER_ROLES = frozenset({'pending', 'student'})


def _parse_linked_param(request):
    raw = (request.query_params.get('linked') or '').strip().lower()
    if raw in ('true', '1', 'yes'):
        return True
    if raw in ('false', '0', 'no'):
        return False
    return None


def _user_has_other_profile(user):
    return (
        Teacher.objects.filter(user=user).exists()
        or Staff.objects.filter(user=user).exists()
    )


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
        user = (
            User.objects
            .select_related('teacher_profile', 'student_profile', 'staff_profile')
            .get(pk=request.user.pk)
        )
        serializer = UserSerializer(user)
        return Response(serializer.data)


class MeStudentView(APIView):
    """Owner-scoped student profile + QR token. No student id in the URL."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: StudentSerializer},
        summary="Get the linked student profile for the current user",
        description=(
            "Student role only. Returns 404 when the account is not matched to a "
            "Student row. Includes the check-in token for the owner."
        ),
    )
    def get(self, request):
        if request.user.role != 'student':
            return Response(
                {'error': 'Student role required.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            student = (
                Student.objects
                .select_related('user')
                .prefetch_related('enrolled_classes__class_obj')
                .get(user=request.user)
            )
        except Student.DoesNotExist:
            return Response(
                {'error': 'Account is not linked to a student record.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = StudentSerializer(
            student,
            context={'request': request, 'include_check_in_token': True},
        )
        return Response(serializer.data)


class MeAttendanceSummaryView(APIView):
    """Owner-scoped campus + lesson attendance. No student id in the URL."""
    permission_classes = [IsAuthenticated]

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
        summary='Own campus + lesson attendance summary',
        description='Student role only. Uses the linked Student row for request.user.',
    )
    def get(self, request):
        if request.user.role != 'student':
            return Response(
                {'error': 'Student role required.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            student = Student.objects.get(user=request.user)
        except Student.DoesNotExist:
            return Response(
                {'error': 'Account is not linked to a student record.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        range_key = (request.query_params.get('range') or '').strip().lower()
        if range_key not in VALID_RANGES:
            return Response(
                {'error': f'range must be one of: {", ".join(sorted(VALID_RANGES))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(build_student_attendance_summary(student, range_key))


class SubjectViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Subject.objects.order_by('id')
    serializer_class = SubjectSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    pagination_class = None  # small catalog — used as dropdown options


class TeacherViewSet(AuditedViewSetMixin, BulkOperationsMixin, ModelViewSet):
    queryset = Teacher.objects.select_related('user').order_by('id')
    serializer_class = TeacherSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    audit_category = 'teacher'
    audit_noun = 'teacher'
    audit_noun_plural = 'teachers'
    audit_label_attr = 'name'

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


class StudentViewSet(AuditedViewSetMixin, BulkOperationsMixin, ModelViewSet):
    queryset = Student.objects.select_related('user').order_by('id')
    serializer_class = StudentSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    audit_category = 'student'
    audit_noun = 'student'
    audit_noun_plural = 'students'
    audit_label_attr = 'name'

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

    def _is_owner(self, request):
        """True when the requester is the student who owns this resource."""
        return (
            request.user.is_authenticated
            and request.user.role == 'student'
        )

    def get_permissions(self):
        """Owner may retrieve their own record + attendance-summary; mutations remain staff-only."""
        if self.action in ('retrieve', 'attendance_summary'):
            return [IsStudentOwnerOrStaffOrAdmin()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset().prefetch_related('enrolled_classes__class_obj')

        # Owner (student role): scope to their own record for safe read actions.
        if self._is_owner(self.request) and self.action in ('retrieve', 'attendance_summary'):
            return qs.filter(user=self.request.user)

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

        linked = _parse_linked_param(self.request)
        if linked is True:
            qs = qs.filter(user__isnull=False)
        elif linked is False:
            qs = qs.filter(user__isnull=True)

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
        log_event(
            user=request.user,
            category=CATEGORY_STUDENT,
            action='update',
            summary=f"Regenerated check-in QR for {student.name}",
            model_name='Student',
            record_id=student.pk,
            field_name='check_in_token',
        )
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
            log_event(
                user=request.user,
                category=CATEGORY_STUDENT,
                action='update',
                summary=f"Activated check-in QR for {student.name}",
                model_name='Student',
                record_id=student.pk,
                field_name='check_in_token_active',
                old_value=False,
                new_value=True,
            )
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
            log_event(
                user=request.user,
                category=CATEGORY_STUDENT,
                action='update',
                summary=f"Deactivated check-in QR for {student.name}",
                model_name='Student',
                record_id=student.pk,
                field_name='check_in_token_active',
                old_value=True,
                new_value=False,
            )
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
            'Owner student, staff, or admin. Campus check-in and lesson roll are returned '
            'as separate objects. Never blend them into a single rate.'
        ),
    )
    @action(detail=True, methods=['get'], url_path='attendance-summary',
            permission_classes=[IsStudentOwnerOrStaffOrAdmin])
    def attendance_summary(self, request, pk=None):
        student = self.get_object()
        self.check_object_permissions(request, student)
        range_key = (request.query_params.get('range') or '').strip().lower()
        if range_key not in VALID_RANGES:
            return Response(
                {'error': f'range must be one of: {", ".join(sorted(VALID_RANGES))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = build_student_attendance_summary(student, range_key)
        return Response(payload)

    @extend_schema(
        request=inline_serializer(
            name='LinkStudentUserRequest',
            fields={'user_id': drf_serializers.IntegerField()},
        ),
        responses={200: StudentSerializer},
        summary='Link a Clerk account to this student',
        description=(
            'Admin only. Sets Student.user and promotes the account role to student. '
            'User must be pending or student, with no existing profile link.'
        ),
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def link_user(self, request, pk=None):
        student = self.get_object()
        if student.user_id:
            return Response(
                {'error': 'This student is already linked to an account. Unlink first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_id = request.data.get('user_id')
        try:
            user_id = int(raw_id)
        except (TypeError, ValueError):
            return Response(
                {'error': 'user_id is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            target = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if target.role not in LINKABLE_USER_ROLES:
            return Response(
                {'error': f'Cannot link a {target.role} account to a student.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if _user_has_other_profile(target):
            return Response(
                {'error': 'This account is already linked to a teacher or staff profile.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if Student.objects.filter(user=target).exists():
            return Response(
                {'error': 'This account is already linked to another student.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                student.user = target
                student.save(update_fields=['user'])
                if target.role != 'student':
                    target.role = 'student'
                    target.save(update_fields=['role'])
        except IntegrityError:
            return Response(
                {'error': 'This account is already linked to a student.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(student)
        return Response(serializer.data)

    @extend_schema(
        responses={200: StudentSerializer},
        summary='Unlink the account from this student',
        description=(
            'Admin only. Clears Student.user. If the account role is student, '
            'it is set back to pending.'
        ),
    )
    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def unlink_user(self, request, pk=None):
        student = self.get_object()
        previous = student.user
        if previous is None:
            return Response(
                {'error': 'This student is not linked to an account.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            student.user = None
            student.save(update_fields=['user'])
            if previous.role == 'student':
                previous.role = 'pending'
                previous.save(update_fields=['role'])

        serializer = self.get_serializer(student)
        return Response(serializer.data)


class StaffViewSet(AuditedViewSetMixin, BulkOperationsMixin, ModelViewSet):
    queryset = Staff.objects.select_related('user').order_by('id')
    serializer_class = StaffSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    audit_category = 'staff'
    audit_noun = 'staff member'
    audit_noun_plural = 'staff members'
    audit_label_attr = 'name'


class UserViewSet(AuditActorMixin, BulkOperationsMixin, ModelViewSet):
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

        linked = _parse_linked_param(self.request)
        if linked is True:
            qs = qs.filter(student_profile__isnull=False)
        elif linked is False:
            qs = qs.filter(student_profile__isnull=True)

        linkable = (self.request.query_params.get('linkable') or '').strip().lower()
        if linkable in ('true', '1', 'yes'):
            qs = qs.filter(
                role__in=LINKABLE_USER_ROLES,
                teacher_profile__isnull=True,
                staff_profile__isnull=True,
            )

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

    def perform_update(self, serializer):
        old_role = serializer.instance.role
        old_active = serializer.instance.is_active
        instance = serializer.save()
        label = instance.email or instance.username
        if instance.role != old_role:
            log_event(
                user=self.request.user,
                category=CATEGORY_USER,
                action='update',
                summary=f"Changed role of {label} from {old_role} to {instance.role}",
                model_name='User',
                record_id=instance.pk,
                field_name='role',
                old_value=old_role,
                new_value=instance.role,
            )
        elif instance.is_active != old_active:
            state = 'Activated' if instance.is_active else 'Deactivated'
            log_event(
                user=self.request.user,
                category=CATEGORY_USER,
                action='update',
                summary=f"{state} account {label}",
                model_name='User',
                record_id=instance.pk,
                field_name='is_active',
                old_value=old_active,
                new_value=instance.is_active,
            )


class AuditLogViewSet(ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related('user').order_by('-timestamp')
    serializer_class = AuditLogSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['-timestamp']

    def get_queryset(self):
        qs = super().get_queryset()
        category = (self.request.query_params.get('category') or '').strip()
        if category:
            qs = qs.filter(category=category)
        return qs
