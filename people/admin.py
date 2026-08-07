from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from people.models import User, Subject, Teacher, Student, Staff, AuditLog

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Authorization', {'fields': ('role', 'clerk_id')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Authorization', {'fields': ('role', 'clerk_id')}),
    )
    list_display = ('username', 'email', 'role', 'is_staff', 'clerk_id')
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active')
    search_fields = ('username', 'email', 'clerk_id')
    list_editable = ('role',)


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('id', 'unique_code', 'name', 'employment_type', 'join_date', 'school_code', 'user')
    list_filter = ('employment_type', 'school_code')
    search_fields = ('unique_code', 'name', 'contact')
    raw_id_fields = ('user',)
    readonly_fields = ('unique_code',)


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'unique_code', 'exam_candidate_number', 'name', 'dob', 'enrollment_date', 'school_code', 'user', 'check_in_token')
    list_filter = ('enrollment_date', 'school_code')
    search_fields = ('unique_code', 'exam_candidate_number', 'name', 'contact', 'check_in_token')
    raw_id_fields = ('user',)
    readonly_fields = ('unique_code', 'check_in_token')


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ('id', 'unique_code', 'name', 'join_date', 'school_code', 'user')
    list_filter = ('school_code',)
    search_fields = ('unique_code', 'name', 'contact')
    raw_id_fields = ('user',)
    readonly_fields = ('unique_code',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'model_name', 'record_id', 'action', 'field_name', 'user')
    list_filter = ('action', 'model_name', 'timestamp')
    search_fields = ('record_id', 'model_name', 'field_name')
    date_hierarchy = 'timestamp'
    readonly_fields = ('user', 'model_name', 'record_id', 'action', 'field_name', 'old_value', 'new_value', 'timestamp')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
