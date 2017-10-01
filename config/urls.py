from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponseRedirect, HttpResponse
from django.conf import settings
from blog import views as blog_views
from blog import feeds
import os

FAVICON = open(os.path.join(settings.BASE_DIR, 'static/favicon.ico')).read()


def static_redirect(request):
    return HttpResponseRedirect(
        'http://static.simonwillison.net%s' % request.get_full_path()
    )


def robots_txt(request):
    if settings.STAGING:
        txt = 'User-agent: *\nDisallow: /'
    else:
        txt = 'User-agent: *\nDisallow: /admin/'
    return HttpResponse(txt, content_type='text/plain')


def favicon_ico(request):
    return HttpResponse(FAVICON, content_type='image/x-icon')


urlpatterns = [
    url(r'^$', blog_views.index),
    url(r'^(\d{4})/$', blog_views.archive_year),
    url(r'^(\d{4})/(\w{3})/$', blog_views.archive_month),
    url(r'^(\d{4})/(\w{3})/(\d{1,2})/$', blog_views.archive_day),
    url(r'^(\d{4})/(\w{3})/(\d{1,2})/([\-\w]+)/$', blog_views.archive_item),

    url(r'^robots\.txt$', robots_txt),
    url(r'^favicon\.ico$', favicon_ico),

    url(r'^search/$', blog_views.search),
    url(r'^tags/$', blog_views.tag_index),
    url(r'^tags/(.*?)/$', blog_views.archive_tag),

    url(r'^atom/entries/$', feeds.Entries()),
    url(r'^atom/links/$', feeds.Blogmarks()),
    url(r'^atom/everything/$', feeds.Everything()),

    url(r'^tools/$', blog_views.tools),
    url(r'^write/$', blog_views.write),
    #  (r'^about/$', blog_views.about),

    url(r'^admin/', include(admin.site.urls)),
    url(r'^static/', static_redirect),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        url(r'^__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns
