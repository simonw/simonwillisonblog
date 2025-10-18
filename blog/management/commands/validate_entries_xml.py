from django.core.management.base import BaseCommand
from blog.models import Entry


class Command(BaseCommand):
    help = "Spits out list of entries with invalid XML"

    def handle(self, *args, **kwargs):
        for entry in Entry.objects.all():
            if entry.use_markdown:
                continue
            try:
                from xml.etree import ElementTree

                ElementTree.fromstring("<entry>%s</entry>" % entry.body.encode("utf8"))
            except Exception as e:
                print(e)
                print(entry.title)
                print("https://simonwillison.com/admin/blog/entry/%d/" % entry.pk)
                print()
