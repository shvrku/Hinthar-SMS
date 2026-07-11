from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('teacher', 'Teacher'),
        ('student', 'Student'),
    ]
    
    clerk_id = models.CharField(max_length=255, unique=True, db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    
    # Relationships to the domain entities
    teacher = models.OneToOneField(
        'Teacher', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='user_profile'
    )
    student = models.OneToOneField(
        'Student', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='user_profile'
    )

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
    default_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # hourly or per session rate
    contact = models.TextField(blank=True, null=True) # JSON or descriptive text
    bank_details = models.TextField(blank=True, null=True) # payment routing information

    def __str__(self):
        return f"{self.name} ({self.get_employment_type_display()})"


class Student(models.Model):
    name = models.CharField(max_length=255)
    dob = models.DateField(null=True, blank=True)
    enrollment_date = models.DateField(auto_now_add=True)
    contact = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
