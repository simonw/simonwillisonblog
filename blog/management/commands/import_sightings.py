from django.core.management.base import BaseCommand

from blog.importers import import_sightings


class Command(BaseCommand):
    help = "Import iNaturalist sighting clumps from a JSON URL as Beat objects"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a clumps.json file")

    def handle(self, *args, **options):
        result = import_sightings(options["url"])
        self.stdout.write(
            "Created {}, updated {}, skipped {}".format(
                result["created"], result["updated"], result["skipped"]
            )
        )
