import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import authentication, exceptions
from drf_spectacular.extensions import OpenApiAuthenticationExtension

User = get_user_model()


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

        # Local test bypass / mock authentication for development
        if settings.DEBUG and getattr(settings, 'ENABLE_MOCK_AUTH', False) and token.startswith("mock_token_"):
            return self._authenticate_mock(token)

        return self._authenticate_clerk(token)

    def _authenticate_mock(self, token):
        """
        Helper for local testing without real Clerk endpoints.
        All mock users get the DEFAULT_ROLE — change via admin if needed.
        """
        clerk_id = f"clerk_{token}"
        username = f"user_{token}"
        email = f"{username}@example.com"

        user, _ = User.objects.get_or_create(
            clerk_id=clerk_id,
            defaults={
                'username': username,
                'email': email,
                'role': DEFAULT_ROLE,
                'is_staff': False,
                'is_superuser': False,
            }
        )

        return (user, token)

    def _authenticate_clerk(self, token):
        jwks_url = getattr(settings, 'CLERK_JWKS_URL', '')
        if not jwks_url:
            raise exceptions.AuthenticationFailed("Clerk JWKS URL is not configured.")

        try:
            # 1. Fetch public keys from Clerk's JWKS endpoint (cache for 1 hour)
            jwks = cache.get('clerk_jwks')
            if not jwks:
                response = requests.get(jwks_url, timeout=5)
                response.raise_for_status()
                jwks = response.json()
                cache.set('clerk_jwks', jwks, timeout=3600)

            # 2. Get the kid from the JWT header
            unverified_header = jwt.get_unverified_header(token)
            kid = unverified_header.get('kid')
            if not kid:
                raise exceptions.AuthenticationFailed("Token does not contain 'kid' in header.")

            # 3. Find the matching public key
            public_key = None
            for key in jwks.get('keys', []):
                if key.get('kid') == kid:
                    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key)
                    break

            if not public_key:
                raise exceptions.AuthenticationFailed("Matching public key not found in JWKS.")

            # 4. Decode and verify the JWT (leeway=60 handles clock skew between Clerk servers and local machine)
            audience = getattr(settings, 'CLERK_JWT_AUDIENCE', '')
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                audience=audience or None,
                options={"verify_aud": bool(audience)},
                leeway=60
            )

        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.ImmatureSignatureError:
            raise exceptions.AuthenticationFailed("Token is not yet valid (clock skew).")
        except jwt.InvalidSignatureError:
            raise exceptions.AuthenticationFailed("Token signature is invalid.")
        except jwt.DecodeError:
            raise exceptions.AuthenticationFailed("Token decoding failed.")
        except requests.RequestException:
            raise exceptions.AuthenticationFailed("Failed to fetch JWKS keys from Clerk.")
        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Token verification failed: {str(e)}")

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
