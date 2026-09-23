from django.urls import re_path

from . import views

app_name = "shortener"

urlpatterns = [
    re_path(r"^(?P<short_id>[0-9a-vA-V]{1,13})$", views.redirect, name="redirect"),
]
