from rest_framework import serializers
from timetable.models import Class, ClassStudent, TimetableSlot, TimetableStudent
from people.serializers import SubjectSerializer, TeacherSerializer, StudentSerializer

class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ['id', 'education_level', 'cohort_identifier', 'cohort_sub_category']

class ClassStudentSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    
    class Meta:
        model = ClassStudent
        fields = ['id', 'class_obj', 'student']

class TimetableSlotSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    
    class Meta:
        model = TimetableSlot
        fields = [
            'id', 'class_obj', 'subject', 'teacher', 
            'day_of_week', 'start_time', 'end_time', 'room'
        ]

class TimetableStudentSerializer(serializers.ModelSerializer):
    timetable_slot = TimetableSlotSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    
    class Meta:
        model = TimetableStudent
        fields = ['id', 'timetable_slot', 'student']