from django.db import models
from people.models import Teacher, Student, Subject


class Class(models.Model):
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
    
    class_obj = models.ForeignKey(Class, on_delete=models.CASCADE, related_name='timetable_slots', null=True, blank=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='timetable_slots')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='timetable_slots')
    day_of_week = models.IntegerField(choices=DAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room = models.CharField(max_length=100, blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['teacher', 'day_of_week']),
        ]

    def __str__(self):
        return f"{self.subject.name} - {self.teacher.name} ({self.get_day_of_week_display()} {self.start_time}-{self.end_time})"


class TimetableStudent(models.Model):
    timetable_slot = models.ForeignKey(TimetableSlot, on_delete=models.CASCADE, related_name='timetable_students')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='timetable_slots')
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['timetable_slot', 'student'],
                name='unique_student_per_timetable_slot'
            ),
        ]

    def __str__(self):
        return f"{self.student.name} in {self.timetable_slot}"

