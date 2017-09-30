from django.core.management.base import BaseCommand
from django.db.models import Value, F, Func
from django.contrib.postgres.search import SearchVector

from blog.models import Entry, Blogmark, Quotation


class Command(BaseCommand):
    help = "Re-indexes all entries, blogmarks, quotations"

    def handle(self, *args, **kwargs):
        print 'entries', Entry.objects.update(search_document=entry_vector_fields_only)
        print 'blogmarks', Blogmark.objects.update(search_document=blogmark_vector_fields_only)
        print 'quotations', Quotation.objects.update(search_document=quotation_vector_fields_only)


def strip_tags_func(field):
    return Func(
        F(field), Value('<.*?>'), Value(''), Value('g'), function='regexp_replace'
    )

entry_vector_fields_only = (
    SearchVector('title', weight='A') +
    SearchVector(strip_tags_func('body'), weight='C')
)

blogmark_vector_fields_only = (
    SearchVector('link_title', weight='A') +
    SearchVector(strip_tags_func('commentary'), weight='C')
)

quotation_vector_fields_only = (
    SearchVector('source', weight='A') +
    SearchVector('quotation', weight='B')
)
