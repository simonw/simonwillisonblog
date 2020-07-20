from .models import Redirect
from django.http import HttpResponsePermanentRedirect


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
