from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from django.db import transaction
from django.db.models import Q
from timetable.models import Class, ClassStudent, TimetableSlot, TimetableStudent
from timetable.serializers import (
    ClassSerializer, ClassStudentSerializer, TimetableSlotSerializer, TimetableStudentSerializer
)
from people.permissions import IsAdmin, IsStaffOrAdmin, IsAdminOrReadOnlyAuthenticated, IsStaffOrAdminOrReadOnlyAuthenticated

class ClassViewSet(ModelViewSet):
    queryset = Class.objects.all()
    serializer_class = ClassSerializer
    permission_classes = [IsStaffOrAdminOrReadOnlyAuthenticated]

class ClassStudentViewSet(ModelViewSet):
    queryset = ClassStudent.objects.select_related('class_obj', 'student__user').all()
    serializer_class = ClassStudentSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]

class TimetableSlotViewSet(ModelViewSet):
    queryset = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').all()
    serializer_class = TimetableSlotSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]
    
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

class TimetableStudentViewSet(ModelViewSet):
    queryset = TimetableStudent.objects.select_related(
        'timetable_slot__class_obj', 'timetable_slot__subject',
        'timetable_slot__teacher__user', 'student__user',
    ).all()
    serializer_class = TimetableStudentSerializer
    permission_classes = [IsAdminOrReadOnlyAuthenticated]

class TeacherTimetableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Teacher timetable",
        description="Get all timetable slots for a specific teacher.",
        responses=TimetableSlotSerializer(many=True),
    )
    def get(self, request, teacher_id):
        slots = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').filter(teacher_id=teacher_id)
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response(serializer.data)

class ClassTimetableView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Class timetable",
        description="Get all timetable slots for a specific class.",
        responses={200: TimetableSlotSerializer(many=True)},
    )
    def get(self, request, class_id):
        slots = TimetableSlot.objects.select_related('class_obj', 'subject', 'teacher__user').filter(class_obj_id=class_id)
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response(serializer.data)
