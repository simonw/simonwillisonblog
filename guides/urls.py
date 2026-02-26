from django.urls import path, re_path
from . import views

urlpatterns = [
    path("guides/", views.guide_index),
    re_path(r"^guides/([\w-]+)\.atom$", views.guide_atom),
    re_path(r"^guides/([\w-]+)/$", views.guide_detail),
    re_path(r"^guides/([\w-]+)/([\w-]+)/$", views.chapter_detail),
    re_path(r"^guides/([\w-]+)/([\w-]+)/changes/$", views.chapter_changes),
]
