from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse
from drf_spectacular.types import OpenApiTypes
from django.db import transaction
from django.db.models import Q
from timetable.models import Class, ClassStudent, TimetableSlot
from timetable.serializers import (
    ClassSerializer, ClassStudentSerializer, TimetableSlotSerializer
)
from timetable.utils import generate_sessions_for_slots
from people.permissions import IsAdmin, IsStaffOrAdmin, IsAdminOrReadOnlyAuthenticated, IsStaffOrAdminOrReadOnlyAuthenticated
from people.views import BulkOperationsMixin


class ClassViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = Class.objects.order_by('id')
    serializer_class = ClassSerializer
    permission_classes = [IsStaffOrAdminOrReadOnlyAuthenticated]
    ordering = ['id']


class ClassStudentViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = ClassStudent.objects.select_related('class_obj', 'student__user').order_by('id')
    serializer_class = ClassStudentSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        class_obj_id = self.request.query_params.get('class_obj_id')
        student_id = self.request.query_params.get('student_id')
        if class_obj_id:
            qs = qs.filter(class_obj_id=class_obj_id)
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs


class TimetableSlotViewSet(BulkOperationsMixin, ModelViewSet):
    queryset = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').order_by('id')
    serializer_class = TimetableSlotSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    ordering = ['id']
    
    def _validate_no_overlap(self, day, start, end, teacher, room, exclude_pk=None):
        """Check teacher and room double-booking. Raises ValidationError if overlap found."""
        from rest_framework.exceptions import ValidationError

        overlap_filter = Q(day_of_week=day, start_time__lt=end, end_time__gt=start)

        teacher_overlap = TimetableSlot.objects.filter(
            overlap_filter & Q(teacher=teacher)
        )
        if exclude_pk:
            teacher_overlap = teacher_overlap.exclude(pk=exclude_pk)
        if teacher_overlap.exists():
            day_name = TimetableSlot(day_of_week=day).get_day_of_week_display()
            raise ValidationError(
                f"Teacher '{teacher.name}' already has a slot overlapping this time on {day_name}."
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
                'start_time': session.start_time.strftime('%d/%m/%y %H:%M:%S'),
                'end_time': session.end_time.strftime('%d/%m/%y %H:%M:%S'),
                'status': session.status,
                'paid': session.paid,
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
        return response


class TeacherTimetableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Teacher timetable",
        description="Get all timetable slots for a specific teacher.",
        responses=TimetableSlotSerializer(many=True),
    )
    def get(self, request, teacher_id):
        slots = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').filter(teacher_id=teacher_id).order_by('id')
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response({
            'count': len(serializer.data),
            'next': None,
            'previous': None,
            'results': serializer.data
        })


class ClassTimetableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Class timetable",
        description="Get all timetable slots for a specific class.",
        responses={200: TimetableSlotSerializer(many=True)},
    )
    def get(self, request, class_id):
        slots = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').filter(class_obj_id=class_id).order_by('id')
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response({
            'count': len(serializer.data),
            'next': None,
            'previous': None,
            'results': serializer.data
        })
