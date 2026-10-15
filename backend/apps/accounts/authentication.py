from rest_framework.authentication import SessionAuthentication


class CsrfEnforcedSessionAuthentication(SessionAuthentication):
    """
    Session (cookie) authentication. DRF already enforces CSRF for authenticated session requests;
    unauthenticated auth endpoints (login/register/reset) are additionally wrapped with `csrf_protect`.
    Session cookies are HttpOnly, so XSS cannot steal them (unlike tokens kept in localStorage).
    """

    def authenticate_header(self, request):
        # Makes unauthenticated API calls return 401 (not 403) so the SPA can tell "sign in" from "forbidden".
        return 'Session realm="api"'
