from django.core.management.base import BaseCommand
from django.utils import timezone

from blog.models import Beat, Blogmark, Entry, Note, Quotation


class Command(BaseCommand):
    help = "Populate database with one of every content type for development"

    def handle(self, *args, **options):
        now = timezone.now()

        entry, created = Entry.objects.get_or_create(
            slug="demo-entry",
            defaults={
                "title": "Demo Entry",
                "body": "This is a **demo entry** for local development.",
                "created": now,
            },
        )
        self.stdout.write(f"Entry: {'created' if created else 'exists'}")

        blogmark, created = Blogmark.objects.get_or_create(
            slug="demo-blogmark",
            defaults={
                "link_url": "https://example.com/demo",
                "link_title": "Demo Blogmark Link",
                "commentary": "A demo blogmark for local development.",
                "created": now,
            },
        )
        self.stdout.write(f"Blogmark: {'created' if created else 'exists'}")

        quotation, created = Quotation.objects.get_or_create(
            slug="demo-quotation",
            defaults={
                "quotation": "The best way to predict the future is to invent it.",
                "source": "Alan Kay",
                "source_url": "https://example.com/quote",
                "created": now,
            },
        )
        self.stdout.write(f"Quotation: {'created' if created else 'exists'}")

        note, created = Note.objects.get_or_create(
            slug="demo-note",
            defaults={
                "body": "This is a demo note for local development.",
                "created": now,
            },
        )
        self.stdout.write(f"Note: {'created' if created else 'exists'}")

        for bt_value, bt_label in Beat.BeatType.choices:
            beat, created = Beat.objects.get_or_create(
                slug=f"demo-beat-{bt_value}",
                defaults={
                    "beat_type": bt_value,
                    "title": f"Demo {bt_label}",
                    "url": f"https://example.com/beat/{bt_value}",
                    "commentary": f"A demo {bt_label.lower()} beat.",
                    "created": now,
                },
            )
            self.stdout.write(f"Beat ({bt_label}): {'created' if created else 'exists'}")

        self.stdout.write(self.style.SUCCESS("Demo data populated."))
