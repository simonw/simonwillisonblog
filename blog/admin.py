from django.contrib import admin
from .models import Entry, Tag, Quotation, Blogmark

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
