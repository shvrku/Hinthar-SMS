"""Clerk → SMS webhooks. Svix verifies the signature; JWT auth is skipped."""

import json
import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from svix.webhooks import Webhook, WebhookVerificationError

from people.clerk_users import (
    deactivate_from_clerk,
    identity_from_clerk_user,
    upsert_from_clerk,
)

logger = logging.getLogger(__name__)

UPSERT_EVENTS = frozenset({'user.created', 'user.updated'})
DEACTIVATE_EVENTS = frozenset({'user.deleted'})


@method_decorator(csrf_exempt, name='dispatch')
class ClerkWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        secret = getattr(settings, 'CLERK_WEBHOOK_SECRET', '') or ''
        if not secret:
            return Response({'error': 'Webhook secret is not configured.'}, status=401)

        headers = {
            'svix-id': request.META.get('HTTP_SVIX_ID', ''),
            'svix-timestamp': request.META.get('HTTP_SVIX_TIMESTAMP', ''),
            'svix-signature': request.META.get('HTTP_SVIX_SIGNATURE', ''),
        }
        try:
            payload = Webhook(secret).verify(request.body, headers)
        except WebhookVerificationError:
            return Response({'error': 'Invalid webhook signature.'}, status=401)

        if not isinstance(payload, dict):
            try:
                payload = json.loads(request.body.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return Response({'error': 'Invalid webhook payload.'}, status=400)

        event_type = payload.get('type') or ''
        data = payload.get('data') if isinstance(payload.get('data'), dict) else {}

        if event_type in UPSERT_EVENTS:
            clerk_id, email, username = identity_from_clerk_user(data)
            if not clerk_id:
                return Response({'error': 'Webhook user is missing id.'}, status=400)
            user, created = upsert_from_clerk(clerk_id, email=email, username=username)
            banned = data.get('banned') is True
            if banned:
                deactivate_from_clerk(clerk_id)
                user.refresh_from_db()
            logger.info(
                'Clerk webhook %s clerk_id=%s django_id=%s created=%s banned=%s',
                event_type,
                clerk_id,
                user.pk,
                created,
                banned,
            )
            return Response({'ok': True, 'created': created, 'deactivated': banned})

        if event_type in DEACTIVATE_EVENTS:
            clerk_id = data.get('id') or ''
            deactivate_from_clerk(str(clerk_id))
            logger.info('Clerk webhook %s clerk_id=%s deactivated', event_type, clerk_id)
            return Response({'ok': True})

        return Response({'ok': True, 'ignored': event_type})
