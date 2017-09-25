from django.conf.urls import include, url
from django.conf import settings
from django.contrib import admin
from django.conf.urls.static import static

from blog import views as blog_views

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
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
