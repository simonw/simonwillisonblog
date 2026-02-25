from django.contrib import admin
from blog.admin import BaseAdmin
from .models import Guide, GuideSection, Chapter, ChapterChange


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_draft")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(GuideSection)
class GuideSectionAdmin(admin.ModelAdmin):
    list_display = ("title", "guide", "order")
    list_filter = ("guide",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Chapter)
class ChapterAdmin(BaseAdmin):
    list_display = ("title", "guide", "section", "order", "is_draft")
    list_filter = ("guide", "section", "is_draft")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(ChapterChange)
class ChapterChangeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "chapter", "created", "is_notable")
    list_filter = ("is_notable", "created")
    readonly_fields = ("chapter", "created", "title", "body", "is_draft")
    fields = (
        "chapter",
        "created",
        "title",
        "body",
        "is_draft",
        "is_notable",
        "change_note",
    )
    date_hierarchy = "created"

    def has_add_permission(self, request):
        return False
