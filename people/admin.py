from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from people.models import User, Subject, Teacher, Student, Staff

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Clerk Identity', {'fields': ('clerk_id', 'role')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Clerk Identity', {'fields': ('clerk_id', 'role')}),
    )
    list_display = ('username', 'email', 'role', 'clerk_id', 'is_staff')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'clerk_id')


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'employment_type', 'default_rate', 'user')
    list_filter = ('employment_type',)
    search_fields = ('name', 'contact')
    raw_id_fields = ('user',)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'dob', 'enrollment_date', 'user')
    list_filter = ('enrollment_date',)
    search_fields = ('name', 'contact')
    raw_id_fields = ('user',)


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user')
    search_fields = ('name', 'contact')
    raw_id_fields = ('user',)
