from django.db import models
from django.core.exceptions import ValidationError
from people.models import Teacher, Student, Subject


class Class(models.Model):
    """
    Represents a school Cohort (e.g. IG K1, IAL K2).
    - education_level: IG / IAL / Year1..Year9
    - cohort (stored in cohort_identifier column): single letter e.g. K, A, B
    - sub_cohort_category (stored in cohort_sub_category column): number/code e.g. 1, 2 (nullable)
    - full_cohort_identifier / str(self): e.g. "IG K1", "IAL K2"

    NOTE: Keeping the Django model name 'Class' (with alias Cohort = Class) preserves
    migration graph and FK references across apps while exposing explicit Cohort terminology.
    """
    EDUCATION_LEVEL_CHOICES = [
        ('IAL', 'IAL'),
        ('IG', 'IG'),
        ('Year1', 'Year 1'),
        ('Year2', 'Year 2'),
        ('Year3', 'Year 3'),
        ('Year4', 'Year 4'),
        ('Year5', 'Year 5'),
        ('Year6', 'Year 6'),
        ('Year7', 'Year 7'),
        ('Year8', 'Year 8'),
        ('Year9', 'Year 9'),
    ]
    
    education_level = models.CharField(max_length=20, choices=EDUCATION_LEVEL_CHOICES)
    cohort_identifier = models.CharField(max_length=1)  # single letter, e.g. A, K, L
    cohort_sub_category = models.CharField(max_length=10, null=True, blank=True)  # e.g. 1, 2, 2A, 2B, 4

    def __init__(self, *args, **kwargs):
        if 'cohort' in kwargs and 'cohort_identifier' not in kwargs:
            kwargs['cohort_identifier'] = kwargs.pop('cohort')
        elif 'cohort' in kwargs:
            kwargs.pop('cohort')
        if 'sub_cohort_category' in kwargs and 'cohort_sub_category' not in kwargs:
            kwargs['cohort_sub_category'] = kwargs.pop('sub_cohort_category')
        elif 'sub_cohort_category' in kwargs:
            kwargs.pop('sub_cohort_category')
        super().__init__(*args, **kwargs)

    @property
    def cohort(self) -> str:
        """Single-letter cohort code (e.g. K, A, B)."""
        return self.cohort_identifier

    @cohort.setter
    def cohort(self, value: str):
        self.cohort_identifier = value

    @property
    def sub_cohort_category(self):
        """Nullable sub-cohort number/category (e.g. 1, 2)."""
        return self.cohort_sub_category

    @sub_cohort_category.setter
    def sub_cohort_category(self, value):
        self.cohort_sub_category = value

    @property
    def full_cohort_identifier(self) -> str:
        """Combined Cohort Identifier, e.g. 'IG K1' or 'IAL K'."""
        return str(self)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['education_level', 'cohort_identifier', 'cohort_sub_category'],
                name='unique_class_per_level_cohort'
            ),
        ]
        verbose_name_plural = 'Classes'
        
    def __str__(self):
        if self.cohort_sub_category:
            return f"{self.education_level} {self.cohort_identifier}{self.cohort_sub_category}"
        return f"{self.education_level} {self.cohort_identifier}"


# Domain alias: Cohort
Cohort = Class


class Course(models.Model):
    """
    Represents a specific Subject offered within a specific Cohort (e.g. 'IG K1 — Mathematics').
    Students enroll into Courses (either from their Primary Cohort or across other Cohorts).
    """
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='courses')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='courses')
    default_teacher = models.ForeignKey(
        Teacher, on_delete=models.SET_NULL, null=True, blank=True, related_name='courses'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['class_obj', 'subject'],
                name='unique_course_per_cohort_subject'
            ),
        ]
        indexes = [
            models.Index(fields=['class_obj', 'subject'], name='idx_course_cohort_subj'),
        ]

    @property
    def cohort(self) -> Class:
        return self.class_obj

    @property
    def cohort_identifier(self) -> str:
        return str(self.class_obj)

    @property
    def course_label(self) -> str:
        return f"{self.class_obj} — {self.subject.name}"

    def __str__(self):
        return f"{self.class_obj} — {self.subject.name}"


