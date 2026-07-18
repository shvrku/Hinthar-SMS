from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from people.models import Subject, Teacher, Student, Staff, AuditLog

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    teacher_profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source='teacher_profile.id')
    student_profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source='student_profile.id')
    staff_profile_id = serializers.PrimaryKeyRelatedField(read_only=True, source='staff_profile.id')
    
    class Meta:
        model = User
        fields = [
            'id', 
            'username', 
            'email', 
            'role', 
            'clerk_id', 
            'teacher_profile_id', 
            'student_profile_id',
            'staff_profile_id',
            'is_active'
        ]
        read_only_fields = [
            'id', 
            'clerk_id', 
            'teacher_profile_id', 
            'student_profile_id', 
            'staff_profile_id'
        ]

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']

class TeacherSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')
    
    class Meta:
        model = Teacher
        fields = ['id', 'name', 'employment_type', 'default_rate', 'contact', 'bank_details', 'user_id']

class StudentSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')
    
    class Meta:
        model = Student
        fields = ['id', 'name', 'dob', 'enrollment_date', 'contact', 'user_id', 'check_in_token']
        read_only_fields = ['check_in_token']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        request = self.context.get('request')
        if request and request.user and request.user.is_authenticated:
            user = request.user
            is_owner = (user.role == 'student' and instance.user == user)
            is_privileged = user.role in ('terminal', 'admin', 'staff')
            if not (is_owner or is_privileged):
                representation.pop('check_in_token', None)
        else:
            representation.pop('check_in_token', None)
        return representation

class StaffSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')
    
    class Meta:
        model = Staff
        fields = ['id', 'name', 'contact', 'user_id']


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_email', 'model_name', 'record_id', 'action', 'field_name', 'old_value', 'new_value', 'timestamp']
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None
