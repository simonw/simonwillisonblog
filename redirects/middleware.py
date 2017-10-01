from .models import Redirect
from django.http import HttpResponseRedirect


def redirect_middleware(get_response):
    def middleware(request):
        try:
            redirect = Redirect.objects.get(
                domain=request.get_host(),
                path=request.path.lstrip('/')
            )
            return HttpResponseRedirect(redirect.target)
        except Redirect.DoesNotExist:
            pass
        return get_response(request)

    return middleware
