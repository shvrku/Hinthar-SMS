from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from class_sessions.models import Session, SessionAttendance, CheckIn, AdHocSession, AdHocSessionAttendance
from timetable.serializers import TimetableSlotSerializer, ClassSerializer
from people.serializers import TeacherSerializer, StudentSerializer, SubjectSerializer
from people.models import Teacher, Student, Subject
from timetable.models import Class, TimetableSlot

DT_FORMAT = '%d/%m/%y %H:%M:%S'  # legacy input + human __str__ only; API DateTime output is ISO-8601

class SessionSerializer(serializers.ModelSerializer):
    timetable_slot = TimetableSlotSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    actual_teacher = TeacherSerializer(read_only=True)
    class_obj = ClassSerializer(read_only=True)
    
    teacher_id = serializers.PrimaryKeyRelatedField(
        source='teacher', queryset=Teacher.objects.all()
    )
    actual_teacher_id = serializers.PrimaryKeyRelatedField(
        source='actual_teacher',
        queryset=Teacher.objects.all(),
        allow_null=True,
        required=False,
    )
    class_obj_id = serializers.PrimaryKeyRelatedField(
        source='class_obj', queryset=Class.objects.all()
    )
    timetable_slot_id = serializers.PrimaryKeyRelatedField(
        source='timetable_slot', queryset=TimetableSlot.objects.all()
    )
    
    start_time = serializers.DateTimeField(input_formats=['iso-8601', DT_FORMAT])
    end_time = serializers.DateTimeField(input_formats=['iso-8601', DT_FORMAT])
    
    class Meta:
        model = Session
        fields = [
            'id', 'timetable_slot', 'teacher', 'actual_teacher', 'class_obj',
            'teacher_id', 'actual_teacher_id', 'class_obj_id', 'timetable_slot_id',
            'start_time', 'end_time', 'status'
        ]
        validators = []

    def validate(self, attrs):
        timetable_slot = attrs.get('timetable_slot')
        start_time = attrs.get('start_time')
        
        if timetable_slot and start_time:
            qs = Session.objects.filter(timetable_slot=timetable_slot, start_time=start_time)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({
                    'timetable_slot_id': 'A session already exists for this timetable slot at this start time.'
                })
        return attrs

class SessionAttendanceSerializer(serializers.ModelSerializer):
    session = SessionSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    
    session_id = serializers.PrimaryKeyRelatedField(
        source='session', queryset=Session.objects.all()
    )
    student_id = serializers.PrimaryKeyRelatedField(
        source='student', queryset=Student.objects.all()
    )
    
    class Meta:
        model = SessionAttendance
        fields = ['id', 'session', 'student', 'status', 'session_id', 'student_id']


class SessionAttendanceListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for listing attendance records."""
    session_id = serializers.IntegerField(source='session.id')
    session_start_time = serializers.DateTimeField(source='session.start_time')
    session_end_time = serializers.DateTimeField(source='session.end_time')
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
        return str(obj.session.class_obj) if (obj.session and obj.session.class_obj) else None


class CheckInSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        source='student', queryset=Student.objects.all(), write_only=False
    )
    student_name = serializers.CharField(source='student.name', read_only=True)

    class Meta:
        model = CheckIn
        fields = ['id', 'student', 'student_id', 'student_name', 'date', 'timestamp', 'check_in_type', 'checked_by']
        read_only_fields = ['date', 'timestamp', 'checked_by']


class AdHocSessionSerializer(serializers.ModelSerializer):
    teacher = TeacherSerializer(read_only=True)
    actual_teacher = TeacherSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    
    teacher_id = serializers.PrimaryKeyRelatedField(
        source='teacher', queryset=Teacher.objects.all()
    )
    actual_teacher_id = serializers.PrimaryKeyRelatedField(
        source='actual_teacher',
        queryset=Teacher.objects.all(),
        allow_null=True,
        required=False,
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject', queryset=Subject.objects.all()
    )
    
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    
    class Meta:
        model = AdHocSession
        fields = [
            'id', 'teacher', 'actual_teacher', 'subject',
            'teacher_id', 'actual_teacher_id', 'subject_id',
            'date', 'start_time', 'end_time', 'status'
        ]

    def validate(self, attrs):
        teacher = attrs.get('teacher')
        subject = attrs.get('subject')
        date = attrs.get('date')
        start_time = attrs.get('start_time')
        
        if teacher and subject and date and start_time:
            qs = AdHocSession.objects.filter(
                teacher=teacher, subject=subject, date=date, start_time=start_time
            )
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "An ad-hoc session already exists for this teacher, subject, date, and start time."
                )
        return attrs

class AdHocSessionAttendanceSerializer(serializers.ModelSerializer):
    ad_hoc_session = AdHocSessionSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    
    ad_hoc_session_id = serializers.PrimaryKeyRelatedField(
        source='ad_hoc_session', queryset=AdHocSession.objects.all()
    )
    student_id = serializers.PrimaryKeyRelatedField(
        source='student', queryset=Student.objects.all()
    )
    
    class Meta:
        model = AdHocSessionAttendance
        fields = ['id', 'ad_hoc_session', 'student', 'status', 'ad_hoc_session_id', 'student_id']
