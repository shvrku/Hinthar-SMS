from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from class_sessions.models import Session, SessionAttendance, CheckIn
from timetable.serializers import TimetableSlotSerializer, ClassSerializer
from people.serializers import TeacherSerializer, StudentSerializer

DT_FORMAT = '%d/%m/%y %H:%M:%S'

class SessionSerializer(serializers.ModelSerializer):
    timetable_slot = TimetableSlotSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    class_obj = ClassSerializer(read_only=True)
    start_time = serializers.DateTimeField(format=DT_FORMAT)
    end_time = serializers.DateTimeField(format=DT_FORMAT)
    
    class Meta:
        model = Session
        fields = [
            'id', 'timetable_slot', 'teacher', 'class_obj',
            'start_time', 'end_time', 'status', 'paid'
        ]

class SessionAttendanceSerializer(serializers.ModelSerializer):
    session = SessionSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    
    class Meta:
        model = SessionAttendance
        fields = ['id', 'session', 'student', 'status']


class SessionAttendanceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing attendance records."""
    session_id = serializers.IntegerField(source='session.id')
    session_start_time = serializers.DateTimeField(source='session.start_time', format=DT_FORMAT)
    session_end_time = serializers.DateTimeField(source='session.end_time', format=DT_FORMAT)
    session_status = serializers.CharField(source='session.status')
    teacher_name = serializers.SerializerMethodField()
    class_name = serializers.SerializerMethodField()
    student_id = serializers.IntegerField(source='student.id')
    student_name = serializers.CharField(source='student.name')

    class Meta:
        model = SessionAttendance
        fields = [
            'id', 'status',
            'session_id', 'session_start_time', 'session_end_time', 'session_status',
            'teacher_name', 'class_name',
            'student_id', 'student_name',
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_teacher_name(self, obj):
        return obj.session.teacher.name if (obj.session and obj.session.teacher) else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_class_name(self, obj):
        return obj.session.class_obj.name if (obj.session and obj.session.class_obj) else None


class CheckInSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.name', read_only=True)

    class Meta:
        model = CheckIn
        fields = ['id', 'student', 'student_name', 'date', 'timestamp', 'check_in_type', 'checked_by']
        read_only_fields = ['date', 'timestamp', 'checked_by']
