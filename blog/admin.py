from django.contrib import admin
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
    list_display = ('__unicode__', 'slug', 'created', 'tag_summary')
    
@admin.register(Entry)
class EntryAdmin(BaseAdmin):
    search_fields = ('tags__tag', 'title', 'body')

@admin.register(Quotation)
class QuotationAdmin(BaseAdmin):
    search_fields = ('tags__tag', 'quotation')

@admin.register(Blogmark)
class BlogmarkAdmin(BaseAdmin):
    search_fields = ('tags__tag', 'commentary')


admin.site.register(Tag)

admin.site.register(Comment,
    list_filter = (
        'created', 'visible_on_site', 'spam_status', 'content_type'
    ),
    search_fields = ('body', 'name', 'url', 'email', 'openid'),
    list_display = ('name', 'admin_summary', 'on_link', 'created',
        'ip_link', 'visible_on_site', 'spam_status_options'),
    list_display_links = ('name', 'admin_summary'),
    date_hierarchy = 'created'
)

