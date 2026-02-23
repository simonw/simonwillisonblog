from django.contrib import admin
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models.functions import Length
from django.db.models import F
from django import forms
from xml.etree import ElementTree
from .models import (
    Beat,
    Chapter,
    Entry,
    Guide,
    Tag,
    Quotation,
    Blogmark,
    Comment,
    Note,
    Series,
    PreviousTagName,
    LiveUpdate,
    TagMerge,
    SponsorMessage,
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
        wrapped = "<entry>%s</entry>" % body
        try:
            ElementTree.fromstring(wrapped)
        except ElementTree.ParseError as e:
            msg = str(e)
            # ParseError format: "message: line X, column Y"
            import re

            match = re.search(r"line (\d+), column (\d+)", msg)
            if match:
                line_no = int(match.group(1))
                col_no = int(match.group(2))
                lines = wrapped.split("\n")
                if 0 < line_no <= len(lines):
                    problem_line = lines[line_no - 1]
                    # Show context around the error (60 chars either side)
                    start = max(0, col_no - 60)
                    end = min(len(problem_line), col_no + 60)
                    snippet = problem_line[start:end]
                    pointer_pos = min(col_no - start - 1, len(snippet) - 1)
                    pointer = " " * pointer_pos + "^"
                    # Check for common issues
                    hints = []
                    # Check for unescaped & near the error
                    nearby = problem_line[max(0, col_no - 10) : col_no + 10]
                    if "&" in nearby and "&amp;" not in nearby:
                        hints.append("Hint: Found '&' near error - use '&amp;' in URLs")
                    error_parts = [msg, "", "Context:", snippet, pointer]
                    if hints:
                        error_parts.extend(["", *hints])
                    raise forms.ValidationError("\n".join(error_parts))
            raise forms.ValidationError(msg)
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


@admin.register(Beat)
class BeatAdmin(BaseAdmin):
    search_fields = ("tags__tag", "title", "commentary")
    prepopulated_fields = {"slug": ("title",)}
    list_display = ("__str__", "beat_type", "created", "tag_summary", "is_draft")
    list_filter = ("created", "is_draft", "beat_type")


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


class ChapterInline(admin.TabularInline):
    model = Chapter
    fields = ("order", "title", "slug", "is_draft")
    prepopulated_fields = {"slug": ("title",)}
    extra = 1


@admin.register(Guide)
class GuideAdmin(admin.ModelAdmin):
    list_display = ("title", "slug", "is_draft")
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ChapterInline]


@admin.register(Chapter)
class ChapterAdmin(BaseAdmin):
    list_display = ("title", "guide", "order", "is_draft")
    list_filter = ("guide", "is_draft")
    prepopulated_fields = {"slug": ("title",)}


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
        from django.utils.html import escape, mark_safe

        if not obj.details:
            return "-"

        details = obj.details
        html_parts = ["<div style='font-family: monospace;'>"]

        for content_type, data in details.items():
            escaped_type = escape(content_type)
            # Handle new format with added/already_tagged
            if isinstance(data, dict) and "added" in data:
                added = data.get("added", [])
                already = data.get("already_tagged", [])
                total = len(added) + len(already)
                if total:
                    html_parts.append(
                        f"<p><strong>{escaped_type}:</strong> {total} item(s)"
                    )
                    if added:
                        html_parts.append(
                            f"<br><small>Tag added ({len(added)}): "
                            f"{', '.join(str(pk) for pk in added)}</small>"
                        )
                    if already:
                        html_parts.append(
                            f"<br><small>Already tagged ({len(already)}): "
                            f"{', '.join(str(pk) for pk in already)}</small>"
                        )
                    html_parts.append("</p>")
            # Handle old format (list of pks) for backwards compatibility
            elif isinstance(data, list) and data:
                html_parts.append(
                    f"<p><strong>{escaped_type}:</strong> {len(data)} item(s)<br>"
                    f"<small>IDs: {', '.join(str(pk) for pk in data)}</small></p>"
                )

        html_parts.append("</div>")
        return mark_safe("".join(html_parts))

    details_formatted.short_description = "Merge Details"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SponsorMessage)
class SponsorMessageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
        "display_from",
        "display_until",
        "color_scheme",
    )
    list_filter = ("is_active", "color_scheme")
    search_fields = ("name", "message", "notes")
