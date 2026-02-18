import httpx
from dateutil.parser import parse as parse_datetime
from django.core.management.base import BaseCommand

from blog.models import Beat


class Command(BaseCommand):
    help = "Import latest releases from a releases_cache.json URL as Beat objects with beat_type='release'"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a releases_cache.json file")

    def handle(self, *args, **options):
        url = options["url"]
        response = httpx.get(url)
        response.raise_for_status()
        releases = response.json()

        created_count = 0
        skipped_count = 0

        for repo_name, info in releases.items():
            version = info["release"]
            import_ref = "release:{}:{}".format(repo_name, version)

            if Beat.objects.filter(import_ref=import_ref).exists():
                skipped_count += 1
                continue

            title = "{} {}".format(repo_name, version)

            Beat.objects.create(
                beat_type="release",
                title=title,
                url=info["url"],
                slug=repo_name[:64],
                created=parse_datetime(info["published_at"]),
                import_ref=import_ref,
                commentary=info.get("description") or "",
            )
            created_count += 1

        self.stdout.write(
            "Created {} beats, skipped {} duplicates".format(
                created_count, skipped_count
            )
        )
