from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from people.models import Subject, Teacher, Student, Staff, AuditLog, SCHOOL_CHOICES

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    """Read-safe user shape for /me and nested contexts (SEC-L1)."""
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
            'staff_profile_id',
            'role',
            'is_active',
            'username',
            'email',
        ]

    def validate_role(self, value):
        from people.roles import ROLE_RANK
        if value not in ROLE_RANK:
            raise serializers.ValidationError(f'Invalid role: {value}')
        return value


class AdminUserSerializer(UserSerializer):
    """Admin-only write surface for role / is_active (SEC-L1)."""

    class Meta(UserSerializer.Meta):
        read_only_fields = [
            'id',
            'clerk_id',
            'teacher_profile_id',
            'student_profile_id',
            'staff_profile_id',
        ]

class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ['id', 'name']

class TeacherSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')
    school_code = serializers.ChoiceField(choices=SCHOOL_CHOICES, required=True)
    
    class Meta:
        model = Teacher
        fields = ['id', 'unique_code', 'name', 'employment_type', 'contact', 'join_date', 'school_code', 'user_id']
        read_only_fields = ['unique_code']

class StudentSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')
    school_code = serializers.ChoiceField(choices=SCHOOL_CHOICES, required=True)
    class_labels = serializers.SerializerMethodField()
    class_ids = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id', 'unique_code', 'exam_candidate_number', 'name', 'dob', 'enrollment_date',
            'contact', 'school_code', 'user_id', 'check_in_token', 'check_in_token_active',
            'class_labels', 'class_ids',
        ]
        read_only_fields = [
            'unique_code', 'check_in_token', 'check_in_token_active',
            'class_labels', 'class_ids',
        ]

    def _enrollments(self, obj):
        # Prefetched as enrolled_classes → class_obj when list uses prefetch_related.
        return list(obj.enrolled_classes.all())

    def get_class_ids(self, obj):
        return [e.class_obj_id for e in self._enrollments(obj) if e.class_obj_id]

    def get_class_labels(self, obj):
        level_labels = {
            'IAL': 'IAL (A Level)',
            'IG': 'IGCSE',
            'Year1': 'Year 1',
            'Year2': 'Year 2',
            'Year3': 'Year 3',
            'Year4': 'Year 4',
            'Year5': 'Year 5',
            'Year6': 'Year 6',
            'Year7': 'Year 7',
            'Year8': 'Year 8',
            'Year9': 'Year 9',
        }
        labels = []
        for e in self._enrollments(obj):
            cls = e.class_obj
            if not cls:
                continue
            level = level_labels.get(cls.education_level, cls.education_level)
            stream = f"{cls.cohort_identifier}{cls.cohort_sub_category or ''}".strip()
            labels.append(f"{level} · {stream}" if stream else level)
        return labels

    def to_representation(self, instance):
        """
        SEC-H2: check_in_token is omitted unless the view explicitly opts in
        (student detail retrieve / dedicated token actions). Active flag may
        still appear for staff UI badges when privileged.
        """
        representation = super().to_representation(instance)
        request = self.context.get('request')
        include_token = bool(self.context.get('include_check_in_token'))

        is_owner = False
        is_privileged = False
        if request and request.user and request.user.is_authenticated:
            user = request.user
            is_owner = (user.role == 'student' and instance.user_id == user.id)
            is_privileged = user.role in ('admin', 'staff')

        if not include_token or not (is_owner or is_privileged):
            representation.pop('check_in_token', None)

        if not (is_owner or is_privileged):
            representation.pop('check_in_token_active', None)

        return representation

class StaffSerializer(serializers.ModelSerializer):
    user_id = serializers.PrimaryKeyRelatedField(read_only=True, source='user.id')
    school_code = serializers.ChoiceField(choices=SCHOOL_CHOICES, required=True)
    
    class Meta:
        model = Staff
        fields = ['id', 'unique_code', 'name', 'contact', 'join_date', 'school_code', 'user_id']
        read_only_fields = ['unique_code']


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()
    
    class Meta:
        model = AuditLog
        fields = ['id', 'user', 'user_email', 'model_name', 'record_id', 'action', 'field_name', 'old_value', 'new_value', 'timestamp']
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_user_email(self, obj):
        return obj.user.email if obj.user else None
