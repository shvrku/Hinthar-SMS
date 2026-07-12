from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
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
    
    @transaction.atomic
    def perform_create(self, serializer):
        # TODO: Overlap validation (teacher or room overlap)
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
