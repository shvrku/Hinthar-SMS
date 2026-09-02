from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers

from communications.models import Announcement, Event, EventRegistration, Tag

User = get_user_model()


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'name', 'slug', 'scope']
        read_only_fields = ['slug']


class TagNameField(serializers.ListField):
    child = serializers.CharField(max_length=80)

    def to_representation(self, value):
        return [tag.name for tag in value.all()]


def resolve_tags(tag_names, scope):
    tags = []
    for raw in tag_names or []:
        name = (raw or '').strip()
        if not name:
            continue
        slug = slugify(name) or 'tag'
        tag, _ = Tag.objects.get_or_create(
            name=name,
            scope=scope,
            defaults={'slug': slug},
        )
        tags.append(tag)
    return tags


class AnnouncementSerializer(serializers.ModelSerializer):
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=80),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    tags = TagSerializer(many=True, read_only=True)
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'slug',
            'body',
            'status',
            'is_featured',
            'is_pinned',
            'published_at',
            'author',
            'author_name',
            'tags',
            'tag_names',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['slug', 'author', 'author_name', 'created_at', 'updated_at']

    def get_author_name(self, obj):
        if not obj.author:
            return None
        return obj.author.get_full_name() or obj.author.username

    def validate(self, attrs):
        if attrs.get('is_featured') and attrs.get('status', Announcement.STATUS_PUBLISHED) != Announcement.STATUS_PUBLISHED:
            raise serializers.ValidationError({'is_featured': 'Only published announcements can be featured.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        tag_names = validated_data.pop('tag_names', [])
        if validated_data.get('status') == Announcement.STATUS_PUBLISHED and not validated_data.get('published_at'):
            validated_data['published_at'] = timezone.now()
        validated_data['author'] = self.context['request'].user
        announcement = super().create(validated_data)
        if tag_names:
            announcement.tags.set(resolve_tags(tag_names, Tag.SCOPE_ANNOUNCEMENT))
        if announcement.is_featured and announcement.status == Announcement.STATUS_PUBLISHED:
            Announcement.objects.filter(is_featured=True).exclude(pk=announcement.pk).update(is_featured=False)
        return announcement

    @transaction.atomic
    def update(self, instance, validated_data):
        tag_names = validated_data.pop('tag_names', None)
        status = validated_data.get('status', instance.status)
        if validated_data.get('is_featured') and status != Announcement.STATUS_PUBLISHED:
            raise serializers.ValidationError({'is_featured': 'Only published announcements can be featured.'})
        if status == Announcement.STATUS_PUBLISHED and not instance.published_at and not validated_data.get('published_at'):
            validated_data['published_at'] = timezone.now()
        announcement = super().update(instance, validated_data)
        if tag_names is not None:
            announcement.tags.set(resolve_tags(tag_names, Tag.SCOPE_ANNOUNCEMENT))
        if announcement.is_featured and announcement.status == Announcement.STATUS_PUBLISHED:
            Announcement.objects.filter(is_featured=True).exclude(pk=announcement.pk).update(is_featured=False)
        return announcement


class EventRegistrationSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = EventRegistration
        fields = [
            'id',
            'event',
            'user',
            'user_display',
            'user_email',
            'status',
            'staff_note',
            'registered_at',
            'reviewed_at',
            'reviewed_by',
        ]
        read_only_fields = fields

    def get_user_display(self, obj):
        user = obj.user
        if not user:
            return None
        return user.username

    def get_user_email(self, obj):
        user = obj.user
        if not user:
            return ''
        return (user.email or '').strip()


class EventSerializer(serializers.ModelSerializer):
    tag_names = serializers.ListField(
        child=serializers.CharField(max_length=80),
        write_only=True,
        required=False,
        allow_empty=True,
    )
    tags = TagSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    registration_count = serializers.SerializerMethodField()
    my_registration = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id',
            'title',
            'slug',
            'summary',
            'body',
            'audience',
            'registration_mode',
            'status',
            'starts_at',
            'ends_at',
            'location',
            'registration_opens_at',
            'registration_closes_at',
            'capacity',
            'cover_image_url',
            'created_by',
            'created_by_name',
            'tags',
            'tag_names',
            'registration_count',
            'my_registration',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['created_by', 'created_by_name', 'registration_count', 'my_registration', 'created_at', 'updated_at']

    def validate_slug(self, value):
        value = slugify((value or '').strip())
        if not value:
            raise serializers.ValidationError('Enter a valid URL slug.')
        if len(value) > 80:
            raise serializers.ValidationError('Slug must be 80 characters or fewer.')
        qs = Event.objects.filter(slug=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('This URL is already taken.')
        return value

    def validate(self, attrs):
        starts_at = attrs.get('starts_at', getattr(self.instance, 'starts_at', None))
        ends_at = attrs.get('ends_at', getattr(self.instance, 'ends_at', None))
        if starts_at and ends_at and ends_at <= starts_at:
            raise serializers.ValidationError(
                {'ends_at': 'End time must be after the start time.'}
            )
        return attrs

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return obj.created_by.get_full_name() or obj.created_by.username

    def get_registration_count(self, obj):
        return obj.registrations.filter(status=EventRegistration.STATUS_CONFIRMED).count()

    def get_my_registration(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        reg = obj.registrations.filter(user=request.user).exclude(status=EventRegistration.STATUS_CANCELLED).first()
        if not reg:
            return None
        return EventRegistrationSerializer(reg, context=self.context).data

    @transaction.atomic
    def create(self, validated_data):
        tag_names = validated_data.pop('tag_names', [])
        validated_data['created_by'] = self.context['request'].user
        event = super().create(validated_data)
        if tag_names:
            event.tags.set(resolve_tags(tag_names, Tag.SCOPE_EVENT))
        return event

    @transaction.atomic
    def update(self, instance, validated_data):
        tag_names = validated_data.pop('tag_names', None)
        event = super().update(instance, validated_data)
        if tag_names is not None:
            event.tags.set(resolve_tags(tag_names, Tag.SCOPE_EVENT))
        return event


class EventRegistrationReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=['approve', 'reject', 'promote'],
        required=False,
    )
    status = serializers.ChoiceField(
        choices=[
            EventRegistration.STATUS_CONFIRMED,
            EventRegistration.STATUS_WAITLISTED,
            EventRegistration.STATUS_PENDING,
            EventRegistration.STATUS_CANCELLED,
        ],
        required=False,
    )
    staff_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        if not attrs.get('action') and not attrs.get('status'):
            raise serializers.ValidationError('Provide action or status.')
        return attrs
