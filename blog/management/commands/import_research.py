from django.core.management.base import BaseCommand

from blog.importers import import_research


class Command(BaseCommand):
    help = "Import research projects from a README.md URL as Beat objects with beat_type='research'"

    def add_arguments(self, parser):
        parser.add_argument(
            "url",
            help="URL to a README.md with ### [name](url) (YYYY-MM-DD) entries",
        )

    def handle(self, *args, **options):
        result = import_research(options["url"])
        self.stdout.write(
            "Created {}, updated {}, skipped {}".format(
                result["created"], result["updated"], result["skipped"]
            )
        )
