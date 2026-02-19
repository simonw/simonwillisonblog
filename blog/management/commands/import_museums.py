from django.core.management.base import BaseCommand

from blog.importers import import_museums


class Command(BaseCommand):
    help = "Import museums from a JSON URL as Beat objects with beat_type='museum'"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a museums.json file")

    def handle(self, *args, **options):
        result = import_museums(options["url"])
        self.stdout.write(
            "Created {}, updated {}, skipped {}".format(
                result["created"], result["updated"], result["skipped"]
            )
        )
