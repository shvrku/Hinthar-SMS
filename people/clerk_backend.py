"""Clerk Backend API client. Used by admin Clerk Sync / Import / Link — not by the browser."""

import logging

import requests
from django.conf import settings

from people.clerk_users import identity_from_clerk_user

logger = logging.getLogger(__name__)

CLERK_API_BASE = 'https://api.clerk.com/v1'
CLERK_DASHBOARD_USERS_URL = 'https://dashboard.clerk.com'
LIST_PAGE_SIZE = 500
LIST_MAX_PAGES = 20


class ClerkBackendError(Exception):
    """Clerk HTTP failed. Views map this to 502."""


def _headers():
    secret = getattr(settings, 'CLERK_SECRET_KEY', '') or ''
    if not secret:
        raise ClerkBackendError('Clerk secret key is not configured.')
    return {
        'Authorization': f'Bearer {secret}',
        'Content-Type': 'application/json',
    }


def _parse_user_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get('data'), list):
        return payload['data']
    raise ClerkBackendError('Unexpected Clerk user list response.')


def public_clerk_user(data: dict) -> dict:
    clerk_id, email, username = identity_from_clerk_user(data)
    return {
        'clerk_id': clerk_id,
        'email': email,
        'username': username,
    }


def list_clerk_users() -> list[dict]:
    users: list[dict] = []
    offset = 0
    for _ in range(LIST_MAX_PAGES):
        try:
            response = requests.get(
                f'{CLERK_API_BASE}/users',
                headers=_headers(),
                params={'limit': LIST_PAGE_SIZE, 'offset': offset},
                timeout=15,
            )
        except requests.RequestException as exc:
            logger.exception('Clerk list users failed: %s', exc)
            raise ClerkBackendError('Failed to list users from Clerk.') from exc

        if not response.ok:
            logger.error('Clerk list users HTTP %s: %s', response.status_code, response.text[:300])
            raise ClerkBackendError('Failed to list users from Clerk.')

        batch = _parse_user_list(response.json())
        users.extend(item for item in batch if isinstance(item, dict) and item.get('id'))
        if len(batch) < LIST_PAGE_SIZE:
            break
        offset += LIST_PAGE_SIZE
    return users


def get_clerk_user(clerk_id: str) -> dict | None:
    clerk_id = (clerk_id or '').strip()
    if not clerk_id:
        return None
    try:
        response = requests.get(
            f'{CLERK_API_BASE}/users/{clerk_id}',
            headers=_headers(),
            timeout=15,
        )
    except requests.RequestException as exc:
        logger.exception('Clerk get user failed: %s', exc)
        raise ClerkBackendError('Failed to fetch user from Clerk.') from exc

    if response.status_code == 404:
        return None
    if not response.ok:
        logger.error('Clerk get user HTTP %s: %s', response.status_code, response.text[:300])
        raise ClerkBackendError('Failed to fetch user from Clerk.')

    data = response.json()
    if not isinstance(data, dict):
        raise ClerkBackendError('Unexpected Clerk user response.')
    return data
