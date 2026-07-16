from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from people.models import Teacher, Student
from timetable.models import TimetableSlot, Class


class Session(models.Model):
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]
    
    timetable_slot = models.ForeignKey(TimetableSlot, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='sessions')
    class_obj = models.ForeignKey(Class, on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    paid = models.BooleanField(default=False)
    payslip = models.ForeignKey('payroll.Payslip', on_delete=models.SET_NULL, null=True, blank=True, related_name='sessions')
    
    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError('end_time must be after start_time.')
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['timetable_slot', 'start_time'],
                name='unique_session_per_slot_start'
            ),
        ]
        indexes = [
            models.Index(fields=['teacher']),
        ]
        
    def __str__(self):
        return f"Session with {self.teacher.name} on {self.start_time:%d/%m/%y %H:%M} ({self.get_status_display()})"


class SessionAttendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
    ]
    
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'student'],
                name='unique_attendance_per_session_student'
            ),
        ]
        
    def __str__(self):
        return f"{self.student.name} - {self.get_status_display()}"


class CheckIn(models.Model):
    CHECK_IN_TYPES = [
        ('qr', 'QR Code'),
        ('manual', 'Manual'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='check_ins')
    date = models.DateField(db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    check_in_type = models.CharField(max_length=10, choices=CHECK_IN_TYPES, default='qr')
    checked_by = models.ForeignKey(
        'people.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='check_ins_performed'
    )

    def save(self, *args, **kwargs):
        if not self.date:
            self.date = timezone.localdate()
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = 'Check In'
        verbose_name_plural = 'Check Ins'
        db_table = 'check_ins'
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'date'],
                name='unique_student_daily_checkin'
            ),
        ]
        indexes = [
            models.Index(fields=['student', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.student.name} checked in via {self.check_in_type} at {self.timestamp:%d/%m/%y %H:%M:%S}"
