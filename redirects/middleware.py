import re

from .models import Redirect
from django.http import HttpResponseNotFound, HttpResponsePermanentRedirect


CANONICAL_HOST = "simonwillison.net"

# Crawlers occasionally get stuck in a loop re-URL-encoding their own input:
# "%" becomes "%25", which re-encoded becomes "%2525", then "%252525", and so
# on. Two shapes show up in logs:
#   1. "%25%25%25..."     — three-or-more literal "%"s, each encoded once.
#   2. "%252525252525..." — a single "%" re-encoded recursively; each
#                           additional level appends another "25".
# Both are bot pathologies: no legitimate URL contains three literal "%"
# characters in a row, and no legitimate URL-encoding produces more than
# two hex digits after a single "%". These requests can still match real
# URL prefixes (e.g. /tags/<slug>/) and trigger expensive view + DB work
# for what is effectively garbage input, so we short-circuit them here
# with a bare 404 before any downstream middleware or view runs.
NESTED_PERCENT_ENCODING_RE = re.compile(r"(?:%25){3,}|%(?:25){3,}")


def block_nested_percent_encoding_middleware(get_response):
    def middleware(request):
        if NESTED_PERCENT_ENCODING_RE.search(request.get_full_path()):
            return HttpResponseNotFound()
        return get_response(request)

    return middleware


def herokuapp_redirect_middleware(get_response):
    def middleware(request):
        if request.get_host().endswith(".herokuapp.com"):
            return HttpResponsePermanentRedirect(
                "https://" + CANONICAL_HOST + request.get_full_path()
            )
        return get_response(request)

    return middleware


def redirect_middleware(get_response):
    def middleware(request):
        path = request.path.lstrip("/")
        redirects = list(
            Redirect.objects.filter(
                domain=request.get_host(),
                # We redirect on either a path match or a '*'
                # record existing for this domain
                path__in=(path, "*"),
            )
        )
        # A non-star redirect always takes precedence
        non_star = [r for r in redirects if r.path != "*"]
        if non_star:
            return HttpResponsePermanentRedirect(non_star[0].target)
        # If there's a star redirect, build path and redirect to that
        star = [r for r in redirects if r.path == "*"]
        if star:
            new_url = star[0].target + path
            if request.META["QUERY_STRING"]:
                new_url += "?" + request.META["QUERY_STRING"]
            return HttpResponsePermanentRedirect(new_url)
        # Default: no redirects, just get on with it:
        return get_response(request)

    return middleware
