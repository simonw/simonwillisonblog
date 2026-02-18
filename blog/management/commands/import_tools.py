import httpx
from dateutil.parser import parse as parse_datetime
from django.core.management.base import BaseCommand

from blog.models import Beat


def truncate(text, max_length=500):
    if not text or len(text) <= max_length:
        return text or ""
    # Try to truncate at a sentence boundary
    truncated = text[: max_length - 1]
    last_period = truncated.rfind(". ")
    if last_period > max_length // 2:
        return truncated[: last_period + 1]
    return truncated.rsplit(" ", 1)[0] + "\u2026"


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
            defaults = {
                "beat_type": "tool",
                "title": tool["title"],
                "url": "https://tools.simonwillison.net{}".format(tool["url"]),
                "slug": tool["slug"][:64],
                "created": parse_datetime(tool["created"]),
                "commentary": truncate(tool.get("description") or ""),
            }

            _, created = Beat.objects.update_or_create(
                import_ref=import_ref, defaults=defaults
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            "Created {}, updated {}".format(created_count, updated_count)
        )
