from rest_framework import serializers
from class_sessions.models import Session, SessionAttendance
from timetable.serializers import TimetableSlotSerializer, ClassSerializer
from people.serializers import TeacherSerializer, StudentSerializer

class SessionSerializer(serializers.ModelSerializer):
    timetable_slot = TimetableSlotSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    class_obj = ClassSerializer(read_only=True)
    
    class Meta:
        model = Session
        fields = [
            'id', 'timetable_slot', 'teacher', 'class_obj',
            'session_date', 'status', 'paid', 'payslip'
        ]

class SessionAttendanceSerializer(serializers.ModelSerializer):
    session = SessionSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    
    class Meta:
        model = SessionAttendance
        fields = ['id', 'session', 'student', 'status']