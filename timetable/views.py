from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from timetable.models import Class, ClassStudent, TimetableSlot, TimetableStudent
from timetable.serializers import (
    ClassSerializer, ClassStudentSerializer, TimetableSlotSerializer, TimetableStudentSerializer
)
from people.permissions import IsAdmin, IsOwnerTeacher

class ClassViewSet(ModelViewSet):
    queryset = Class.objects.all()
    serializer_class = ClassSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]

class ClassStudentViewSet(ModelViewSet):
    queryset = ClassStudent.objects.all()
    serializer_class = ClassStudentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]

class TimetableSlotViewSet(ModelViewSet):
    queryset = TimetableSlot.objects.all()
    serializer_class = TimetableSlotSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]
    
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
        day = serializer.validated_data.get('day_of_week')
        start = serializer.validated_data.get('start_time')
        end = serializer.validated_data.get('end_time')
        teacher = serializer.validated_data.get('teacher')
        room = serializer.validated_data.get('room')
        # Only validate overlap if time-related fields are being changed
        if day is not None and start is not None and end is not None and teacher is not None:
            self._validate_no_overlap(
                day=day, start=start, end=end, teacher=teacher, room=room,
                exclude_pk=self.get_object().pk,
            )
        serializer.save()

class TimetableStudentViewSet(ModelViewSet):
    queryset = TimetableStudent.objects.all()
    serializer_class = TimetableStudentSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]

class TeacherTimetableView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, teacher_id):
        slots = TimetableSlot.objects.filter(teacher_id=teacher_id)
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response(serializer.data)

class ClassTimetableView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request, class_id):
        slots = TimetableSlot.objects.filter(class_obj_id=class_id)
        serializer = TimetableSlotSerializer(slots, many=True)
        return Response(serializer.data)
