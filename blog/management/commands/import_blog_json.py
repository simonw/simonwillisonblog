from django.core.management.base import BaseCommand
from datetime import timezone
from blog.models import (
    Entry,
    Blogmark,
    Tag,
    Quotation,
)
import requests
from dateutil import parser
import json


class Command(BaseCommand):
    help = """
        ./manage.py import_blog_json URL-or-path-to-JSON
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "url_or_path_to_json",
            type=str,
            help="URL or path to JSON to import",
        )
        parser.add_argument(
            "--tag_with",
            action="store",
            dest="tag_with",
            default=False,
            help="Tag to apply to all imported items",
        )

    def handle(self, *args, **kwargs):
        url_or_path_to_json = kwargs["url_or_path_to_json"]
        tag_with = kwargs["tag_with"]
        tag_with_tag = None
        if tag_with:
            tag_with_tag = Tag.objects.get_or_create(tag=tag_with)[0]

        is_url = url_or_path_to_json.startswith(
            "http://"
        ) or url_or_path_to_json.startswith("https://")

        if is_url:
            items = requests.get(url_or_path_to_json).json()
        else:
            items = json.load(open(url_or_path_to_json))

        for item in items:
            created = parser.parse(item["datetime"]).replace(tzinfo=timezone.utc)
            was_created = False
            slug = item["slug"][:64].strip("-")
            if item["type"] == "entry":
                klass = Entry
                kwargs = dict(
                    body=item["body"],
                    title=item["title"],
                    created=created,
                    slug=slug,
                    metadata=item,
                )
            elif item["type"] == "quotation":
                klass = Quotation
                kwargs = dict(
                    quotation=item["quotation"],
                    source=item["source"],
                    source_url=item["source_url"],
                    created=created,
                    slug=slug,
                    metadata=item,
                )
            elif item["type"] == "blogmark":
                klass = Blogmark
                kwargs = dict(
                    slug=slug,
                    link_url=item["link_url"],
                    link_title=item["link_title"],
                    via_url=item.get("via_url") or "",
                    via_title=item.get("via_title") or "",
                    commentary=item["commentary"] or "",
                    created=created,
                    metadata=item,
                )
            else:
                assert False, "type should be known, %s" % item["type"]
            if item.get("import_ref"):
                obj, was_created = klass.objects.update_or_create(
                    import_ref=item["import_ref"], defaults=kwargs
                )
            else:
                obj = klass.objects.create(**kwargs)
            tags = [Tag.objects.get_or_create(tag=tag)[0] for tag in item["tags"]]
            if tag_with_tag:
                tags.append(tag_with_tag)
            obj.tags.set(tags)
            print(was_created, obj, obj.get_absolute_url())
