from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema
from people.serializers import UserSerializer

class MeView(APIView):
    """
    Returns the authenticated user's profile info.
    This endpoint is JIT provisioned automatically upon token validation.
    """
    permission_classes = [IsAuthenticated]
    
    @extend_schema(
        responses={200: UserSerializer},
        summary="Get current user details",
        description="Retrieve profile details for the currently logged in user based on Clerk access token validation."
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)
