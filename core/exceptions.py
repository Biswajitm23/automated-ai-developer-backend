from django.http import Http404
from rest_framework import exceptions
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    """DRF's handler, but a missing record is always {"detail": "Not found."}.

    Django's Http404 from get_object_or_404 carries "No <Model> matches the given query.",
    which names internal models; the API contract promises a plain "Not found." — also for
    records the caller may not see, so their existence does not leak.
    """
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    return drf_exception_handler(exc, context)
