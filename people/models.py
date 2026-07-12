from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
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
    # Link to user account (optional, student can exist without login)
    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='student_profile'
    )

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
