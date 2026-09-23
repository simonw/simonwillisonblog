from django.contrib import admin
from django.utils.html import format_html
from django.utils.text import Truncator

from .models import ShortURL


@admin.register(ShortURL)
class ShortURLAdmin(admin.ModelAdmin):
    list_display = ("short_link", "truncated_url", "description")
    list_display_links = ("truncated_url",)
    search_fields = ("url", "description")
    readonly_fields = ("short_link",)

    @admin.display(description="URL", ordering="url")
    def truncated_url(self, obj):
        return Truncator(obj.url).chars(100)

    @admin.display(description="Short URL")
    def short_link(self, obj):
        if not obj or not obj.pk:
            return "Save to generate a short URL."
        path = obj.get_absolute_url()
        return format_html('<a href="{}">{}</a>', path, path)
