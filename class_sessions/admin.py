from django.contrib import admin
from class_sessions.models import Session, SessionAttendance


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'teacher', 'session_date', 'status', 'paid')
    list_filter = ('status', 'paid', 'session_date')
    search_fields = ('teacher__name',)
    date_hierarchy = 'session_date'


@admin.register(SessionAttendance)
class SessionAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'student', 'status')
    list_filter = ('status', 'session')
    search_fields = ('student__name',)

