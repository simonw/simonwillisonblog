from django.core.management.base import BaseCommand
from blog.models import Entry, Blogmark, Quotation, Newsletter


class Command(BaseCommand):
    help = "Re-indexes all entries, blogmarks, quotations, and newsletters"

    def handle(self, *args, **kwargs):
        for klass in (Entry, Blogmark, Quotation, Newsletter):
            i = 0
            objects = klass.objects.all()
            if klass != Newsletter:
                objects = objects.prefetch_related("tags")
            for obj in objects:
                obj.save()
                i += 1
                if i % 100 == 0:
                    print(klass, i)
