from django.urls import path, re_path
from django.contrib import admin
from django.http import HttpResponsePermanentRedirect, HttpResponse
from django.conf import settings
from blog import views as blog_views
from blog import feeds
from feedstats.utils import count_subscribers
import os

FAVICON = open(os.path.join(settings.BASE_DIR, 'static/favicon.ico'), 'rb').read()


def static_redirect(request):
    return HttpResponsePermanentRedirect(
        'http://static.simonwillison.net%s' % request.get_full_path()
    )

STAGING_ROBOTS_TXT = '''
User-agent: Twitterbot
Disallow:

User-agent: *
Disallow: /
'''

PRODUCTION_ROBOTS_TXT = '''
User-agent: *
Disallow: /admin/

Sitemap: https://simonwillison.net/sitemap.xml
'''


def robots_txt(request):
    if settings.STAGING:
        txt = STAGING_ROBOTS_TXT
    else:
        txt = PRODUCTION_ROBOTS_TXT
    return HttpResponse(txt, content_type='text/plain')


def favicon_ico(request):
    return HttpResponse(FAVICON, content_type='image/x-icon')


urlpatterns = [
    re_path(r'^$', blog_views.index),
    re_path(r'^(\d{4})/$', blog_views.archive_year),
    re_path(r'^(\d{4})/(\w{3})/$', blog_views.archive_month),
    re_path(r'^(\d{4})/(\w{3})/(\d{1,2})/$', blog_views.archive_day),
    re_path(r'^(\d{4})/(\w{3})/(\d{1,2})/([\-\w]+)/$', blog_views.archive_item),

    # Ancient URL pattern still getting hits
    re_path(r'^/?archive/(\d{4})/(\d{2})/(\d{2})/$', blog_views.archive_day_redirect),
    re_path(r'^/?archive/(\d{4})/(\d{2})/(\d{2})/([\-\w]+)/?$', blog_views.archive_item_redirect),

    re_path(r'^robots\.txt$', robots_txt),
    re_path(r'^favicon\.ico$', favicon_ico),

    re_path(r'^search/$', blog_views.search),
    re_path(r'^tags/$', blog_views.tag_index),
    re_path(r'^tags/(.*?)/$', blog_views.archive_tag),

    re_path(r'^atom/entries/$', count_subscribers(feeds.Entries().__call__)),
    re_path(r'^atom/links/$', count_subscribers(feeds.Blogmarks().__call__)),
    re_path(r'^atom/everything/$', count_subscribers(feeds.Everything().__call__)),

    re_path(r'^sitemap\.xml$', feeds.sitemap),

    re_path(r'^tools/$', blog_views.tools),
    re_path(r'^tools/search-tags/$', blog_views.tools_search_tags),

    re_path(r'^write/$', blog_views.write),
    #  (r'^about/$', blog_views.about),

    re_path(r'^admin/', admin.site.urls),
    re_path(r'^static/', static_redirect),
]
