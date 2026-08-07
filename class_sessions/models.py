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
    
    timetable_slot = models.ForeignKey(TimetableSlot, on_delete=models.PROTECT, related_name='sessions')
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='sessions')
    actual_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name='sessions_taught',
        null=True,
        blank=True,
        help_text='Who actually taught. Null means taught as assigned (or not yet run). Set when a substitute covers.',
    )
    class_obj = models.ForeignKey(Class, on_delete=models.PROTECT, related_name='sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    
    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError('end_time must be after start_time.')
        if self.actual_teacher_id and self.teacher_id and self.actual_teacher_id == self.teacher_id:
            # Same as assigned is redundant; store as null (taught as assigned).
            self.actual_teacher = None
    
    @classmethod
    def from_db(cls, db, field_names, values):
        """Track loaded status so audit signals skip an extra SELECT (PERF-M1)."""
        instance = super().from_db(db, field_names, values)
        instance._old_status = instance.status
        return instance

    def save(self, *args, **kwargs):
        # BUG-M1: skip full_clean on status-only updates (bulk status / patch paths)
        update_fields = kwargs.get('update_fields')
        if update_fields is None or not set(update_fields).issubset({'status'}):
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
            models.Index(fields=['class_obj', 'start_time'], name='idx_session_class_start'),
            models.Index(fields=['teacher', 'start_time'], name='idx_session_teacher_start'),
            models.Index(fields=['start_time']),
            models.Index(fields=['status']),
        ]
        
    def __str__(self):
        return f"Session with {self.teacher.name} on {self.start_time:%d/%m/%y %H:%M} ({self.get_status_display()})"


class SessionAttendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ]
    
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendances')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='absent')
    auto_marked_by_checkin = models.ForeignKey(
        'CheckIn',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auto_marked_session_attendances',
        editable=False,
    )
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['session', 'student'],
                name='unique_attendance_per_session_student'
            ),
        ]
        indexes = [
            models.Index(fields=['session', 'student'], name='idx_attendance_sess_stud'),
            models.Index(fields=['student']),
            models.Index(fields=['session', 'status']),
        ]
        
    def __str__(self):
        return f"{self.student.name} - {self.get_status_display()}"


class AdHocSession(models.Model):
    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name='adhoc_sessions')
    actual_teacher = models.ForeignKey(
        Teacher,
        on_delete=models.PROTECT,
        related_name='adhoc_sessions_taught',
        null=True,
        blank=True,
        help_text='Who actually taught. Null means taught as assigned. Set when a substitute covers.',
    )
    subject = models.ForeignKey('people.Subject', on_delete=models.PROTECT, related_name='adhoc_sessions')
    date = models.DateField(db_index=True)
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(max_length=20, choices=Session.STATUS_CHOICES, default='scheduled')

    def clean(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValidationError('end_time must be after start_time.')
        if self.actual_teacher_id and self.teacher_id and self.actual_teacher_id == self.teacher_id:
            self.actual_teacher = None

    @classmethod
    def from_db(cls, db, field_names, values):
        """Track loaded status so audit signals skip an extra SELECT (PERF-M1)."""
        instance = super().from_db(db, field_names, values)
        instance._old_status = instance.status
        return instance

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        if update_fields is None or not set(update_fields).issubset({'status'}):
            self.full_clean()
        super().save(*args, **kwargs)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'subject', 'date', 'start_time'],
                name='unique_adhoc_session_per_start'
            ),
        ]
        indexes = [
            models.Index(fields=['teacher', 'date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"Ad-Hoc: {self.subject.name} with {self.teacher.name} on {self.date:%d/%m/%y} ({self.get_status_display()})"


class AdHocSessionAttendance(models.Model):
    ad_hoc_session = models.ForeignKey(AdHocSession, on_delete=models.CASCADE, related_name='attendances')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='adhoc_attendances')
    status = models.CharField(max_length=20, choices=SessionAttendance.STATUS_CHOICES, default='absent')
    auto_marked_by_checkin = models.ForeignKey(
        'CheckIn',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='auto_marked_adhoc_attendances',
        editable=False,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['ad_hoc_session', 'student'],
                name='unique_attendance_per_adhoc_session_student'
            ),
        ]
        indexes = [
            models.Index(fields=['student']),
            models.Index(fields=['ad_hoc_session', 'status']),
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
        if self.timestamp:
            self.date = timezone.localdate(self.timestamp)
        elif not self.date:
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
