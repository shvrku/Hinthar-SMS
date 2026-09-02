from django.contrib import admin

from communications.models import Announcement, Event, EventRegistration, Tag

admin.site.register(Tag)
admin.site.register(Announcement)
admin.site.register(Event)
admin.site.register(EventRegistration)
