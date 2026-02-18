import httpx
from dateutil.parser import parse as parse_datetime
from django.core.management.base import BaseCommand

from blog.models import Beat
from ._beat_utils import truncate, unique_slug


class Command(BaseCommand):
    help = "Import TILs from til.simonwillison.net as Beat objects with beat_type='til_new'"

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            help="URL to the tils.json endpoint",
        )

    def handle(self, *args, **options):
        url = options["url"]
        response = httpx.get(url)
        response.raise_for_status()
        tils = response.json()

        created_count = 0
        updated_count = 0

        for til in tils:
            topic = til["topic"]
            slug = til["slug"]
            import_ref = "til:{}/{}".format(topic, slug)
            til_url = "https://til.simonwillison.net/{}/{}".format(topic, slug)

            # Use first line of body as commentary, stripping markdown heading
            body = (til.get("body") or "").strip()
            first_line = body.split("\n")[0].strip()
            if first_line.startswith("# "):
                # Skip the title line, use next non-empty line
                lines = [l.strip() for l in body.split("\n")[1:] if l.strip()]
                first_line = lines[0] if lines else ""
            commentary = truncate(first_line)

            created = parse_datetime(til["created_utc"])
            defaults = {
                "beat_type": "til_new",
                "title": til["title"],
                "url": til_url,
                "slug": unique_slug(slug, created, import_ref),
                "created": created,
                "commentary": commentary,
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
