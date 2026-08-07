from django.db import models
from django.core.exceptions import ValidationError
from people.models import Teacher, Student, Subject


class Class(models.Model):
    """
    Represents a school cohort/class.
    NOTE: Shadowing the Python builtin name 'class' is intentional to keep API path parity 
    with next.js dashboard routes (/classes) and avoid complex database migration renames.
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
    cohort_identifier = models.CharField(max_length=1)  # single letter like E, F, G, H, K
    cohort_sub_category = models.CharField(max_length=1, null=True, blank=True)  # stream split like 1, 2, 3
    
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


class ClassStudent(models.Model):
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='class_students')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrolled_classes')
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['class_obj', 'student'],
                name='unique_student_per_class'
            ),
        ]
        indexes = [
            models.Index(fields=['class_obj', 'student'], name='idx_class_student_rel'),
        ]

    def __str__(self):
        return f"{self.student.name} in {self.class_obj}"


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
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='timetable_slots')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=100, blank=True, null=True)

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError('end_time must be after start_time.')

    def save(self, *args, **kwargs):
        # Skip full_clean when only non-time fields change (BUG-M1)
        update_fields = kwargs.get('update_fields')
        if update_fields is None or {'start_time', 'end_time', 'day_of_week'} & set(update_fields):
            self.full_clean()
        super().save(*args, **kwargs)
    
    class Meta:
        indexes = [
            models.Index(fields=['teacher', 'day_of_week']),
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.teacher.name} ({self.get_day_of_week_display()} {self.start_time}-{self.end_time})"

