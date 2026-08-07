import logging

import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import authentication, exceptions
from drf_spectacular.extensions import OpenApiAuthenticationExtension

User = get_user_model()
logger = logging.getLogger(__name__)


class ClerkJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = 'people.authentication.ClerkJWTAuthentication'
    name = 'clerk_jwt'

    def get_security_definition(self, auto_schema):
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'description': 'Clerk-issued JWT token.',
        }

DEFAULT_ROLE = 'pending'

class ClerkJWTAuthentication(authentication.BaseAuthentication):
    """
    Custom DRF authentication class for Clerk JWT verification.
    
    Clerk handles identity (who you are). Roles are managed locally
    in the Django User model via the admin panel — NOT synced from Clerk.
    """

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization')
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None

        token = parts[1]

        # Local test bypass — opt-in via ENABLE_MOCK_AUTH=true AND DEBUG=True only
        if settings.DEBUG and getattr(settings, 'ENABLE_MOCK_AUTH', False) and token.startswith("mock_token_"):
            return self._authenticate_mock(token)

        return self._authenticate_clerk(token)

    def _reject_if_inactive(self, user):
        """SEC-H1: deactivated accounts must not authenticate."""
        if not user.is_active:
            raise exceptions.AuthenticationFailed("User account is deactivated.")
        return user

    def _authenticate_mock(self, token):
        """
        Helper for local testing without real Clerk endpoints.
        All mock users get the DEFAULT_ROLE — change via admin if needed.
        """
        clerk_id = f"clerk_{token}"
        username = f"user_{token}"
        email = f"{username}@example.com"

        existing = User.objects.filter(clerk_id=clerk_id).first()
        if existing:
            self._reject_if_inactive(existing)
            return (existing, token)

        # SEC-L2: cap unbounded mock user creation
        mock_count = User.objects.filter(clerk_id__startswith='clerk_mock_token_').count()
        if mock_count >= 50:
            raise exceptions.AuthenticationFailed("Too many mock users; refuse new mock provisioning.")

        user = User.objects.create(
            clerk_id=clerk_id,
            username=username,
            email=email,
            role=DEFAULT_ROLE,
            is_staff=False,
            is_superuser=False,
        )

        self._reject_if_inactive(user)
        return (user, token)

    def _fetch_jwks(self, jwks_url, *, force_refresh=False):
        if not force_refresh:
            jwks = cache.get('clerk_jwks')
            if jwks:
                return jwks
        response = requests.get(jwks_url, timeout=5)
        response.raise_for_status()
        jwks = response.json()
        cache.set('clerk_jwks', jwks, timeout=3600)
        return jwks

    def _public_key_for_kid(self, jwks, kid):
        for key in jwks.get('keys', []):
            if key.get('kid') == kid:
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
        return None

    def _authenticate_clerk(self, token):
        jwks_url = getattr(settings, 'CLERK_JWKS_URL', '')
        if not jwks_url:
            raise exceptions.AuthenticationFailed("Clerk JWKS URL is not configured.")

        issuer = getattr(settings, 'CLERK_JWT_ISSUER', '') or getattr(settings, 'CLERK_FRONTEND_API', '')
        if not issuer:
            raise exceptions.AuthenticationFailed("Clerk JWT issuer is not configured.")

        audience = getattr(settings, 'CLERK_JWT_AUDIENCE', '') or ''
        # SEC-M1: require audience binding outside DEBUG
        if not audience and not settings.DEBUG:
            raise exceptions.AuthenticationFailed("Clerk JWT audience is not configured.")

        try:
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
            if not kid:
                raise exceptions.AuthenticationFailed("Token does not contain 'kid' in header.")

            jwks = self._fetch_jwks(jwks_url)
            public_key = self._public_key_for_kid(jwks, kid)
            # SEC-L3: kid miss → bust cache and refetch once (key rotation)
            if not public_key:
                jwks = self._fetch_jwks(jwks_url, force_refresh=True)
                public_key = self._public_key_for_kid(jwks, kid)
            if not public_key:
                raise exceptions.AuthenticationFailed("Matching public key not found in JWKS.")

            decode_kwargs = {
                'algorithms': ['RS256'],
                'issuer': issuer,
                'leeway': 60,
                'options': {
                    'verify_iss': True,
                    'verify_aud': bool(audience),
                },
            }
            if audience:
                decode_kwargs['audience'] = audience

            payload = jwt.decode(token, public_key, **decode_kwargs)

        except exceptions.AuthenticationFailed:
            raise
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.ImmatureSignatureError:
            raise exceptions.AuthenticationFailed("Token is not yet valid (clock skew).")
        except jwt.InvalidSignatureError:
            raise exceptions.AuthenticationFailed("Token signature is invalid.")
        except jwt.InvalidIssuerError:
            raise exceptions.AuthenticationFailed("Token issuer is invalid.")
        except jwt.InvalidAudienceError:
            raise exceptions.AuthenticationFailed("Token audience is invalid.")
        except jwt.DecodeError:
            raise exceptions.AuthenticationFailed("Token decoding failed.")
        except requests.RequestException:
            raise exceptions.AuthenticationFailed("Failed to fetch JWKS keys from Clerk.")
        except Exception as e:
            # SEC-M2: never leak internal exception detail to clients
            logger.exception("Token verification failed: %s", e)
            raise exceptions.AuthenticationFailed("Token verification failed.")

        # 5. Extract identity claims (NOT role — roles are managed in Django admin).
        #    Expect custom session-token claims from Clerk Dashboard → Sessions:
        #      { "email": "{{user.primary_email_address}}", "username": "{{user.username}}" }
        clerk_id = payload.get('sub')
        if not clerk_id:
            raise exceptions.AuthenticationFailed("Token does not contain 'sub' claim.")

        email, username = self._identity_from_claims(payload, clerk_id)

        # 6. JIT provision the User with DEFAULT_ROLE
        #    Role is NEVER overwritten from Clerk — admins manage it via Django /users.
        user, created = User.objects.get_or_create(
            clerk_id=clerk_id,
            defaults={
                'username': username,
                'email': email,
                'role': DEFAULT_ROLE,
                'is_staff': False,
                'is_superuser': False,
            }
        )

        # 7. Sync identity fields only (never role) when Clerk claims improve
        if not created:
            self._sync_identity(user, email=email, username=username)

        self._reject_if_inactive(user)
        return (user, token)

    @staticmethod
    def _identity_from_claims(payload, clerk_id: str) -> tuple[str, str]:
        """
        Resolve email + username from the Clerk session JWT.

        Prefer explicit claims added via Clerk session-token customization.
        Fall back to email local-part, then clerk_id, so JIT never fails.
        """
        email = (
            payload.get('email')
            or payload.get('primary_email_address')
            or payload.get('primaryEmail')
            or ''
        )
        if isinstance(email, str):
            email = email.strip()
        else:
            email = ''

        username_claim = payload.get('username') or payload.get('user_username') or ''
        if isinstance(username_claim, str):
            username_claim = username_claim.strip()
        else:
            username_claim = ''

        if username_claim:
            username = username_claim
        elif email and '@' in email:
            username = email.split('@', 1)[0]
        else:
            username = clerk_id

        return email, username

    @staticmethod
    def _sync_identity(user, *, email: str, username: str) -> None:
        """Update email/username from Clerk without touching role."""
        update_fields: list[str] = []

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
