from django.contrib import admin
from class_sessions.models import Session, SessionAttendance, CheckIn


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'start_time', 'end_time', 'status')
    list_filter = ('status', 'start_time')
    search_fields = ('teacher__name',)
    date_hierarchy = 'start_time'


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'student', 'status')
    list_filter = ('status', 'session')
    search_fields = ('student__name',)


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'timestamp', 'check_in_type', 'checked_by')
    list_filter = ('check_in_type', 'timestamp')
    search_fields = ('student__name',)
    date_hierarchy = 'timestamp'
