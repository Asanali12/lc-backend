from functools import wraps

from django.conf import settings
from django.http import JsonResponse


def require_write_token(view):
    """Bearer-token gate for write endpoints. If LC_BACKEND_WRITE_TOKEN is
    unset, all writes are allowed — the server prints a warning at boot so
    the operator notices."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        expected = (settings.LC_BACKEND_WRITE_TOKEN or "").strip()
        if not expected:
            return view(request, *args, **kwargs)
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            provided = header[len("Bearer ") :].strip()
        else:
            provided = request.headers.get("X-API-Key", "").strip()
        if provided != expected:
            return JsonResponse({"error": "unauthorized"}, status=401)
        return view(request, *args, **kwargs)

    return wrapper
