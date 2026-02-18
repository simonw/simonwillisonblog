from django.core.management.base import BaseCommand

from blog.importers import import_tools


class Command(BaseCommand):
    help = "Import tools from a JSON URL as Beat objects with beat_type='tool'"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a JSON array of tool objects")

    def handle(self, *args, **options):
        result = import_tools(options["url"])
        self.stdout.write(
            "Created {}, updated {}, skipped {}".format(
                result["created"], result["updated"], result["skipped"]
            )
        )
