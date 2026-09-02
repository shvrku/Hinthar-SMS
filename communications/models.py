from django.conf import settings
from django.db import models
from django.utils.text import slugify
import secrets
import string


class Tag(models.Model):
    SCOPE_ANNOUNCEMENT = 'announcement'
    SCOPE_EVENT = 'event'
    SCOPE_CHOICES = [
        (SCOPE_ANNOUNCEMENT, 'Announcement'),
        (SCOPE_EVENT, 'Event'),
    ]

    name = models.CharField(max_length=80)
    slug = models.SlugField(max_length=100, blank=True)
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, default=SCOPE_ANNOUNCEMENT)

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['name', 'scope'], name='unique_tag_name_per_scope'),
            models.UniqueConstraint(fields=['slug', 'scope'], name='unique_tag_slug_per_scope'),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'tag'
            slug = base
            counter = 1
            while Tag.objects.filter(slug=slug, scope=self.scope).exclude(pk=self.pk).exists():
                slug = f'{base}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Announcement(models.Model):
    STATUS_PUBLISHED = 'published'
    STATUS_ARCHIVED = 'archived'
    STATUS_CHOICES = [
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    body = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PUBLISHED)
    is_featured = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='announcements',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='announcements')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_featured', '-is_pinned', '-published_at', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title) or 'announcement'
            slug = base
            counter = 1
            while Announcement.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{counter}'
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Event(models.Model):
    AUDIENCE_INTERNAL = 'internal'
    AUDIENCE_EXTERNAL = 'external'
    AUDIENCE_CHOICES = [
        (AUDIENCE_INTERNAL, 'Internal'),
        (AUDIENCE_EXTERNAL, 'External'),
    ]

    REGISTRATION_INSTANT_WAITLIST = 'instant_waitlist'
    REGISTRATION_APPROVAL = 'approval_required'
    REGISTRATION_MODE_CHOICES = [
        (REGISTRATION_INSTANT_WAITLIST, 'Instant with waitlist'),
        (REGISTRATION_APPROVAL, 'Approval required'),
    ]

    STATUS_PUBLISHED = 'published'
    STATUS_CLOSED = 'closed'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PUBLISHED, 'Published'),
        (STATUS_CLOSED, 'Closed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=280, unique=True, blank=True)
    summary = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)
    audience = models.CharField(max_length=20, choices=AUDIENCE_CHOICES, default=AUDIENCE_INTERNAL)
    registration_mode = models.CharField(
        max_length=30,
        choices=REGISTRATION_MODE_CHOICES,
        default=REGISTRATION_INSTANT_WAITLIST,
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PUBLISHED)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)
    registration_opens_at = models.DateTimeField(null=True, blank=True)
    registration_closes_at = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    cover_image_url = models.URLField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='events_created',
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name='events')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['starts_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            alphabet = string.ascii_lowercase + string.digits
            while True:
                candidate = ''.join(secrets.choice(alphabet) for _ in range(8))
                if not Event.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                    self.slug = candidate
                    break
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class EventRegistration(models.Model):
    STATUS_CONFIRMED = 'confirmed'
    STATUS_WAITLISTED = 'waitlisted'
    STATUS_PENDING = 'pending'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, 'Confirmed'),
        (STATUS_WAITLISTED, 'Waitlisted'),
        (STATUS_PENDING, 'Pending'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='registrations')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='event_registrations',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    staff_note = models.TextField(blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='event_registrations_reviewed',
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['event', 'user'], name='unique_event_registration_per_user'),
        ]
        ordering = ['registered_at']

    def __str__(self):
        return f'{self.user_id} → {self.event_id} ({self.status})'
