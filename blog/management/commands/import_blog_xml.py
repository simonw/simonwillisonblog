from django.conf import settings
from django.core.management.base import BaseCommand
from django.contrib.contenttypes.models import ContentType
from blog.models import (
    Entry,
    Blogmark,
    Tag,
    Quotation,
    Comment,
)
from xml.etree import ElementTree as ET
import os
import sys


def iter_rows(filepath):
    # Iterate over rows in a SequelPro XML dump
    et = ET.parse(open(filepath))
    for row in et.findall("database/table_data/row"):
        d = {}
        for field in row.findall("field"):
            d[field.attrib["name"]] = field.text
        yield d


class Command(BaseCommand):
    help = """
        ./manage.py import_blog_xml
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--xmldir",
            action="store",
            dest="xmldir",
            default=os.path.join(settings.BASE_DIR, "old-import-xml"),
            help="Directory where the XML files live",
        )

    def handle(self, *args, **kwargs):
        xmldir = kwargs["xmldir"]
        import_tags(xmldir)
        import_entries(xmldir)
        import_blogmarks(xmldir)
        import_quotations(xmldir)
        import_comments(xmldir)


def import_tags(xmldir):
    # First create tags
    for row in iter_rows(os.path.join(xmldir, "blog_tag.xml")):
        Tag.objects.get_or_create(tag=row["tag"])


def import_entries(xmldir):
    # Now do entries
    for row in iter_rows(os.path.join(xmldir, "blog_entry.xml")):
        entry, created = Entry.objects.get_or_create(
            id=row["id"],
            defaults=dict(
                body=row["body"],
                created=row["created"],
                title=row["title"],
                slug=row["slug"],
            ),
        )
        print(entry, created)

    # Now associate entries with tags
    for row in iter_rows(os.path.join(xmldir, "blog_entry_tags.xml")):
        entry_id = row["entry_id"]
        tag = row["tag_id"]  # actually a tag
        entry = Entry.objects.get(pk=entry_id)
        entry.tags.add(Tag.objects.get(tag=tag))


def import_blogmarks(xmldir):
    # Next do blogmarks
    for row in iter_rows(os.path.join(xmldir, "blog_blogmark.xml")):
        blogmark, created = Blogmark.objects.get_or_create(
            id=row["id"],
            defaults=dict(
                slug=row["slug"],
                link_url=row["link_url"],
                link_title=row["link_title"],
                via_url=row["via_url"],
                via_title=row["via_title"],
                commentary=row["commentary"] or "",
                created=row["created"],
            ),
        )
    for row in iter_rows(os.path.join(xmldir, "blog_blogmark_tags.xml")):
        blogmark_id = row["blogmark_id"]
        tag = row["tag_id"]  # actually a tag
        entry = Blogmark.objects.get(pk=blogmark_id)
        entry.tags.add(Tag.objects.get(tag=tag))


def import_quotations(xmldir):
    # and now quotations
    for row in iter_rows(os.path.join(xmldir, "blog_quotation.xml")):
        quotation, created = Quotation.objects.get_or_create(
            id=row["id"],
            defaults=dict(
                slug=row["slug"],
                quotation=row["quotation"],
                source=row["source"],
                source_url=row["source_url"],
                created=row["created"],
            ),
        )
    for row in iter_rows(os.path.join(xmldir, "blog_quotation_tags.xml")):
        quotation_id = row["quotation_id"]
        tag = row["tag_id"]  # actually a tag
        entry = Quotation.objects.get(pk=quotation_id)
        entry.tags.add(Tag.objects.get(tag=tag))


def import_comments(xmldir):
    # Finally... comments!
    # First we need to know what the old content_type IDs
    # should map to
    content_types_by_id = {}
    for row in iter_rows(os.path.join(xmldir, "django_content_type.xml")):
        content_types_by_id[row["id"]] = row

    content_type_models_by_name = {}
    for ct in ContentType.objects.filter(app_label="blog"):
        content_type_models_by_name[ct.model] = ct

    i = 0

    for row in iter_rows(os.path.join(xmldir, "blog_comment.xml")):
        #
        #         <row>
        #     <field name="id">31819</field>
        #     <field name="content_type_id">19</field>
        #     <field name="object_id">1503</field>
        #     <field name="body">http://videos.pass.as/index.html
        # http://www.full-length-movies.biz/index.html
        # http://download-movies.fw.nu/index.html
        # http://movies.isthebe.st/index.html</field>
        #     <field name="created">2005-10-11 21:29:24</field>
        #     <field name="name">xxx</field>
        #     <field name="url">http://movies.isthebe.st/index.html</field>
        #     <field name="email">-ana@ma-.com</field>
        #     <field name="openid" xsi:nil="true" />
        #     <field name="ip">80.82.59.156</field>
        #     <field name="spam_status">spam</field>
        #     <field name="visible_on_site">0</field>
        #     <field name="spam_reason" xsi:nil="true" />
        # </row>
        Comment.objects.get_or_create(
            id=row["id"],
            defaults=dict(
                content_type=content_type_models_by_name[
                    content_types_by_id[row["content_type_id"]]["model"]
                ],
                object_id=row["object_id"],
                body=row["body"],
                created=row["created"] + "Z",
                name=row["name"] or "",
                url=row["url"],
                email=row["email"],
                openid=row["openid"],
                ip=(row["ip"] or "0.0.0.0")
                .replace("xx.xx.xx.xx", "0.0.0.0")
                .replace("xxx.xxx.xxx.xxx", "0.0.0.0")
                .replace("unknown", "0.0.0.0"),
                spam_status=row["spam_status"],
                visible_on_site=row["visible_on_site"],
                spam_reason=row["spam_reason"] or "",
            ),
        )
        i += 1
        if i % 100 == 0:
            print(i)
            sys.stdout.flush()
