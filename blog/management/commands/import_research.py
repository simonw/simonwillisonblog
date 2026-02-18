import re
from datetime import datetime, timezone

import httpx
from django.core.management.base import BaseCommand

from blog.models import Beat
from ._beat_utils import truncate, unique_slug


class Command(BaseCommand):
    help = "Import research projects from a README.md URL as Beat objects with beat_type='research'"

    def add_arguments(self, parser):
        parser.add_argument("url", help="URL to a README.md with ### [name](url) (YYYY-MM-DD) entries")

    def handle(self, *args, **options):
        url = options["url"]
        response = httpx.get(url)
        response.raise_for_status()
        text = response.text

        # Pattern matches: ### [title](url) (YYYY-MM-DD)
        heading_pattern = re.compile(
            r"^### \[([^\]]+)\]\(([^)]+)\) \((\d{4}-\d{2}-\d{2})\)",
            re.MULTILINE,
        )

        matches = list(heading_pattern.finditer(text))
        created_count = 0
        updated_count = 0

        for i, match in enumerate(matches):
            title = match.group(1)
            project_url = match.group(2)
            if not project_url.endswith("#readme"):
                project_url += "#readme"
            date_str = match.group(3)
            created = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            import_ref = "research:{}".format(title)

            # Extract description: text between this heading and the next heading
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()

            # Take just the first paragraph (before any blank line or "Key findings:")
            first_para = body.split("\n\n")[0].strip()
            # Strip markdown links: [text](url) -> text
            first_para = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first_para)
            commentary = truncate(first_para)

            defaults = {
                "beat_type": "research",
                "title": title,
                "url": project_url,
                "slug": unique_slug(title, created, import_ref),
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
