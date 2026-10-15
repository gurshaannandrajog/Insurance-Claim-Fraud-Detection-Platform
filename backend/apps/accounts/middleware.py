"""
REQ-AUTH-006 / REQ-SEC-005 — terminate sessions after 30 minutes of inactivity.

The timestamp of the last *user-initiated* request is stored in the server-side session.
Background polls (the notification badge) send `X-Background-Poll: 1` and are **not** treated as activity,
so an idle browser tab cannot keep a session alive forever. Enforcement is server-side; the frontend
only reacts to the 401 `session_expired` response.
"""
import time

from django.conf import settings
from django.contrib.auth import logout
from django.http import JsonResponse

from apps.audit.models import AuditAction
from apps.audit.services import log_event

SESSION_KEY = "_last_activity"


class InactivityTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = time.time()
            last = request.session.get(SESSION_KEY)
            limit = settings.SESSION_INACTIVITY_MINUTES * 60
            if last is not None and now - float(last) > limit:
                log_event(AuditAction.SESSION_EXPIRED, user, actor=user, request=request,
                          description="Session terminated after inactivity")
                logout(request)
                return JsonResponse(
                    {"error": {"code": "session_expired",
                               "message": "Your session expired after 30 minutes of inactivity. Please sign in again."}},
                    status=401,
                )
            if request.headers.get("X-Background-Poll") != "1" or last is None:
                request.session[SESSION_KEY] = now
        return self.get_response(request)
