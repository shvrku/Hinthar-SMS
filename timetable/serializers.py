from rest_framework import serializers
from timetable.models import Class, ClassStudent, TimetableSlot
from people.serializers import SubjectSerializer, TeacherSerializer, StudentSerializer
from people.models import Student, Subject, Teacher

class ClassSerializer(serializers.ModelSerializer):
    class Meta:
        model = Class
        fields = ['id', 'education_level', 'cohort_identifier', 'cohort_sub_category']

class ClassStudentListStudentSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Student
        fields = ['id', 'name', 'unique_code', 'user_id']


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


class ClassStudentListSerializer(serializers.ModelSerializer):
    """List payload without StudentSerializer class_labels / class_ids (N+1)."""
    class_obj = ClassSerializer(read_only=True)
    student = ClassStudentListStudentSerializer(read_only=True)

    class Meta:
        model = ClassStudent
        fields = ['id', 'class_obj', 'student', 'class_obj_id', 'student_id']
        read_only_fields = fields

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