from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404

from .models import ShortURL


def redirect(request, short_id):
    pk = int(short_id, 32) - 1010
    if not 1 <= pk <= 2**63 - 1:
        raise Http404
    short_url = get_object_or_404(ShortURL, pk=pk)
    # Destinations are managed in the admin and may exceed Django's default
    # redirect length limit (including after Unicode URL escaping).
    return HttpResponseRedirect(short_url.url, max_length=None)
