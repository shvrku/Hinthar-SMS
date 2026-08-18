from django.urls import path, include
from rest_framework.routers import DefaultRouter
from people.views import (
    MeView,
    MeStudentView,
    MeAttendanceSummaryView,
    SubjectViewSet,
    TeacherViewSet,
    StudentViewSet,
    StaffViewSet,
    UserViewSet,
    AuditLogViewSet,
)
from people.webhooks import ClerkWebhookView

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
    path('me/student/', MeStudentView.as_view(), name='me-student'),
    path('me/attendance-summary/', MeAttendanceSummaryView.as_view(), name='me-attendance-summary'),
    path('webhooks/clerk/', ClerkWebhookView.as_view(), name='clerk-webhook'),
]
