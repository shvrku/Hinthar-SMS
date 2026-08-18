"""Shared Clerk identity helpers. Roles stay in Django; this never sets role."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError

User = get_user_model()

DEFAULT_ROLE = 'pending'
MOCK_CLERK_ID_PREFIX = 'clerk_mock_token_'
CLERK_USER_PK_CACHE_TTL = 60


def clerk_user_pk_cache_key(clerk_id: str) -> str:
    return f'clerk_user_pk:{clerk_id}'


def is_mock_clerk_id(clerk_id: str) -> bool:
    return (clerk_id or '').startswith(MOCK_CLERK_ID_PREFIX)


def _profile_qs():
    return User.objects.select_related(
        'teacher_profile', 'student_profile', 'staff_profile'
    )


def unique_username(desired: str, *, exclude_pk=None) -> str:
    base = (desired or '').strip() or 'user'
    base = base[:150]
    qs = User.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    if not qs.filter(username=base).exists():
        return base
    suffix = 2
    while True:
        candidate = f"{base[:140]}_{suffix}"
        if not qs.filter(username=candidate).exists():
            return candidate
        suffix += 1


def sync_identity(user, *, email: str, username: str) -> None:
    """Update email/username from Clerk without touching role."""
    update_fields: list[str] = []
    email = (email or '').strip()
    username = (username or '').strip()

    if email and user.email != email:
        user.email = email
        update_fields.append('email')

    if username and user.username != username:
        taken = User.objects.filter(username=username).exclude(pk=user.pk).exists()
        if not taken:
            user.username = username
            update_fields.append('username')

    if update_fields:
        user.save(update_fields=update_fields)


def identity_from_clerk_user(data: dict) -> tuple[str, str, str]:
    """Return (clerk_id, email, username) from a Clerk Backend API / webhook user object."""
    clerk_id = data.get('id') or ''
    if not isinstance(clerk_id, str):
        clerk_id = str(clerk_id)

    username = data.get('username') or ''
    if not isinstance(username, str):
        username = ''
    username = username.strip()

    email = ''
    emails = data.get('email_addresses') or []
    primary_id = data.get('primary_email_address_id')
    if isinstance(emails, list):
        if primary_id:
            for item in emails:
                if isinstance(item, dict) and item.get('id') == primary_id:
                    email = str(item.get('email_address') or '').strip()
                    break
        if not email:
            for item in emails:
                if isinstance(item, dict) and item.get('email_address'):
                    email = str(item.get('email_address')).strip()
                    break

    if not username:
        if email and '@' in email:
            username = email.split('@', 1)[0]
        else:
            username = clerk_id

    return clerk_id, email, username


def upsert_from_clerk(clerk_id: str, *, email: str, username: str):
    """Create as pending, or update email/username on an existing row."""
    clerk_id = (clerk_id or '').strip()
    if not clerk_id:
        raise ValueError('clerk_id is required')

    email = (email or '').strip()
    username = (username or '').strip() or clerk_id

    qs = _profile_qs()
    existing = qs.filter(clerk_id=clerk_id).first()
    if existing:
        sync_identity(existing, email=email, username=username)
        cache.set(clerk_user_pk_cache_key(clerk_id), existing.pk, CLERK_USER_PK_CACHE_TTL)
        return existing, False

    chosen = unique_username(username)
    try:
        user, created = User.objects.get_or_create(
            clerk_id=clerk_id,
            defaults={
                'username': chosen,
                'email': email,
                'role': DEFAULT_ROLE,
                'is_staff': False,
                'is_superuser': False,
            },
        )
    except IntegrityError:
        user = qs.filter(clerk_id=clerk_id).first()
        if user is None:
            chosen = unique_username(clerk_id)
            user, created = User.objects.get_or_create(
                clerk_id=clerk_id,
                defaults={
                    'username': chosen,
                    'email': email,
                    'role': DEFAULT_ROLE,
                    'is_staff': False,
                    'is_superuser': False,
                },
            )
        else:
            created = False

    user = qs.get(pk=user.pk)
    if not created:
        sync_identity(user, email=email, username=username)

    cache.set(clerk_user_pk_cache_key(clerk_id), user.pk, CLERK_USER_PK_CACHE_TTL)
    return user, created


def deactivate_from_clerk(clerk_id: str):
    """Set is_active=False. Do not delete. No-op if the row is missing."""
    clerk_id = (clerk_id or '').strip()
    if not clerk_id:
        return None
    user = User.objects.filter(clerk_id=clerk_id).first()
    if user is None:
        return None
    if user.is_active:
        user.is_active = False
        user.save(update_fields=['is_active'])
    cache.delete(clerk_user_pk_cache_key(clerk_id))
    return user


def relink_clerk_id(django_user, new_clerk_id: str, *, email: str, username: str):
    """Replace clerk_id when the new id is unused. Keep role and profile FKs."""
    new_clerk_id = (new_clerk_id or '').strip()
    if not new_clerk_id:
        raise ValueError('clerk_id is required')
    if User.objects.filter(clerk_id=new_clerk_id).exclude(pk=django_user.pk).exists():
        raise ValueError('That Clerk id is already on another Django user.')

    old_clerk_id = django_user.clerk_id
    django_user.clerk_id = new_clerk_id
    django_user.save(update_fields=['clerk_id'])
    sync_identity(django_user, email=email, username=username)
    cache.delete(clerk_user_pk_cache_key(old_clerk_id))
    cache.set(clerk_user_pk_cache_key(new_clerk_id), django_user.pk, CLERK_USER_PK_CACHE_TTL)
    return django_user
