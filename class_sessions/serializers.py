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


class SessionAttendanceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing attendance records.
    
    Uses flat fields sourced from select_related to avoid N+1 queries
    and deeply nested serialization on list endpoints.
    """
    session_id = serializers.IntegerField(source='session.id')
    session_date = serializers.DateField(source='session.session_date')
    session_status = serializers.CharField(source='session.status')
    teacher_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    student_id = serializers.IntegerField(source='student.id')
    student_name = serializers.CharField(source='student.name')

    class Meta:
        model = SessionAttendance
        fields = [
            'id', 'status',
            'session_id', 'session_date', 'session_status',
            'teacher_name', 'class_name',
            'student_id', 'student_name',
        ]

    def get_teacher_name(self, obj):
        return obj.session.teacher.name if (obj.session and obj.session.teacher) else None

    def get_class_name(self, obj):
        return obj.session.class_obj.name if (obj.session and obj.session.class_obj) else None