from django.conf.urls import patterns, include, url
from django.conf import settings
from django.contrib import admin
from django.conf.urls.static import static

from blog import views as blog_views

urlpatterns = patterns('',
    (r'^$', blog_views.index),
    (r'^(\d{4})/$', blog_views.archive_year),
    (r'^(\d{4})/(\w{3})/$', blog_views.archive_month),
    (r'^(\d{4})/(\w{3})/(\d{1,2})/$', blog_views.archive_day),
    (r'^(\d{4})/(\w{3})/(\d{1,2})/(\w+)/$', blog_views.archive_item),

    (r'^write/$', blog_views.write),
    #(r'^about/$', blog_views.about),
    (r'^tags/$', blog_views.tag_index),
    (r'^tags/(.*?)/$', blog_views.archive_tag),

    url(r'^admin/', include(admin.site.urls)),
) + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