class ClassStudent(models.Model):
    """
    Tracks a student's single Primary Cohort assignment.
    Additional course enrollments in other cohorts are stored in StudentSubjectEnrollment.
    """
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='class_students')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrolled_classes')
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['class_obj', 'student'],
                name='unique_student_per_class'
            ),
            models.UniqueConstraint(
                fields=['student'],
                name='unique_primary_cohort_per_student'
            ),
        ]
        indexes = [
            models.Index(fields=['class_obj', 'student'], name='idx_class_student_rel'),
        ]

    def __str__(self):
        return f"{self.student.name} in {self.class_obj}"


class StudentSubjectEnrollment(models.Model):
    """
    Course Enrollment table: tracks a student's enrollment in a specific Course
    (a Cohort's specific Subject).
    - status='enrolled': student attends this Course (in their Primary Cohort or another Cohort).
    - status='dropped': student has opted out of this specific Course within their Primary Cohort.
    """
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('dropped', 'Dropped'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='cross_subject_enrollments')
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='cross_subject_enrollments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='cross_student_enrollments')
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, null=True, blank=True, related_name='enrollments'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'class_obj', 'subject'],
                name='unique_student_class_subject_enrollment'
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'class_obj', 'subject'], name='idx_stud_cls_subj_rel'),
            models.Index(fields=['class_obj', 'subject'], name='idx_cls_subj_rel'),
        ]

    def save(self, *args, **kwargs):
        if self.course_id and (not self.class_obj_id or not self.subject_id):
            self.class_obj_id = self.course.class_obj_id
            self.subject_id = self.course.subject_id
        elif self.class_obj_id and self.subject_id and not self.course_id:
            course_obj, _ = Course.objects.get_or_create(
                class_obj_id=self.class_obj_id,
                subject_id=self.subject_id,
            )
            self.course = course_obj
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student.name} -> {self.subject.name} in {self.class_obj} ({self.status})"


# Domain alias: CourseEnrollment
CourseEnrollment = StudentSubjectEnrollment


class TimetableSlot(models.Model):
    DAY_CHOICES = [
        (0, 'Monday'),
        (1, 'Tuesday'),
        (2, 'Wednesday'),
        (3, 'Thursday'),
        (4, 'Friday'),
        (5, 'Saturday'),
        (6, 'Sunday'),
    ]
    
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='timetable_slots')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='timetable_slots')
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, null=True, blank=True, related_name='timetable_slots'
    )
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='timetable_slots')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=100, blank=True, null=True)

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError('end_time must be after start_time.')

    def save(self, *args, **kwargs):
        if self.course_id and (not self.class_obj_id or not self.subject_id):
            self.class_obj_id = self.course.class_obj_id
            self.subject_id = self.course.subject_id
        # Skip full_clean when only non-time fields change (BUG-M1)
        update_fields = kwargs.get('update_fields')
        if update_fields is None or {'start_time', 'end_time', 'day_of_week'} & set(update_fields):
            self.full_clean()
        if self.class_obj_id and self.subject_id and not self.course_id:
            course_obj, _ = Course.objects.get_or_create(
                class_obj_id=self.class_obj_id,
                subject_id=self.subject_id,
                defaults={'default_teacher_id': self.teacher_id},
            )
            self.course = course_obj
            if update_fields is not None:
                kwargs['update_fields'] = list(set(update_fields) | {'course'})
        super().save(*args, **kwargs)
    
    class Meta:
        indexes = [
            models.Index(fields=['teacher', 'day_of_week']),
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.teacher.name} ({self.get_day_of_week_display()} {self.start_time}-{self.end_time})"
