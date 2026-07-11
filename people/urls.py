from django.urls import path
from people.views import MeView

urlpatterns = [
    path('me', MeView.as_view(), name='me'),
]
