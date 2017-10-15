from .utils import is_cloudflare

CF_HEADER = 'HTTP_CF_CONNECTING_IP'


def cloudflare_ip_middleware(get_response):
    def middleware(request):
        remote_addr = request.META['REMOTE_ADDR']
        if is_cloudflare(remote_addr) and CF_HEADER in request.META:
            request.META['REMOTE_ADDR'] = request.META[CF_HEADER]
        return get_response(request)

    return middleware
