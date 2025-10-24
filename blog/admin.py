from django.contrib import admin
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models.functions import Length
from django.db.models import F
from django import forms
from xml.etree import ElementTree
import re
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
)


def validate_no_empty_links_html(content, field_name="content"):
    """Check for empty href attributes in HTML anchor tags."""
    # Pattern matches: <a href="">, <a href=''>, <a href="" >, etc.
    html_pattern = r'<a\s+[^>]*href=(["\'])\s*\1'
    if re.search(html_pattern, content):
        raise forms.ValidationError(
            f'Found empty link in {field_name}: <a href="">. '
            'Please provide a URL or remove the link.'
        )


def validate_no_empty_links_markdown(content, field_name="content"):
    """Check for empty URLs in Markdown link syntax."""
    # Pattern matches: [text](), [text]( ), etc.
    markdown_pattern = r'\]\(\s*\)'
    if re.search(markdown_pattern, content):
        raise forms.ValidationError(
            f'Found empty link in {field_name}: [text](). '
            'Please provide a URL or remove the link.'
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
    class Meta:
        model = Entry
        fields = "__all__"

    def clean_body(self):
        # Ensure this is valid XML
        body = self.cleaned_data["body"]
        try:
            ElementTree.fromstring("<entry>%s</entry>" % body)
        except Exception as e:
            raise forms.ValidationError(str(e))
        # Check for empty HTML links
        validate_no_empty_links_html(body, "body")
        return body


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = "__all__"

    def clean_quotation(self):
        quotation = self.cleaned_data["quotation"]
        # Check for both HTML and Markdown empty links
        validate_no_empty_links_html(quotation, "quotation")
        validate_no_empty_links_markdown(quotation, "quotation")
        return quotation


class NoteForm(forms.ModelForm):
    class Meta:
        model = Note
        fields = "__all__"

    def clean_body(self):
        body = self.cleaned_data["body"]
        # Check for both HTML and Markdown empty links
        validate_no_empty_links_html(body, "body")
        validate_no_empty_links_markdown(body, "body")
        return body


class BlogmarkForm(forms.ModelForm):
    class Meta:
        model = Blogmark
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        commentary = cleaned_data.get("commentary", "")
        use_markdown = cleaned_data.get("use_markdown", False)

        if commentary and use_markdown:
            # Only check for empty links when markdown is enabled
            # (plain text mode doesn't render links)
            validate_no_empty_links_html(commentary, "commentary")
            validate_no_empty_links_markdown(commentary, "commentary")

        return cleaned_data


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
    form = QuotationForm
    search_fields = ("tags__tag", "quotation")
    list_display = ("__str__", "source", "created", "tag_summary", "is_draft")
    prepopulated_fields = {"slug": ("source",)}


@admin.register(Blogmark)
class BlogmarkAdmin(BaseAdmin):
    form = BlogmarkForm
    search_fields = ("tags__tag", "commentary")
    prepopulated_fields = {"slug": ("link_title",)}


@admin.register(Note)
class NoteAdmin(BaseAdmin):
    form = NoteForm
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
