from django.conf.urls import include, url
from django.contrib import admin
from django.http import HttpResponseRedirect
from blog import views as blog_views


def static_redirect(request):
    return HttpResponseRedirect(
        'http://static.simonwillison.net%s' % request.get_full_path()
    )

urlpatterns = [
    url(r'^$', blog_views.index),
    url(r'^(\d{4})/$', blog_views.archive_year),
    url(r'^(\d{4})/(\w{3})/$', blog_views.archive_month),
    url(r'^(\d{4})/(\w{3})/(\d{1,2})/$', blog_views.archive_day),
    url(r'^(\d{4})/(\w{3})/(\d{1,2})/([\-\w]+)/$', blog_views.archive_item),

    url(r'^write/$', blog_views.write),
    #  (r'^about/$', blog_views.about),
    url(r'^tags/$', blog_views.tag_index),
    url(r'^tags/(.*?)/$', blog_views.archive_tag),

    url(r'^admin/', include(admin.site.urls)),
    url(r'^static/', static_redirect),
]
