from django.core.management.base import BaseCommand

from blog.importers import import_tils


class Command(BaseCommand):
    help = "Import TILs from til.simonwillison.net as Beat objects with beat_type='til'"

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            help="URL to the tils.json endpoint",
        )

    def handle(self, *args, **options):
        result = import_tils(options["url"])
        self.stdout.write(
            "Created {}, updated {}, skipped {}".format(
                result["created"], result["updated"], result["skipped"]
            )
        )
