from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import ShortURL


class ShortURLTests(TestCase):
    def test_base32_ids(self):
        for pk, code in (
            (1, "vj"),
            (13, "vv"),
            (14, "100"),
            (2**63 - 1, "80000000000vh"),
        ):
            with self.subTest(pk=pk):
                obj = ShortURL(pk=pk, url="https://example.com/")
                self.assertEqual(obj.short_id, code)
                self.assertEqual(obj.get_absolute_url(), "/u/" + code)

    def test_redirect_and_edit_destination(self):
        obj = ShortURL.objects.create(url="https://example.com/?a=1&b=2#fragment")
        self.assertRedirects(
            self.client.get(obj.get_absolute_url()),
            obj.url,
            fetch_redirect_response=False,
        )
        obj.url = "https://example.org/updated"
        obj.save()
        self.assertRedirects(
            self.client.get("/u/" + obj.short_id.upper()),
            obj.url,
            fetch_redirect_response=False,
        )

    def test_invalid_and_missing_ids(self):
        for code in ("0", "vi", "vj", "xyz", "-1", "vvvvvvvvvvvvv", "1" * 100):
            with self.subTest(code=code):
                self.assertEqual(self.client.get("/u/" + code).status_code, 404)

    def test_long_url(self):
        obj = ShortURL(url="https://example.com/?q=" + "a" * 10_000)
        obj.full_clean()
        obj.save()
        obj.refresh_from_db()
        self.assertRedirects(
            self.client.get(obj.get_absolute_url()),
            obj.url,
            fetch_redirect_response=False,
        )

    def test_url_validation(self):
        for url in (
            "not a URL",
            "javascript:alert(1)",
            "https://example.com/" + "a" * 100_000,
        ):
            with self.subTest(url=url[:40]):
                with self.assertRaises(ValidationError):
                    ShortURL(url=url).full_clean()


class ShortURLAdminTests(TestCase):
    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_superuser(
                "admin", "admin@example.com", "password"
            )
        )

    def test_add_long_url_without_description(self):
        url = "https://example.com/?q=" + "a" * 10_000
        response = self.client.post(
            reverse("admin:shortener_shorturl_add"),
            {"url": url, "description": "", "_save": "Save"},
        )
        self.assertEqual(response.status_code, 302)
        obj = ShortURL.objects.get()
        self.assertEqual(obj.url, url)
        self.assertEqual(obj.description, "")
        response = self.client.get(
            reverse("admin:shortener_shorturl_change", args=[obj.pk])
        )
        self.assertContains(response, obj.get_absolute_url())

    def test_list_and_search(self):
        obj = ShortURL.objects.create(
            url="https://example.com/", description="Reference link"
        )
        response = self.client.get(
            reverse("admin:shortener_shorturl_changelist"), {"q": "Reference"}
        )
        self.assertContains(response, obj.get_absolute_url())
        self.assertContains(response, "Reference link")
