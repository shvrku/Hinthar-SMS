from rest_framework import serializers
from timetable.models import Class, ClassStudent, TimetableSlot
from people.serializers import SubjectSerializer, TeacherSerializer, StudentSerializer
from people.models import Student, Subject, Teacher

class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ['id', 'education_level', 'cohort_identifier', 'cohort_sub_category']

class ClassStudentSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    class_obj_id = serializers.PrimaryKeyRelatedField(
        source='class_obj', queryset=Class.objects.all()
    )
    student_id = serializers.PrimaryKeyRelatedField(
        source='student', queryset=Student.objects.all()
    )

    class Meta:
        model = ClassStudent
        fields = ['id', 'class_obj', 'student', 'class_obj_id', 'student_id']

class TimetableSlotSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    
    class_obj_id = serializers.PrimaryKeyRelatedField(
        source='class_obj', queryset=Class.objects.all()
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject', queryset=Subject.objects.all()
    )
    teacher_id = serializers.PrimaryKeyRelatedField(
        source='teacher', queryset=Teacher.objects.all()
    )
    
    class Meta:
        model = TimetableSlot
        fields = [
            'id', 'class_obj', 'subject', 'teacher', 
            'class_obj_id', 'subject_id', 'teacher_id',
            'day_of_week', 'start_time', 'end_time', 'room'
        ]