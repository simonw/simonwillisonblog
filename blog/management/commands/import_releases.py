from django.core.management.base import BaseCommand

from blog.importers import import_releases


class Command(BaseCommand):
    help = "Import latest releases from a releases_cache.json URL as Beat objects with beat_type='release'"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a releases_cache.json file")

    def handle(self, *args, **options):
        result = import_releases(options["url"])
        self.stdout.write(
            "Created {} beats, skipped {} duplicates".format(
                result["created"], result["skipped"]
            )
        )
