from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiResponse, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from django.db.models import Q
from timetable.models import Class, ClassStudent, TimetableSlot
from timetable.serializers import (
    ClassSerializer, ClassStudentSerializer, ClassStudentListSerializer, TimetableSlotSerializer
)
from timetable.utils import generate_sessions_for_slots
from timetable.access import can_read_class_timetable, can_read_teacher_timetable
from people.audit import AuditedViewSetMixin, log_sessions_generated
from people.models import Teacher
from people.permissions import IsActiveAuthenticated, IsStaffOrAbove
from people.views import BulkOperationsMixin
from people.student_analytics import VALID_RANGES
from timetable.class_analytics import build_class_attendance_summary
from rest_framework import status
from rest_framework.decorators import action


class ClassViewSet(AuditedViewSetMixin, BulkOperationsMixin, ModelViewSet):
    queryset = Class.objects.order_by('id')
    serializer_class = ClassSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    pagination_class = None  # small catalog — used as dropdown options
    audit_category = 'class'
    audit_noun = 'class'
    audit_noun_plural = 'classes'

    def perform_destroy(self, instance):
        with transaction.atomic():
            from class_sessions.models import Session
            # Delete all sessions associated directly or through timetable slots
            # Deleting Session automatically cascades into SessionAttendance
            Session.objects.filter(
                Q(class_obj=instance) | Q(timetable_slot__class_obj=instance)
            ).delete()
            super().perform_destroy(instance)

    @action(detail=False, methods=['delete'])
    def bulk_delete(self, request):
        ids = request.data.get('ids', [])
        if not isinstance(ids, list) or not ids:
            return Response(
                {'error': 'Expected a non-empty list of IDs in {"ids": [...]}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from class_sessions.models import Session
        with transaction.atomic():
            Session.objects.filter(
                Q(class_obj_id__in=ids) | Q(timetable_slot__class_obj_id__in=ids)
            ).delete()
            qs = self.get_queryset().filter(pk__in=ids)
            classes_count = qs.count()
            qs.delete()

        request = getattr(self, 'request', None)
        user = getattr(request, 'user', None) if request else None
        from people.audit import log_event
        log_event(
            user=user,
            category=self.audit_category,
            action='delete',
            summary=f"Bulk deleted {classes_count} classes and all associated sessions/timetable records",
            model_name='Class',
            record_id='',
            new_value=str(classes_count),
        )
        return Response(
            {'deleted_count': classes_count, 'deleted_ids': ids},
            status=status.HTTP_200_OK
        )

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
        summary='Class campus + lesson attendance summary',
        description=(
            'Staff+. Lesson roll and campus check-in for enrolled students are separate objects. '
            'Never blend them into a single rate.'
        ),
    )
    @action(detail=True, methods=['get'], url_path='attendance-summary',
            permission_classes=[IsStaffOrAbove])
    def attendance_summary(self, request, pk=None):
        class_obj = self.get_object()
        range_key = (request.query_params.get('range') or '').strip().lower()
        if range_key not in VALID_RANGES:
            return Response(
                {'error': f'range must be one of: {", ".join(sorted(VALID_RANGES))}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(build_class_attendance_summary(class_obj, range_key))


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter(
                'class_id',
                OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description='Canonical class filter.',
            ),
            OpenApiParameter(
                'class_obj_id',
                OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                deprecated=True,
                description='Deprecated alias for class_id.',
            ),
            OpenApiParameter('student_id', OpenApiTypes.INT, location=OpenApiParameter.QUERY, required=False),
        ],
    ),
)
class ClassStudentViewSet(AuditedViewSetMixin, BulkOperationsMixin, ModelViewSet):
    queryset = ClassStudent.objects.select_related('class_obj', 'student__user').order_by('id')
    serializer_class = ClassStudentSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    audit_category = 'class'
    audit_noun = 'enrollment'
    audit_noun_plural = 'enrollments'

    def audit_summary(self, action, instance):
        student = getattr(getattr(instance, 'student', None), 'name', None) or instance.student_id
        klass = instance.class_obj
        if action == 'create':
            return f"Enrolled {student} in {klass}"
        if action == 'delete':
            return f"Removed {student} from {klass}"
        return f"Updated enrollment of {student} in {klass}"

    def get_serializer_class(self):
        if self.action == 'list':
            return ClassStudentListSerializer
        return ClassStudentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        class_id = self.request.query_params.get('class_id') or self.request.query_params.get('class_obj_id')
        student_id = self.request.query_params.get('student_id')
        if class_id:
            qs = qs.filter(class_obj_id=class_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs


class TimetableSlotViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').order_by('id')
    serializer_class = TimetableSlotSerializer
    permission_classes = [IsStaffOrAbove]
    ordering = ['id']
    pagination_class = None  # scoped by class; list requires class_id

    def list(self, request, *args, **kwargs):
        class_id = request.query_params.get('class_id') or request.query_params.get('class_obj_id')
        if not class_id:
            return Response(
                {'error': 'class_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        class_id = self.request.query_params.get('class_id') or self.request.query_params.get('class_obj_id')
        if class_id:
            qs = qs.filter(class_obj_id=class_id)
        return qs

    def _validate_no_overlap(self, day, start, end, teacher, room, exclude_pk=None):
        """Check teacher and room double-booking. Raises ValidationError if overlap found."""
        from rest_framework.exceptions import ValidationError

        overlap_filter = Q(day_of_week=day, start_time__lt=end, end_time__gt=start)

        teacher_overlap = TimetableSlot.objects.filter(
            overlap_filter & Q(teacher=teacher)
        )
        if exclude_pk:
            teacher_overlap = teacher_overlap.exclude(pk=exclude_pk)
        conflicting = teacher_overlap.select_related('class_obj').first()
        if conflicting:
            day_name = TimetableSlot(day_of_week=day).get_day_of_week_display()
            class_name = str(conflicting.class_obj) if conflicting.class_obj else 'Unknown'
            raise ValidationError(
                f"Teacher '{teacher.name}' already has a slot in class '{class_name}' overlapping this time on {day_name}."
            )

        if room:
            room_overlap = TimetableSlot.objects.filter(
                overlap_filter & Q(room=room)
            )
            if exclude_pk:
                room_overlap = room_overlap.exclude(pk=exclude_pk)
            if room_overlap.exists():
                day_name = TimetableSlot(day_of_week=day).get_day_of_week_display()
                raise ValidationError(
                    f"Room '{room}' is already booked for this time slot on {day_name}."
                )

    def _build_generation_summary(self, created, existed):
        """Build a serializable summary of generated sessions."""
        def _session_summary(session):
            return {
                'id': session.id,
                'timetable_slot_id': session.timetable_slot_id,
                'teacher_id': session.teacher_id,
                'class_obj_id': session.class_obj_id,
                'start_time': session.start_time.isoformat(),
                'end_time': session.end_time.isoformat(),
                'status': session.status,
            }
        return {
            'total_created': len(created),
            'total_already_existed': len(existed),
            'created': [_session_summary(s) for s in created],
            'already_existed': [_session_summary(s) for s in existed],
        }

    @transaction.atomic
    def perform_create(self, serializer):
        self._validate_no_overlap(
            day=serializer.validated_data.get('day_of_week'),
            start=serializer.validated_data.get('start_time'),
            end=serializer.validated_data.get('end_time'),
            teacher=serializer.validated_data.get('teacher'),
            room=serializer.validated_data.get('room'),
        )
        serializer.save()

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.instance
        # Merge submitted values with existing instance values for complete validation
        day = serializer.validated_data.get('day_of_week', instance.day_of_week)
        start = serializer.validated_data.get('start_time', instance.start_time)
        end = serializer.validated_data.get('end_time', instance.end_time)
        teacher = serializer.validated_data.get('teacher', instance.teacher)
        room = serializer.validated_data.get('room', instance.room)
        self._validate_no_overlap(
            day=day, start=start, end=end, teacher=teacher, room=room,
            exclude_pk=instance.pk,
        )
        serializer.save()

    @extend_schema(
        summary="Create a timetable slot",
        description="Create a timetable slot and auto-generate sessions for the rest of the month. Returns the created slot along with a summary of generated sessions.",
        responses={
            201: TimetableSlotSerializer,
            400: OpenApiResponse(description="Bad Request - Validation Error (e.g., overlapping slots, missing required fields like class_obj)"),
        }
    )
    def create(self, request, *args, **kwargs):
        """Create a timetable slot and auto-generate sessions for the rest of the month."""
        response = super().create(request, *args, **kwargs)
        slot = TimetableSlot.objects.get(pk=response.data['id'])
        created, existed = generate_sessions_for_slots([slot])
        response.data['sessions_generated'] = self._build_generation_summary(created, existed)
        log_sessions_generated(request.user, len(created), f"timetable slot on {slot.class_obj}")
        return response

    @extend_schema(
        summary="Update a timetable slot",
        description="Update a timetable slot and auto-generate sessions for the rest of the month.",
        responses={
            200: TimetableSlotSerializer,
            400: OpenApiResponse(description="Bad Request - Validation Error (e.g., overlapping slots)"),
            404: OpenApiResponse(description="Not Found"),
        }
    )
    def update(self, request, *args, **kwargs):
        """Update a timetable slot and auto-generate sessions for the rest of the month."""
        response = super().update(request, *args, **kwargs)
        slot = TimetableSlot.objects.get(pk=response.data['id'])
        created, existed = generate_sessions_for_slots([slot])
        response.data['sessions_generated'] = self._build_generation_summary(created, existed)
        log_sessions_generated(request.user, len(created), f"timetable slot on {slot.class_obj}")
        return response

    @extend_schema(
        summary="Partial update a timetable slot",
        description="Partial update a timetable slot and auto-generate sessions for the rest of the month.",
        responses={
            200: TimetableSlotSerializer,
            400: OpenApiResponse(description="Bad Request - Validation Error"),
            404: OpenApiResponse(description="Not Found"),
        }
    )
    def partial_update(self, request, *args, **kwargs):
        """Partial update a timetable slot and auto-generate sessions for the rest of the month."""
        response = super().partial_update(request, *args, **kwargs)
        slot = TimetableSlot.objects.get(pk=response.data['id'])
        created, existed = generate_sessions_for_slots([slot])
        response.data['sessions_generated'] = self._build_generation_summary(created, existed)
        log_sessions_generated(request.user, len(created), f"timetable slot on {slot.class_obj}")
        return response


class TeacherTimetableView(APIView):
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        summary="Teacher timetable",
        description=(
            "Weekly TimetableSlot rows assigned to this teacher (not dated sessions). "
            "Staff+ any teacher; linked teacher only their own id."
        ),
        responses=TimetableSlotSerializer(many=True),
    )
    def get(self, request, teacher_id):
        teacher_id = int(teacher_id)
        if not can_read_teacher_timetable(request.user, teacher_id):
            raise PermissionDenied()
        if not Teacher.objects.filter(pk=teacher_id).exists():
            raise NotFound()
        slots = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').filter(teacher_id=teacher_id).order_by('id')
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response(serializer.data)


class ClassTimetableView(APIView):
    permission_classes = [IsActiveAuthenticated]

    @extend_schema(
        summary="Class timetable",
        description=(
            "Weekly TimetableSlot rows for this class (not dated sessions). "
            "Staff+ any class; linked student only classes they are enrolled in."
        ),
        responses={200: TimetableSlotSerializer(many=True)},
    )
    def get(self, request, class_id):
        class_id = int(class_id)
        if not can_read_class_timetable(request.user, class_id):
            raise PermissionDenied()
        if not Class.objects.filter(pk=class_id).exists():
            raise NotFound()
        slots = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').filter(class_obj_id=class_id).order_by('id')
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response(serializer.data)
