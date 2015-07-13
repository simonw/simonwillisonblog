from django.contrib import admin
from .models import Entry, Tag, Quotation, Blogmark

admin.site.register(Entry, raw_id_fields=('tags',))
admin.site.register(Tag)
admin.site.register(Quotation)
admin.site.register(Blogmark)
