from django.contrib import admin
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models.functions import Length
from django.db.models import F
from django import forms
from xml.etree import ElementTree
from .models import (
    Entry,
    Tag,
    Quotation,
    Blogmark,
    Comment,
    Note,
    Series,
    PreviousTagName,
    LiveUpdate,
    TagMerge,
)


class BaseAdmin(admin.ModelAdmin):
    date_hierarchy = "created"
    raw_id_fields = ("tags",)
    list_display = ("__str__", "slug", "created", "tag_summary", "is_draft")
    list_filter = ("created", "is_draft")
    autocomplete_fields = ("tags",)
    readonly_fields = ("import_ref",)
    exclude = ("search_document",)

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    def get_search_results(self, request, queryset, search_term):
        if not search_term:
            return super().get_search_results(request, queryset, search_term)
        query = SearchQuery(search_term, search_type="websearch")
        rank = SearchRank(F("search_document"), query)
        queryset = (
            queryset.annotate(rank=rank).filter(search_document=query).order_by("-rank")
        )
        return queryset, False


class MyEntryForm(forms.ModelForm):
    def clean_body(self):
        # Ensure this is valid XML
        body = self.cleaned_data["body"]
        try:
            ElementTree.fromstring("<entry>%s</entry>" % body)
        except Exception as e:
            raise forms.ValidationError(str(e))
        return body


@admin.register(Entry)
class EntryAdmin(BaseAdmin):
    form = MyEntryForm
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "body")
    list_filter = ("created", "series")


@admin.register(LiveUpdate)
class LiveUpdateAdmin(admin.ModelAdmin):
    raw_id_fields = ("entry",)


@admin.register(Quotation)
class QuotationAdmin(BaseAdmin):
    search_fields = ("tags__tag", "quotation")
    list_display = ("__str__", "source", "created", "tag_summary", "is_draft")
    prepopulated_fields = {"slug": ("source",)}


@admin.register(Blogmark)
class BlogmarkAdmin(BaseAdmin):
    search_fields = ("tags__tag", "commentary")
    prepopulated_fields = {"slug": ("link_title",)}


@admin.register(Note)
class NoteAdmin(BaseAdmin):
    search_fields = ("tags__tag", "body")
    list_display = ("__str__", "created", "tag_summary", "is_draft")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ("tag",)

    def get_search_results(self, request, queryset, search_term):
        search_term = search_term.strip()
        if search_term:
            return (
                queryset.filter(tag__istartswith=search_term)
                .annotate(tag_length=Length("tag"))
                .order_by("tag_length"),
                False,
            )
        else:
            return queryset.all(), False

    def save_model(self, request, obj, form, change):
        if change:
            old_obj = Tag.objects.get(pk=obj.pk)
            if old_obj.tag != obj.tag:
                PreviousTagName.objects.create(tag=obj, previous_name=old_obj.tag)
        super().save_model(request, obj, form, change)


admin.site.register(
    Comment,
    list_filter=("created", "visible_on_site", "spam_status", "content_type"),
    search_fields=("body", "name", "url", "email", "openid"),
    list_display=(
        "name",
        "admin_summary",
        "on_link",
        "created",
        "ip_link",
        "visible_on_site",
        "spam_status_options",
    ),
    list_display_links=("name", "admin_summary"),
    date_hierarchy="created",
)

admin.site.register(
    Series,
    list_display=(
        "title",
        "slug",
    ),
)


admin.site.register(
    PreviousTagName, raw_id_fields=("tag",), list_display=("previous_name", "tag")
)


@admin.register(TagMerge)
class TagMergeAdmin(admin.ModelAdmin):
    list_display = ("__str__", "source_tag_name", "destination_tag_name", "created")
    list_filter = ("created",)
    search_fields = ("source_tag_name", "destination_tag_name")
    readonly_fields = (
        "created",
        "source_tag_name",
        "destination_tag",
        "destination_tag_name",
        "details_formatted",
    )
    exclude = ("details",)
    date_hierarchy = "created"

    def details_formatted(self, obj):
        """Display the details JSON in a formatted way."""
        import json
        from django.utils.html import format_html

        if not obj.details:
            return "-"

        details = obj.details
        html_parts = ["<div style='font-family: monospace;'>"]

        for content_type, pks in details.items():
            if pks:
                html_parts.append(
                    f"<p><strong>{content_type}:</strong> {len(pks)} item(s)<br>"
                    f"<small>IDs: {', '.join(str(pk) for pk in pks)}</small></p>"
                )

        html_parts.append("</div>")
        return format_html("".join(html_parts))

    details_formatted.short_description = "Merge Details"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
