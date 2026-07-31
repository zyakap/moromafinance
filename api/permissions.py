"""API authentication for machine-to-machine endpoints (e.g. the DCC sync).

Access is granted only when the request carries a valid API key in the
``X-API-KEY`` header that matches ``settings.DCC_API_KEY``. The key is loaded
from the environment (.env) and must never be committed to source control.

Fails closed: if no key is configured on the server, all requests are denied.
"""
import hmac

from django.conf import settings
from rest_framework.permissions import BasePermission


class HasAPIKey(BasePermission):
    message = 'A valid X-API-KEY header is required.'

    def has_permission(self, request, view):
        configured = getattr(settings, 'DCC_API_KEY', '') or ''
        provided = request.META.get('HTTP_X_API_KEY', '') or ''
        if not configured or not provided:
            return False
        # Constant-time comparison to avoid timing side-channels.
        return hmac.compare_digest(str(configured), str(provided))
