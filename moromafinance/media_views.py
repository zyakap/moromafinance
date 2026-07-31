"""Authenticated serving of uploaded media (KYC documents, payslips, IDs).

Uploaded files contain sensitive personal data and must never be world-readable
by guessing predictable filenames. This view requires an authenticated user and
then hands off the actual byte-streaming to nginx via ``X-Accel-Redirect`` (fast,
zero-copy). If nginx isn't configured for that yet, it falls back to Django's
``FileResponse``.

REQUIRED nginx change to actually enforce protection (until then, nginx may still
serve /uploads/ publicly):

    # Make the raw upload directory reachable ONLY via X-Accel-Redirect:
    location /protected-uploads/ {
        internal;
        alias /root/moromafinance/uploads/;
    }
    # Remove/replace any public `location /uploads/ { ... }` block so that the
    # only path to these files is through Django's /media/<path> view below.
"""
import os
import posixpath

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse


def _safe_join(root, path):
    """Join *path* onto *root*, refusing anything that escapes *root*."""
    path = posixpath.normpath('/' + path).lstrip('/')
    full = os.path.realpath(os.path.join(root, path))
    root = os.path.realpath(root)
    if not (full == root or full.startswith(root + os.sep)):
        raise Http404('Not found')
    return full


# Media sub-directories that are public by design (white-label branding assets:
# logos + favicon). These are shown on the unauthenticated login page, so they
# must not require a logged-in user. Everything else (KYC docs, payslips, IDs)
# stays behind the auth gate below.
PUBLIC_MEDIA_PREFIXES = ('branding/',)


def _is_public(path):
    norm = posixpath.normpath('/' + path).lstrip('/')
    return norm.startswith(PUBLIC_MEDIA_PREFIXES)


def protected_media(request, path):
    if not _is_public(path) and not request.user.is_authenticated:
        # Bounce to login rather than leaking existence of the file.
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())

    full_path = _safe_join(str(settings.MEDIA_ROOT), path)
    if not os.path.isfile(full_path):
        raise Http404('Not found')

    # Preferred path: let nginx stream the file from an internal location.
    if getattr(settings, 'USE_X_ACCEL_REDIRECT', False):
        response = HttpResponse()
        response['X-Accel-Redirect'] = '/protected-uploads/' + path
        # Let nginx set Content-Type from the file extension.
        del response['Content-Type']
        return response

    # Fallback: Django streams it (works without nginx changes, just slower).
    return FileResponse(open(full_path, 'rb'))
