from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from django.shortcuts import redirect


class AmpersandRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        full_path = request.get_full_path()
        if "&amp;" in full_path or "&amp%3B" in full_path:
            parsed_url = urlparse(full_path)
            query_params = parse_qsl(parsed_url.query)

            # Replace &amp; with & in the query parameters
            corrected_query = [(k.replace("amp;", ""), v) for k, v in query_params]

            # Rebuild the URL with corrected query parameters
            corrected_url = urlunparse(
                (
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    urlencode(corrected_query),
                    parsed_url.fragment,
                )
            )

            # Redirect the user to the corrected URL
            return redirect(corrected_url)

        response = self.get_response(request)
        return response
