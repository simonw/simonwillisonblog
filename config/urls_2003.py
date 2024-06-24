from django.urls import re_path, include
from django.http import (
    HttpResponse,
)
from django.conf import settings
from blog import views_2003 as blog_views


DISALLOW_ALL = """
User-agent: *
Disallow: /
""".strip()


def robots_txt(request):
    return HttpResponse(DISALLOW_ALL, content_type="text/plain")


urlpatterns = [
    re_path(r"^$", blog_views.index),
    re_path(r"^robots\.txt$", robots_txt),
]


if settings.DEBUG:
    try:
        import debug_toolbar

        urlpatterns = [
            re_path(r"^__debug__/", include(debug_toolbar.urls))
        ] + urlpatterns
    except ImportError:
        pass
