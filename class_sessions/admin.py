from django.contrib import admin
from class_sessions.models import Session, SessionAttendance


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'start_time', 'end_time', 'status', 'paid')
    list_filter = ('status', 'paid', 'start_time')
    search_fields = ('teacher__name',)
    date_hierarchy = 'start_time'


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'student', 'status')
    list_filter = ('status', 'session')
    search_fields = ('student__name',)
