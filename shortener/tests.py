import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects

from .models import ShortURL


@pytest.mark.django_db
class TestShortURL:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

    def test_base32_ids(self, subtests):
        for pk, code in (
            (1, "vj"),
            (13, "vv"),
            (14, "100"),
            (2**63 - 1, "80000000000vh"),
        ):
            with subtests.test(pk=pk):
                obj = ShortURL(pk=pk, url="https://example.com/")
                assert obj.short_id == code
                assert obj.get_absolute_url() == "/u/" + code

    def test_redirect_and_edit_destination(self):
        obj = ShortURL.objects.create(url="https://example.com/?a=1&b=2#fragment")
        assertRedirects(
            self.client.get(obj.get_absolute_url()),
            obj.url,
            fetch_redirect_response=False,
        )
        obj.url = "https://example.org/updated"
        obj.save()
        assertRedirects(
            self.client.get("/u/" + obj.short_id.upper()),
            obj.url,
            fetch_redirect_response=False,
        )

    def test_invalid_and_missing_ids(self, subtests):
        for code in ("0", "vi", "vj", "xyz", "-1", "vvvvvvvvvvvvv", "1" * 100):
            with subtests.test(code=code):
                assert self.client.get("/u/" + code).status_code == 404

    def test_long_url(self):
        obj = ShortURL(url="https://example.com/?q=" + "a" * 10_000)
        obj.full_clean()
        obj.save()
        obj.refresh_from_db()
        assertRedirects(
            self.client.get(obj.get_absolute_url()),
            obj.url,
            fetch_redirect_response=False,
        )

    def test_url_validation(self, subtests):
        for url in (
            "not a URL",
            "javascript:alert(1)",
            "https://example.com/" + "a" * 100_000,
        ):
            with subtests.test(url=url[:40]):
                with pytest.raises(ValidationError):
                    ShortURL(url=url).full_clean()


@pytest.mark.django_db
class TestShortURLAdmin:
    @pytest.fixture(autouse=True)
    def setup(self, client, db):
        self.client = client
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
        assert response.status_code == 302
        obj = ShortURL.objects.get()
        assert obj.url == url
        assert obj.description == ""
        response = self.client.get(
            reverse("admin:shortener_shorturl_change", args=[obj.pk])
        )
        assertContains(response, obj.get_absolute_url())

    def test_list_and_search(self):
        obj = ShortURL.objects.create(
            url="https://example.com/", description="Reference link"
        )
        response = self.client.get(
            reverse("admin:shortener_shorturl_changelist"), {"q": "Reference"}
        )
        assertContains(response, obj.get_absolute_url())
        assertContains(response, "Reference link")
