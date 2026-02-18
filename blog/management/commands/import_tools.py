import httpx
from dateutil.parser import parse as parse_datetime
from django.core.management.base import BaseCommand

from blog.models import Beat
from ._beat_utils import truncate, unique_slug


class Command(BaseCommand):
    help = "Import tools from a JSON URL as Beat objects with beat_type='tool'"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a JSON array of tool objects")

    def handle(self, *args, **options):
        url = options["url"]
        response = httpx.get(url)
        response.raise_for_status()
        tools = response.json()

        created_count = 0
        updated_count = 0

        for tool in tools:
            import_ref = "tool:{}".format(tool["filename"])
            created = parse_datetime(tool["created"])
            defaults = {
                "beat_type": "tool",
                "title": tool["title"],
                "url": "https://tools.simonwillison.net/colophon#{}".format(tool["filename"]),
                "slug": unique_slug(tool["slug"], created, import_ref),
                "created": created,
                "commentary": truncate(tool.get("description") or ""),
            }

            _, was_created = Beat.objects.update_or_create(
                import_ref=import_ref, defaults=defaults
            )
            if was_created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            "Created {}, updated {}".format(created_count, updated_count)
        )
