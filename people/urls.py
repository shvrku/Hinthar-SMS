from django.urls import path, include
from rest_framework.routers import DefaultRouter
from people.views import MeView, SubjectViewSet, TeacherViewSet, StudentViewSet, StaffViewSet

router = DefaultRouter()
router.register(r'subjects', SubjectViewSet)
router.register(r'teachers', TeacherViewSet)
router.register(r'students', StudentViewSet)
router.register(r'staff', StaffViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('me/', MeView.as_view(), name='me'),
]
