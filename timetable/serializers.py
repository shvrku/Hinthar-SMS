from rest_framework import serializers
from timetable.models import Class, Course, ClassStudent, StudentSubjectEnrollment, TimetableSlot
from people.serializers import SubjectSerializer, TeacherSerializer, StudentSerializer
from people.models import Student, Subject, Teacher


class ClassSerializer(serializers.ModelSerializer):
    cohort = serializers.CharField(read_only=True)
    sub_cohort_category = serializers.CharField(read_only=True, allow_null=True)
    full_cohort_identifier = serializers.CharField(read_only=True)

    class Meta:
        model = Class
        fields = [
            'id',
            'education_level',
            'cohort_identifier',
            'cohort_sub_category',
            'cohort',
            'sub_cohort_category',
            'full_cohort_identifier',
        ]
        extra_kwargs = {
            'cohort_identifier': {'required': False},
            'cohort_sub_category': {'required': False, 'allow_null': True, 'allow_blank': True},
        }

    def to_internal_value(self, data):
        if isinstance(data, dict):
            mutable = dict(data)
            if 'cohort' in mutable and 'cohort_identifier' not in mutable:
                mutable['cohort_identifier'] = mutable['cohort']
            if 'sub_cohort_category' in mutable and 'cohort_sub_category' not in mutable:
                mutable['cohort_sub_category'] = mutable['sub_cohort_category']
            data = mutable
        ret = super().to_internal_value(data)
        if not ret.get('cohort_identifier') and not (self.instance and self.instance.cohort_identifier):
            raise serializers.ValidationError({'cohort_identifier': 'This field is required.'})
        return ret


CohortSerializer = ClassSerializer


class CourseSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    cohort = ClassSerializer(source='class_obj', read_only=True)
    subject = SubjectSerializer(read_only=True)
    default_teacher = TeacherSerializer(read_only=True)

    class_obj_id = serializers.PrimaryKeyRelatedField(
        source='class_obj', queryset=Class.objects.all(), required=False
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject', queryset=Subject.objects.all()
    )
    default_teacher_id = serializers.PrimaryKeyRelatedField(
        source='default_teacher', queryset=Teacher.objects.all(), required=False, allow_null=True
    )
    cohort_identifier = serializers.CharField(read_only=True)
    course_label = serializers.CharField(read_only=True)

    class Meta:
        model = Course
        fields = [
            'id',
            'class_obj',
            'cohort',
            'subject',
            'default_teacher',
            'class_obj_id',
            'subject_id',
            'default_teacher_id',
            'cohort_identifier',
            'course_label',
        ]
        validators = []

    def to_internal_value(self, data):
        if isinstance(data, dict):
            mutable = dict(data)
            if 'cohort_id' in mutable and 'class_obj_id' not in mutable:
                mutable['class_obj_id'] = mutable['cohort_id']
            data = mutable
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs.get('class_obj') and not (self.instance and self.instance.class_obj_id):
            raise serializers.ValidationError({'class_obj_id': 'Cohort / class_obj_id is required.'})
        return attrs

    def create(self, validated_data):
        class_obj = validated_data['class_obj']
        subject = validated_data['subject']
        default_teacher = validated_data.get('default_teacher')
        instance, _ = Course.objects.update_or_create(
            class_obj=class_obj,
            subject=subject,
            defaults={'default_teacher': default_teacher},
        )
        return instance


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
        validators = []  # Custom validation in validate() for friendly error messages

    def validate(self, attrs):
        student = attrs.get('student') or getattr(self.instance, 'student', None)
        class_obj = attrs.get('class_obj') or getattr(self.instance, 'class_obj', None)
        if student:
            qs = ClassStudent.objects.select_related('class_obj').filter(student=student)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            existing = qs.first()
            if existing:
                if class_obj and existing.class_obj_id == class_obj.id:
                    raise serializers.ValidationError(
                        {'student_id': f"{student.name} is already assigned to Primary Cohort {existing.class_obj}."}
                    )
                raise serializers.ValidationError(
                    {
                        'student_id': (
                            f"{student.name} already has a Primary Cohort ({existing.class_obj}). "
                            "Students can only have one Primary Cohort — enroll them in additional courses "
                            "via Course Enrollments, or change their Primary Cohort first."
                        )
                    }
                )
        return attrs


class ClassStudentListSerializer(serializers.ModelSerializer):
    """List payload without StudentSerializer class_labels / class_ids (N+1)."""
    class_obj = ClassSerializer(read_only=True)
    student = ClassStudentListStudentSerializer(read_only=True)

    class Meta:
        model = ClassStudent
        fields = ['id', 'class_obj', 'student', 'class_obj_id', 'student_id']
        read_only_fields = fields


class StudentSubjectEnrollmentSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    student = StudentSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    course = CourseSerializer(read_only=True)

    class_obj_id = serializers.PrimaryKeyRelatedField(
        source='class_obj', queryset=Class.objects.all(), required=False
    )
    student_id = serializers.PrimaryKeyRelatedField(
        source='student', queryset=Student.objects.all()
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject', queryset=Subject.objects.all(), required=False
    )
    course_id = serializers.PrimaryKeyRelatedField(
        source='course', queryset=Course.objects.select_related('class_obj', 'subject').all(), required=False
    )
    cohort_identifier = serializers.SerializerMethodField()
    course_label = serializers.SerializerMethodField()

    class Meta:
        model = StudentSubjectEnrollment
        fields = [
            'id',
            'class_obj',
            'student',
            'subject',
            'course',
            'class_obj_id',
            'student_id',
            'subject_id',
            'course_id',
            'status',
            'cohort_identifier',
            'course_label',
        ]
        validators = []  # Handled in validate() to support upsert of dropped/enrolled or course_id

    def get_cohort_identifier(self, obj) -> str:
        return str(obj.class_obj) if obj.class_obj_id else ''

    def get_course_label(self, obj) -> str:
        if obj.class_obj_id and obj.subject_id:
            return f"{obj.class_obj} — {obj.subject.name}"
        return ''

    def validate(self, attrs):
        course = attrs.get('course')
        class_obj = attrs.get('class_obj')
        subject = attrs.get('subject')
        if course and (not class_obj or not subject):
            attrs['class_obj'] = course.class_obj
            attrs['subject'] = course.subject
            class_obj = course.class_obj
            subject = course.subject

        if not self.instance and (not class_obj or not subject):
            raise serializers.ValidationError(
                'Provide either course_id or both class_obj_id and subject_id.'
            )
        return attrs

    def create(self, validated_data):
        student = validated_data['student']
        class_obj = validated_data['class_obj']
        subject = validated_data['subject']
        status_val = validated_data.get('status', 'enrolled')
        course_obj, _ = Course.objects.get_or_create(class_obj=class_obj, subject=subject)
        instance, created = StudentSubjectEnrollment.objects.update_or_create(
            student=student,
            class_obj=class_obj,
            subject=subject,
            defaults={
                'course': course_obj,
                'status': status_val,
            },
        )
        return instance


class StudentSubjectEnrollmentListSerializer(serializers.ModelSerializer):
    """List payload without StudentSerializer heavy nested fields."""
    class_obj = ClassSerializer(read_only=True)
    student = ClassStudentListStudentSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    course_id = serializers.IntegerField(read_only=True)
    cohort_identifier = serializers.SerializerMethodField()
    course_label = serializers.SerializerMethodField()

    class Meta:
        model = StudentSubjectEnrollment
        fields = [
            'id',
            'class_obj',
            'student',
            'subject',
            'class_obj_id',
            'student_id',
            'subject_id',
            'course_id',
            'status',
            'cohort_identifier',
            'course_label',
        ]
        read_only_fields = fields

    def get_cohort_identifier(self, obj) -> str:
        return str(obj.class_obj) if obj.class_obj_id else ''

    def get_course_label(self, obj) -> str:
        if obj.class_obj_id and obj.subject_id:
            return f"{obj.class_obj} — {obj.subject.name}"
        return ''


CourseEnrollmentSerializer = StudentSubjectEnrollmentSerializer
CourseEnrollmentListSerializer = StudentSubjectEnrollmentListSerializer


class TimetableSlotSerializer(serializers.ModelSerializer):
    class_obj = ClassSerializer(read_only=True)
    subject = SubjectSerializer(read_only=True)
    teacher = TeacherSerializer(read_only=True)
    
    class_obj_id = serializers.PrimaryKeyRelatedField(
        source='class_obj', queryset=Class.objects.all(), required=False
    )
    subject_id = serializers.PrimaryKeyRelatedField(
        source='subject', queryset=Subject.objects.all(), required=False
    )
    course_id = serializers.PrimaryKeyRelatedField(
        source='course', queryset=Course.objects.select_related('class_obj', 'subject').all(), required=False, allow_null=True
    )
    teacher_id = serializers.PrimaryKeyRelatedField(
        source='teacher', queryset=Teacher.objects.all()
    )
    cohort_identifier = serializers.SerializerMethodField()
    course_label = serializers.SerializerMethodField()
    
    class Meta:
        model = TimetableSlot
        fields = [
            'id', 'class_obj', 'subject', 'teacher', 
            'class_obj_id', 'subject_id', 'course_id', 'teacher_id',
            'day_of_week', 'start_time', 'end_time', 'room',
            'cohort_identifier', 'course_label',
        ]

    def get_cohort_identifier(self, obj) -> str:
        return str(obj.class_obj) if obj.class_obj_id else ''

    def get_course_label(self, obj) -> str:
        if obj.class_obj_id and obj.subject_id:
            return f"{obj.class_obj} — {obj.subject.name}"
        return ''

    def validate(self, attrs):
        course = attrs.get('course')
        if course:
            if not attrs.get('class_obj'):
                attrs['class_obj'] = course.class_obj
            if not attrs.get('subject'):
                attrs['subject'] = course.subject
        if not self.instance:
            if not attrs.get('class_obj'):
                raise serializers.ValidationError({'class_obj_id': 'This field is required.'})
            if not attrs.get('subject'):
                raise serializers.ValidationError({'subject_id': 'This field is required.'})
        return attrs
