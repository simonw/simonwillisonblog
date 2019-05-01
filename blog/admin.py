from django.contrib import admin
from django.db.models.functions import Length
from django import forms
from xml.etree import ElementTree
from .models import (
    Entry,
    Tag,
    Quotation,
    Blogmark,
    Comment
)


class BaseAdmin(admin.ModelAdmin):
    date_hierarchy = 'created'
    raw_id_fields = ('tags',)
    list_display = ('__str__', 'slug', 'created', 'tag_summary')
    autocomplete_fields = ('tags',)
    readonly_fields = ('search_document', 'import_ref')


class MyEntryForm(forms.ModelForm):
    def clean_body(self):
        # Ensure this is valid XML
        body = self.cleaned_data['body']
        try:
            ElementTree.fromstring(
                '<entry>%s</entry>' % body
            )
        except Exception as e:
            raise forms.ValidationError(str(e))
        return body


@admin.register(Entry)
class EntryAdmin(BaseAdmin):
    search_fields = ('tags__tag', 'title', 'body')
    form = MyEntryForm
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Quotation)
class QuotationAdmin(BaseAdmin):
    search_fields = ('tags__tag', 'quotation')
    prepopulated_fields = {'slug': ('source',)}


@admin.register(Blogmark)
class BlogmarkAdmin(BaseAdmin):
    search_fields = ('tags__tag', 'commentary')
    prepopulated_fields = {'slug': ('link_title',)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    search_fields = ('tag',)

    def get_search_results(self, request, queryset, search_term):
        search_term = search_term.strip()
        if search_term:
            return queryset.filter(
                tag__startswith=search_term
            ).annotate(
                tag_length=Length('tag')
            ).order_by('tag_length'), False
        else:
            return queryset.none(), False


admin.site.register(Comment,
    list_filter=(
        'created', 'visible_on_site', 'spam_status', 'content_type'
    ),
    search_fields=('body', 'name', 'url', 'email', 'openid'),
    list_display=('name', 'admin_summary', 'on_link', 'created',
        'ip_link', 'visible_on_site', 'spam_status_options'),
    list_display_links=('name', 'admin_summary'),
    date_hierarchy='created'
)
