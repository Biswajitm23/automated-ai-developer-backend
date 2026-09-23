from rest_framework import authentication
from rest_framework.request import Request


class SessionAuthentication(authentication.SessionAuthentication):
    """Session authentication that makes DRF answer unauthenticated requests with 401, not 403.

    The 'Session' challenge is not one browsers act on, so no Basic-auth prompt appears.
    """

    def authenticate_header(self, request: Request) -> str:
        return "Session"


def enforce_csrf(request: Request) -> None:
    """Run DRF's CSRF check even for anonymous requests; raises PermissionDenied (JSON 403)."""
    SessionAuthentication().enforce_csrf(request)
