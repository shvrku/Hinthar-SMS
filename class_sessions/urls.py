from django.urls import path, include
from rest_framework.routers import DefaultRouter
from class_sessions import views

router = DefaultRouter()
router.register(r'sessions', views.SessionViewSet)
router.register(r'session-attendances', views.SessionAttendanceViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('sessions/generate/', views.GenerateSessionsView.as_view(), name='generate-sessions'),
]