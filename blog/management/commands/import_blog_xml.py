from optparse import make_option
from django.conf import settings
from django.core.management.base import BaseCommand
from blog.models import (
    Entry,
    Blogmark,
    Tag,
    Quotation,
)
from xml.etree import ElementTree as ET
import os

def iter_rows(filepath):
    # Iterate over rows in a SequelPro XML dump
    et = ET.parse(open(filepath))
    for row in et.findall('database/table_data/row'):
        d = {}
        for field in row.findall('field'):
            d[field.attrib['name']] = field.text
        yield d


class Command(BaseCommand):
    help = """
        ./manage.py import_blog_xml 
    """
    option_list = BaseCommand.option_list + (
        make_option('--xmldir',
            dest='xmldir',
            type='str',
            help='Directory where the XML files live',
            default=os.path.join(settings.BASE_DIR, '../old-import-xml')
        ),
    )

    def handle(self, *args, **kwargs):
        xmldir = kwargs['xmldir']
        # First create tags
        for row in iter_rows(os.path.join(xmldir, 'blog_tag.xml')):
            Tag.objects.get_or_create(tag = row['tag'])

        # Now do entries
        for row in iter_rows(os.path.join(xmldir, 'blog_entry.xml')):
            entry, created = Entry.objects.get_or_create(id = row['id'], defaults=dict(
                body = row['body'],
                created = row['created'],
                title = row['title'],
                slug = row['slug'],
            ))
            print entry, created

        # Now associate entries with tags
        for row in iter_rows(os.path.join(xmldir, 'blog_entry_tags.xml')):
            entry_id = row['entry_id']
            tag = row['tag_id'] # actually a tag
            entry = Entry.objects.get(pk = entry_id)
            entry.tags.add(Tag.objects.get(tag = tag))

        # Next do blogmarks
        for row in iter_rows(os.path.join(xmldir, 'blog_blogmark.xml')):
            blogmark, created = Blogmark.objects.get_or_create(id = row['id'], defaults=dict(
                slug = row['slug'],
                link_url = row['link_url'],
                link_title = row['link_title'],
                via_url = row['via_url'],
                via_title = row['via_title'],
                commentary = row['commentary'] or '',
                created = row['created'],
            ))
        for row in iter_rows(os.path.join(xmldir, 'blog_blogmark_tags.xml')):
            blogmark_id = row['blogmark_id']
            tag = row['tag_id'] # actually a tag
            entry = Blogmark.objects.get(pk = blogmark_id)
            entry.tags.add(Tag.objects.get(tag = tag))

        # and now quotations
        for row in iter_rows(os.path.join(xmldir, 'blog_quotation.xml')):
            quotation, created = Quotation.objects.get_or_create(id = row['id'], defaults=dict(
                slug = row['slug'],
                quotation = row['quotation'],
                source = row['source'],
                source_url = row['source_url'],
                created = row['created'],
            ))

        for row in iter_rows(os.path.join(xmldir, 'blog_quotation_tags.xml')):
            quotation_id = row['quotation_id']
            tag = row['tag_id'] # actually a tag
            entry = Quotation.objects.get(pk = quotation_id)
            entry.tags.add(Tag.objects.get(tag = tag))
