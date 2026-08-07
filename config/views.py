from django.http import JsonResponse


def health(request):
    """Public liveness probe for uptime monitors (no auth)."""
    return JsonResponse({"status": "ok"})
