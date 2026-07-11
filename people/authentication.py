import jwt
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework import authentication, exceptions

User = get_user_model()

class ClerkJWTAuthentication(authentication.BaseAuthentication):
    """
    Custom DRF authentication class for Clerk JWT verification.
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
        if settings.DEBUG and token.startswith("mock_token_"):
            return self._authenticate_mock(token)
            
        return self._authenticate_clerk(token)

    def _authenticate_mock(self, token):
        """
        Helper for local testing without real Clerk endpoints.
        E.g., mock_token_admin, mock_token_teacher_1, mock_token_student_1
        """
        role = 'student'
        if 'admin' in token:
            role = 'admin'
        elif 'teacher' in token:
            role = 'teacher'
            
        clerk_id = f"clerk_{token}"
        username = f"user_{token}"
        email = f"{username}@example.com"
        
        # JIT provision/retrieve mock user
        user, created = User.objects.get_or_create(
            clerk_id=clerk_id,
            defaults={
                'username': username,
                'email': email,
                'role': role,
                'is_staff': role == 'admin',
                'is_superuser': role == 'admin',
            }
        )
        
        # Update role if it changed
        if user.role != role:
            user.role = role
            user.is_staff = role == 'admin'
            user.is_superuser = role == 'admin'
            user.save(update_fields=['role', 'is_staff', 'is_superuser'])
            
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
                
            # 4. Decode and verify the JWT
            # Clerk token audience is usually the frontend URL or empty
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                options={"verify_aud": False}
            )
            
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Token has expired.")
        except jwt.InvalidSignatureError:
            raise exceptions.AuthenticationFailed("Token signature is invalid.")
        except jwt.DecodeError:
            raise exceptions.AuthenticationFailed("Token decoding failed.")
        except requests.RequestException:
            raise exceptions.AuthenticationFailed("Failed to fetch JWKS keys from Clerk.")
        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Token verification failed: {str(e)}")
            
        # 5. Extract user claims
        clerk_id = payload.get('sub')
        if not clerk_id:
            raise exceptions.AuthenticationFailed("Token does not contain 'sub' claim.")
            
        # Extract metadata and determine role
        # Standard custom claim for metadata or role structure from Clerk JWT template
        role = payload.get('role') or payload.get('public_metadata', {}).get('role', 'student')
        email = payload.get('email') or payload.get('primary_email_address') or ""
        
        # Determine username (use clerk_id as fallback)
        username = payload.get('username') or email.split('@')[0] if email else clerk_id
        
        # 6. JIT provision the User
        user, created = User.objects.get_or_create(
            clerk_id=clerk_id,
            defaults={
                'username': username,
                'email': email,
                'role': role,
                'is_staff': role == 'admin',
                'is_superuser': role == 'admin',
            }
        )
        
        # If user exists, verify / update role if it changed in Clerk
        if not created:
            updated_fields = []
            if user.role != role:
                user.role = role
                user.is_staff = role == 'admin'
                user.is_superuser = role == 'admin'
                updated_fields.extend(['role', 'is_staff', 'is_superuser'])
            if email and user.email != email:
                user.email = email
                updated_fields.append('email')
            if updated_fields:
                user.save(update_fields=updated_fields)
                
        return (user, token)
