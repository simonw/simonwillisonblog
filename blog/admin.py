from django.contrib import admin
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models.functions import Length
from django.db.models import F
from django import forms
from django.http import HttpResponse, HttpResponseBadRequest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import path
from django.views.decorators.http import require_POST
from .replacements import create_replacement, publish_replacement
from xml.etree import ElementTree
from .models import (
    Beat,
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
    SponsorMessage,
)


class AutosaveAdminMixin:
    def view_on_site(self, obj):
        return obj.get_absolute_url()

    def log_change(self, request, obj, message):
        if request.POST.get("_autosave"):
            return
        return super().log_change(request, obj, message)

    def response_change(self, request, obj):
        if request.POST.get("_autosave"):
            return HttpResponse(status=204)
        return super().response_change(request, obj)


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


class ConvertToEntryAdminMixin:
    def get_urls(self):
        return [
            path(
                "<int:object_id>/convert-to-entry/",
                self.admin_site.admin_view(require_POST(self.convert_to_entry)),
                name=f"blog_{self.model._meta.model_name}_convert_to_entry",
            )
        ] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        context = dict(extra_context or {})
        context["can_convert_to_entry"] = (
            obj is not None
            and self.has_change_permission(request, obj)
            and self.admin_site._registry[Entry].has_add_permission(request)
            and self.admin_site._registry[Entry].has_change_permission(request)
        )
        return super().change_view(request, object_id, form_url, context)

    def convert_to_entry(self, request, object_id):
        try:
            with transaction.atomic():
                source = get_object_or_404(
                    self.get_queryset(request).select_for_update(), pk=object_id
                )
                entry_admin = self.admin_site._registry[Entry]
                if not (
                    self.has_change_permission(request, source)
                    and entry_admin.has_add_permission(request)
                    and entry_admin.has_change_permission(request)
                ):
                    raise PermissionDenied
                entry, created = create_replacement(source)
                if created:
                    entry_admin.log_addition(
                        request, entry, "Created replacement draft from " + str(source)
                    )
                    self.log_change(
                        request, source, f"Created replacement entry {entry.pk}"
                    )
                self.message_user(
                    request,
                    "Replacement draft ready. Edit and save it, then use Go live with replacement.",
                )
                return redirect("admin:blog_entry_change", entry.pk)
        except (ValidationError, ElementTree.ParseError) as ex:
            return HttpResponseBadRequest(str(ex), content_type="text/plain")


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
class EntryAdmin(AutosaveAdminMixin, BaseAdmin):
    form = MyEntryForm
    prepopulated_fields = {"slug": ("title",)}
    search_fields = ("title", "body")
    list_filter = ("created", "series")

    def get_urls(self):
        return [
            path(
                "<int:object_id>/go-live-with-replacement/",
                self.admin_site.admin_view(require_POST(self.go_live_with_replacement)),
                name="blog_entry_go_live_with_replacement",
            )
        ] + super().get_urls()

    def change_view(self, request, object_id, form_url="", extra_context=None):
        obj = self.get_object(request, object_id)
        context = dict(extra_context or {})
        source = (obj.replacement_blogmark or obj.replacement_note) if obj else None
        context["can_go_live_with_replacement"] = bool(
            source
            and obj.is_draft
            and self.has_change_permission(request, obj)
            and self.admin_site._registry[type(source)].has_change_permission(
                request, source
            )
        )
        return super().change_view(request, object_id, form_url, context)

    def go_live_with_replacement(self, request, object_id):
        try:
            with transaction.atomic():
                entry = get_object_or_404(
                    Entry.objects.select_for_update(), pk=object_id
                )
                if not self.has_change_permission(request, entry):
                    raise PermissionDenied
                source = entry.replacement_blogmark or entry.replacement_note
                if source is None:
                    raise ValidationError(
                        "This entry does not replace a blogmark or note."
                    )
                source = type(source).objects.select_for_update().get(pk=source.pk)
                source_admin = self.admin_site._registry[type(source)]
                if not source_admin.has_change_permission(request, source):
                    raise PermissionDenied
                publish_replacement(entry, source)
                self.log_change(request, entry, "Went live with replacement")
                source_admin.log_change(
                    request, source, f"Replaced by entry {entry.pk}; moved to draft"
                )
                self.message_user(
                    request, "Replacement is live. The original item is now a draft."
                )
                return redirect("admin:blog_entry_change", entry.pk)
        except ValidationError as ex:
            return HttpResponseBadRequest(str(ex), content_type="text/plain")


@admin.register(LiveUpdate)
class LiveUpdateAdmin(admin.ModelAdmin):
    raw_id_fields = ("entry",)


@admin.register(Quotation)
class QuotationAdmin(AutosaveAdminMixin, BaseAdmin):
    search_fields = ("tags__tag", "quotation")
    list_display = ("__str__", "source", "created", "tag_summary", "is_draft")
    prepopulated_fields = {"slug": ("source",)}


@admin.register(Blogmark)
class BlogmarkAdmin(ConvertToEntryAdminMixin, AutosaveAdminMixin, BaseAdmin):
    search_fields = ("tags__tag", "commentary")
    prepopulated_fields = {"slug": ("link_title",)}


@admin.register(Note)
class NoteAdmin(ConvertToEntryAdminMixin, AutosaveAdminMixin, BaseAdmin):
    search_fields = ("tags__tag", "body")
    list_display = ("__str__", "created", "tag_summary", "is_draft")


class BeatAdminForm(forms.ModelForm):
    comment_site = forms.CharField(
        required=False,
        label="Comment: site name",
        help_text='For comment beats, e.g. "Hacker News"',
    )
    comment_thread_url = forms.URLField(
        required=False,
        label="Comment: thread URL",
        assume_scheme="https",
        help_text=(
            "For comment beats: the thread the comment was posted on. "
            "The url field should be the permalink to the comment itself, "
            "title the thread title, and the full comment text (markdown) "
            "goes in note"
        ),
    )

    class Meta:
        model = Beat
        exclude = ("search_document",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # import_ref is only set by the importers; beats created by hand
        # (e.g. comment beats) don't have one. The admin drops this field
        # entirely (it is in readonly_fields), so it may be absent here.
        if "import_ref" in self.fields:
            self.fields["import_ref"].required = False
        metadata = (self.instance.metadata or {}) if self.instance.pk else {}
        self.fields["comment_site"].initial = metadata.get("comment_site", "")
        self.fields["comment_thread_url"].initial = metadata.get("thread_url", "")

    def clean_import_ref(self):
        # Normalize "" to None so the unique constraint only applies to
        # real import refs
        return self.cleaned_data.get("import_ref") or None

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("beat_type") == Beat.BeatType.COMMENT:
            if not cleaned.get("comment_site"):
                self.add_error("comment_site", "Required for comment beats")
            if not cleaned.get("comment_thread_url"):
                self.add_error("comment_thread_url", "Required for comment beats")
            metadata = dict(cleaned.get("metadata") or {})
            metadata["comment_site"] = cleaned.get("comment_site", "")
            metadata["thread_url"] = cleaned.get("comment_thread_url", "")
            cleaned["metadata"] = metadata
        return cleaned


@admin.register(Beat)
class BeatAdmin(BaseAdmin):
    form = BeatAdminForm
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
                queryset.search(search_term, lookup="istartswith")
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
