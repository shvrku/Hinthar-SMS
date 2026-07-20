from django.contrib import admin
from timetable.models import Class, ClassStudent, TimetableSlot


@admin.register(Class)
class ClassAdmin(admin.ModelAdmin):
    list_display = ('id', 'education_level', 'cohort_identifier', 'cohort_sub_category')
    list_filter = ('education_level', 'cohort_identifier')
    search_fields = ('education_level', 'cohort_identifier')


@admin.register(ClassStudent)
class ClassStudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'class_obj', 'student')
    list_filter = ('class_obj',)


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject', 'teacher', 'day_of_week', 'start_time', 'end_time', 'room')
    list_filter = ('day_of_week', 'subject', 'teacher')

