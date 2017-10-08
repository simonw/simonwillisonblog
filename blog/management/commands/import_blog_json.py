from django.core.management.base import BaseCommand
from django.utils.timezone import utc
from blog.models import (
    Entry,
    Blogmark,
    Tag,
    Quotation,
)
import requests
from dateutil import parser


class Command(BaseCommand):
    help = """
        ./manage.py import_blog_json URL-to-JSON
    """

    def add_arguments(self, parser):
        parser.add_argument(
            '--url_to_json',
            action='store',
            dest='url_to_json',
            help='URL to JSON to import',
        )
        parser.add_argument(
            '--tag_with',
            action='store',
            dest='tag_with',
            default='recovered',
            help='Tag to apply to all imported items',
        )

    def handle(self, *args, **kwargs):
        url_to_json = kwargs['url_to_json']
        tag_with = kwargs['tag_with']
        tag_with_tag = Tag.objects.get_or_create(tag=tag_with)[0]
        for item in requests.get(url_to_json).json():
            created = parser.parse(item['datetime']).replace(tzinfo=utc)
            slug = item['slug']
            # First sanity check this does not exist already with
            # a slug that is in a different case
            skipit = False
            for klass in (Entry, Quotation, Blogmark):
                matches = list(klass.objects.filter(
                    created__year=created.year,
                    created__month=created.month,
                    created__day=created.day,
                    slug__iexact=slug,
                ))
                if matches:
                    print 'Found match for %s: %s / %s : %s' % (
                        klass, created, slug, matches
                    )
                    skipit = True
                    break
            if skipit:
                continue

            if item['type'] == 'entry':
                obj = Entry.objects.create(
                    body=item['body'],
                    title=item['title'],
                    created=created,
                    slug=slug,
                    metadata=item,
                )
            elif item['type'] == 'quotation':
                obj = Quotation.objects.create(
                    quotation=item['quotation'],
                    source=item['source'],
                    source_url=item['source_url'],
                    created=created,
                    slug=slug,
                    metadata=item,
                )
            elif item['type'] == 'blogmark':
                obj = Blogmark.objects.create(
                    slug=slug,
                    link_url=item['link_url'],
                    link_title=item['link_title'],
                    via_url=item['via_url'],
                    via_title=item['via_title'],
                    commentary=item['commentary'] or '',
                    created=created,
                    metadata=item,
                )
            else:
                assert False, 'type should be known, %s' % item['type']
            for tag in item['tags']:
                t = Tag.objects.get_or_create(tag=tag)[0]
                obj.tags.add(t)
            obj.tags.add(tag_with_tag)
            print obj, obj.get_absolute_url()
