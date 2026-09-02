from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from communications.models import Announcement, Event, EventRegistration, Tag
from communications.serializers import (
    AnnouncementSerializer,
    EventRegistrationReviewSerializer,
    EventRegistrationSerializer,
    EventSerializer,
    TagSerializer,
)
from people.permissions import IsActiveAuthenticated, IsStaffOrAbove, IsStaffOrAboveOrReadOnly
from people.roles import is_active_account, is_staff_or_above

User = get_user_model()


def _pending_user(user):
    return getattr(user, 'role', None) == 'pending'


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TagSerializer
    permission_classes = [IsActiveAuthenticated]
    lookup_field = 'slug'
    pagination_class = None

    def get_queryset(self):
        qs = Tag.objects.all()
        scope = (self.request.query_params.get('scope') or '').strip()
        if scope in (Tag.SCOPE_ANNOUNCEMENT, Tag.SCOPE_EVENT):
            qs = qs.filter(scope=scope)
        return qs


class AnnouncementViewSet(viewsets.ModelViewSet):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsStaffOrAboveOrReadOnly]
    lookup_field = 'slug'

    def get_queryset(self):
        qs = Announcement.objects.prefetch_related('tags').select_related('author')
        if not is_staff_or_above(self.request.user):
            qs = qs.filter(status=Announcement.STATUS_PUBLISHED)
        tag = (self.request.query_params.get('tag') or '').strip()
        if tag:
            qs = qs.filter(tags__slug=tag)
        q = (self.request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
        return qs.distinct()


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    lookup_field = 'slug'

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        if self.action in ('register', 'cancel_registration', 'my_registrations'):
            return [IsActiveAuthenticated()]
        if self.action in ('registrations', 'review_registration'):
            return [IsStaffOrAbove()]
        return [IsStaffOrAbove()]

    def get_queryset(self):
        qs = Event.objects.prefetch_related('tags', 'registrations').select_related('created_by')
        user = self.request.user
        if is_staff_or_above(user):
            pass
        elif is_active_account(user):
            qs = qs.filter(status=Event.STATUS_PUBLISHED).filter(
                Q(audience=Event.AUDIENCE_EXTERNAL) | Q(audience=Event.AUDIENCE_INTERNAL)
            )
        else:
            qs = qs.filter(status=Event.STATUS_PUBLISHED, audience=Event.AUDIENCE_EXTERNAL)

        tag = (self.request.query_params.get('tag') or '').strip()
        if tag:
            qs = qs.filter(tags__slug=tag)
        q = (self.request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(body__icontains=q))

        when = (self.request.query_params.get('when') or '').strip().lower()
        now = timezone.now()
        if when == 'upcoming':
            qs = qs.filter(starts_at__gte=now).order_by('starts_at')
        elif when == 'past':
            qs = qs.filter(starts_at__lt=now).order_by('-starts_at')
        else:
            qs = qs.order_by('starts_at')

        return qs.distinct()

    def _registration_window_open(self, event):
        now = timezone.now()
        if event.status != Event.STATUS_PUBLISHED:
            return False
        if event.registration_opens_at and now < event.registration_opens_at:
            return False
        if event.registration_closes_at and now > event.registration_closes_at:
            return False
        # Past events cannot accept new registrations once they have ended
        # (or started, when no end time is set).
        cutoff = event.ends_at or event.starts_at
        if cutoff and now >= cutoff:
            return False
        return True

    def _can_register(self, user, event):
        if not is_active_account(user):
            return False, 'Sign in to register.'
        if event.audience == Event.AUDIENCE_INTERNAL and _pending_user(user):
            return False, 'Internal events require a linked school account.'
        if not self._registration_window_open(event):
            now = timezone.now()
            cutoff = event.ends_at or event.starts_at
            if cutoff and now >= cutoff:
                return False, 'Registration is closed for this past event.'
            return False, 'Registration is not open for this event.'
        return True, None

    def _confirmed_count(self, event):
        return event.registrations.filter(status=EventRegistration.STATUS_CONFIRMED).count()

    @action(detail=True, methods=['post'], url_path='register')
    def register(self, request, slug=None):
        event = self.get_object()
        ok, message = self._can_register(request.user, event)
        if not ok:
            return Response({'detail': message}, status=status.HTTP_400_BAD_REQUEST)

        existing = event.registrations.filter(user=request.user).exclude(
            status=EventRegistration.STATUS_CANCELLED
        ).first()
        if existing:
            return Response(
                EventRegistrationSerializer(existing, context={'request': request}).data,
                status=status.HTTP_200_OK,
            )

        if event.registration_mode == Event.REGISTRATION_APPROVAL:
            reg_status = EventRegistration.STATUS_PENDING
        else:
            capacity = event.capacity
            confirmed = self._confirmed_count(event)
            if capacity is not None and confirmed >= capacity:
                reg_status = EventRegistration.STATUS_WAITLISTED
            else:
                reg_status = EventRegistration.STATUS_CONFIRMED

        cancelled = event.registrations.filter(
            user=request.user,
            status=EventRegistration.STATUS_CANCELLED,
        ).first()
        if cancelled:
            cancelled.status = reg_status
            cancelled.staff_note = ''
            cancelled.reviewed_at = None
            cancelled.reviewed_by = None
            cancelled.save(update_fields=['status', 'staff_note', 'reviewed_at', 'reviewed_by'])
            return Response(
                EventRegistrationSerializer(cancelled, context={'request': request}).data,
                status=status.HTTP_200_OK,
            )

        registration = EventRegistration.objects.create(
            event=event,
            user=request.user,
            status=reg_status,
        )
        return Response(
            EventRegistrationSerializer(registration, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['post'], url_path='cancel-registration')
    def cancel_registration(self, request, slug=None):
        event = self.get_object()
        registration = event.registrations.filter(user=request.user).exclude(status=EventRegistration.STATUS_CANCELLED).first()
        if not registration:
            return Response({'detail': 'No active registration found.'}, status=status.HTTP_404_NOT_FOUND)
        registration.status = EventRegistration.STATUS_CANCELLED
        registration.save(update_fields=['status'])
        return Response(EventRegistrationSerializer(registration, context={'request': request}).data)

    @action(detail=False, methods=['get'], url_path='my-registrations')
    def my_registrations(self, request):
        qs = EventRegistration.objects.filter(user=request.user).exclude(
            status=EventRegistration.STATUS_CANCELLED
        ).select_related('event').order_by('-registered_at')
        data = []
        for reg in qs:
            data.append({
                **EventRegistrationSerializer(reg, context={'request': request}).data,
                'event': EventSerializer(reg.event, context={'request': request}).data,
            })
        return Response(data)

    @action(detail=True, methods=['get'], url_path='registrations')
    def registrations(self, request, slug=None):
        event = self.get_object()
        qs = event.registrations.select_related('user').order_by('registered_at')
        return Response(EventRegistrationSerializer(qs, many=True, context={'request': request}).data)

    @action(detail=True, methods=['post'], url_path=r'registrations/(?P<registration_id>[^/.]+)/review')
    def review_registration(self, request, slug=None, registration_id=None):
        event = self.get_object()
        serializer = EventRegistrationReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action_name = serializer.validated_data.get('action')
        next_status = serializer.validated_data.get('status')
        staff_note = serializer.validated_data.get('staff_note', '')

        try:
            registration = event.registrations.get(pk=registration_id)
        except EventRegistration.DoesNotExist:
            return Response({'detail': 'Registration not found.'}, status=status.HTTP_404_NOT_FOUND)

        if next_status:
            target_status = next_status
        elif action_name in ('approve', 'promote'):
            target_status = EventRegistration.STATUS_CONFIRMED
        elif action_name == 'reject':
            target_status = EventRegistration.STATUS_CANCELLED
        else:
            return Response({'detail': 'Invalid review payload.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            if (
                target_status == EventRegistration.STATUS_CONFIRMED
                and registration.status != EventRegistration.STATUS_CONFIRMED
                and event.capacity is not None
                and self._confirmed_count(event) >= event.capacity
            ):
                return Response({'detail': 'Event is at capacity.'}, status=status.HTTP_400_BAD_REQUEST)
            registration.status = target_status
            registration.staff_note = staff_note
            registration.reviewed_at = timezone.now()
            registration.reviewed_by = request.user
            registration.save()

        return Response(EventRegistrationSerializer(registration, context={'request': request}).data)
