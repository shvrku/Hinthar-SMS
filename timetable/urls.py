from django.urls import path, include
from rest_framework.routers import DefaultRouter
from timetable import views

router = DefaultRouter()
router.register(r'classes', views.ClassViewSet)
router.register(r'class-students', views.ClassStudentViewSet)
router.register(r'timetable-slots', views.TimetableSlotViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('timetable/teacher/<int:teacher_id>/', views.TeacherTimetableView.as_view(), name='teacher-timetable'),
    path('timetable/class/<int:class_id>/', views.ClassTimetableView.as_view(), name='class-timetable'),
]