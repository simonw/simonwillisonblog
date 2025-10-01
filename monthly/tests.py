from datetime import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Newsletter


class MonthlyViewsTests(TestCase):
    def setUp(self):
        self.newsletter_old = Newsletter.objects.create(
            subject="Older edition",
            body="Old body",
            sent_at=timezone.make_aware(datetime(2024, 1, 31, 12, 0, 0)),
        )
        self.newsletter_new = Newsletter.objects.create(
            subject="Newer edition",
            body="New **body**",
            sent_at=timezone.make_aware(datetime(2024, 2, 29, 12, 0, 0)),
        )

    def test_monthly_index_lists_newsletters(self):
        response = self.client.get(reverse("monthly:index"))
        self.assertEqual(response.status_code, 200)
        newsletters = list(response.context["newsletters"])
        self.assertEqual(newsletters, [self.newsletter_new, self.newsletter_old])
        self.assertContains(response, "Newer edition")
        self.assertContains(response, "Older edition")
        self.assertContains(
            response,
            reverse("monthly:detail", kwargs={"year": 2024, "month": "02"}),
        )

    def test_newsletter_detail_renders_content(self):
        response = self.client.get(
            reverse("monthly:detail", kwargs={"year": 2024, "month": "02"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["newsletter"], self.newsletter_new)
        self.assertContains(response, "Newer edition")
        self.assertContains(response, "<strong>body</strong>", html=True)

    def test_newsletter_detail_missing(self):
        response = self.client.get(
            reverse("monthly:detail", kwargs={"year": 2023, "month": "12"})
        )
        self.assertEqual(response.status_code, 404)
