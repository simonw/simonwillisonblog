from django.urls import path, re_path

from . import views

app_name = "monthly"

urlpatterns = [
    path("", views.monthly_index, name="index"),
    re_path(r"^(?P<year>\d{4})-(?P<month>\d{2})/$", views.newsletter_detail, name="detail"),
]
