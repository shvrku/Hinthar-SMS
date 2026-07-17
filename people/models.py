import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
        ('terminal', 'Terminal'),
    ]
    
    clerk_id = models.CharField(max_length=255, unique=True, db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')

    def __str__(self):
        return f"{self.username} ({self.role})"


class Subject(models.Model):
    name = models.CharField(max_length=255, unique=True)

    def __str__(self):
        return self.name


class Teacher(models.Model):
    EMPLOYMENT_TYPES = [
        ('full_time', 'Full Time'),
        ('tutor', 'Tutor'),
    ]
    
    name = models.CharField(max_length=255)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_TYPES, default='tutor')
    default_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    contact = models.TextField(blank=True, null=True)
    bank_details = models.TextField(blank=True, null=True)
    # Link to user account (optional, teacher can exist without login)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teacher_profile'
    )

    def __str__(self):
        return f"{self.name} ({self.get_employment_type_display()})"


class Student(models.Model):
    name = models.CharField(max_length=255)
    dob = models.DateField(null=True, blank=True)
    enrollment_date = models.DateField(auto_now_add=True)
    contact = models.TextField(blank=True, null=True)
    check_in_token = models.CharField(max_length=64, unique=True, blank=True, editable=False)
    # Link to user account (optional, student can exist without login)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_profile'
    )

    def save(self, *args, **kwargs):
        if not self.check_in_token:
            self.check_in_token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def regenerate_check_in_token(self):
        self.check_in_token = secrets.token_urlsafe(32)
        self.save(update_fields=['check_in_token'])

    def __str__(self):
        return self.name


class Staff(models.Model):
    name = models.CharField(max_length=255)
    contact = models.TextField(blank=True, null=True)
    # Link to user account (optional, staff can exist without login)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='staff_profile'
    )

    def __str__(self):
        return self.name


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs'
    )
    model_name = models.CharField(max_length=255, db_index=True)
    record_id = models.CharField(max_length=255, db_index=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    field_name = models.CharField(max_length=255, null=True, blank=True)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        indexes = [
            models.Index(fields=['model_name', 'record_id']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} {self.model_name}#{self.record_id} by {self.user or 'unknown'} at {self.timestamp}"
