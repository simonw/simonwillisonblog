from django.core.management.base import BaseCommand
from blog.models import Entry, Blogmark, Quotation


class Command(BaseCommand):
    help = "Re-indexes all entries, blogmarks, quotations"

    def handle(self, *args, **kwargs):
        for klass in (Entry, Blogmark, Quotation):
            i = 0
            for obj in klass.objects.prefetch_related("tags").all():
                obj.save()
                i += 1
                if i % 100 == 0:
                    print(klass, i)
