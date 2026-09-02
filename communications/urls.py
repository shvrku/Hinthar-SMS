from django.urls import include, path
from rest_framework.routers import DefaultRouter

from communications.views import AnnouncementViewSet, EventViewSet, TagViewSet

router = DefaultRouter()
router.register(r'tags', TagViewSet, basename='tag')
router.register(r'announcements', AnnouncementViewSet, basename='announcement')
router.register(r'events', EventViewSet, basename='event')

urlpatterns = [
    path('', include(router.urls)),
]
