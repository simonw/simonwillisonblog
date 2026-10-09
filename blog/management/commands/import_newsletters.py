import subprocess
from xml.etree.ElementTree import ParseError

import requests
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from blog.newsletter_importers import (
    SUBSTACK_FEED,
    import_monthly,
    import_substack,
    import_substack_archive,
)


class Command(BaseCommand):
    help = "Import Substack listing metadata and/or public monthly newsletters."

    def add_arguments(self, parser):
        parser.add_argument("source", choices=("substack", "monthly", "all"))
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--feed-url", default=SUBSTACK_FEED)
        parser.add_argument(
            "--substack-archive",
            action="store_true",
            help="Backfill all Substack issues instead of using RSS.",
        )
        parser.add_argument(
            "--private-checkout",
            help="Optional private monthly checkout: import titles, send dates, and links for unreleased issues only.",
        )
        parser.add_argument(
            "--monthly-checkout",
            help="Existing checkout of the public monthly-newsletter-archive repository.",
        )

    def handle(self, *args, **options):
        sources = (
            ("monthly", "substack")
            if options["source"] == "all"
            else (options["source"],)
        )
        for source in sources:
            try:
                if source == "monthly":
                    counts = import_monthly(
                        options["monthly_checkout"],
                        options["dry_run"],
                        options["private_checkout"],
                    )
                elif options["substack_archive"]:
                    counts = import_substack_archive(options["dry_run"])
                else:
                    counts = import_substack(options["feed_url"], options["dry_run"])
            except (
                requests.RequestException,
                subprocess.SubprocessError,
                ValueError,
                KeyError,
                TypeError,
                ParseError,
                ValidationError,
            ) as ex:
                raise CommandError(f"{source} import failed: {ex}") from ex
            prefix = "Dry run: " if options["dry_run"] else ""
            self.stdout.write(
                f"{prefix}{source}: created {counts['created']}, updated {counts['updated']}, skipped {counts['skipped']}"
            )
            if source == "substack" and not options["substack_archive"]:
                self.stdout.write(
                    "The RSS feed contains recent issues only, not the full archive."
                )
