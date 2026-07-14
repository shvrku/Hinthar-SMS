from django.urls import path, include
from rest_framework.routers import DefaultRouter
from people.views import MeView, SubjectViewSet, TeacherViewSet, StudentViewSet, StaffViewSet, UserViewSet, AuditLogViewSet

router = DefaultRouter()
router.register(r'subjects', SubjectViewSet)
router.register(r'teachers', TeacherViewSet)
router.register(r'students', StudentViewSet)
router.register(r'staff', StaffViewSet)
router.register(r'users', UserViewSet)
router.register(r'audit-logs', AuditLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('me/', MeView.as_view(), name='me'),
]
