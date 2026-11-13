import datetime
import io
import json
import re
import warnings
from unittest.mock import Mock, patch

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchQuery
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from pytest_django.asserts import (
    assertContains,
    assertNotContains,
    assertRedirects,
    assertTemplateUsed,
)

from .models import Newsletter
from .newsletter_importers import (
    MONTHLY_RAW,
    import_monthly,
    import_substack,
    import_substack_archive,
    monthly_records,
    save_records,
    substack_archive_records,
    substack_records,
)

FEED = b"""<rss version="2.0"><channel><item>
<title>A &amp; B</title><link>https://simonw.substack.com/p/a-b</link>
<pubDate>Mon, 05 Oct 2026 17:16:45 GMT</pubDate>
<enclosure url="https://example.com/image.jpg" type="image/jpeg"/>
<description><![CDATA[Plus we&#8217;re discussing A &amp; B]]></description>
</item></channel></rss>"""


@pytest.mark.django_db
class TestNewsletter:
    @pytest.fixture(autouse=True)
    def setup(self, client, commit_callbacks):
        self.client = client
        self.commit_callbacks = commit_callbacks

    def sponsor(self, **overrides):
        fields = dict(
            kind=Newsletter.Kind.SPONSOR,
            title="Sponsor digest",
            slug="sponsor-digest",
            created=datetime.datetime(2026, 9, 4, tzinfo=datetime.timezone.utc),
            url="https://github.com/simonw/monthly-newsletter-archive/blob/main/2026-08-august.md",
            body="A **pangolin** story.",
            is_public=True,
        )
        fields.update(overrides)
        return Newsletter(**fields)

    def test_only_public_sponsor_content_is_indexed_and_unpublishing_clears_it(self):
        obj = self.sponsor()
        with self.commit_callbacks():
            obj.save()
        assert Newsletter.objects.filter(
            search_document=SearchQuery("pangolin")
        ).exists()
        for fields in (
            {"is_public": False},
            {"is_public": True, "is_draft": True},
            {"is_draft": False, "kind": Newsletter.Kind.SUBSTACK},
        ):
            for key, value in fields.items():
                setattr(obj, key, value)
            with self.commit_callbacks():
                obj.save()
            obj.refresh_from_db()
            assert obj.search_document is None

    def test_validation_separates_listing_and_public_body(self):
        obj = self.sponsor(is_public=False, body="")
        obj.full_clean()
        obj.is_public = True
        with pytest.raises(ValidationError):
            obj.full_clean()
        obj.kind = Newsletter.Kind.SUBSTACK
        obj.body = "Not metadata"
        with pytest.raises(ValidationError):
            obj.full_clean()

    def test_substack_import_is_repeatable_and_metadata_only(self):
        records = substack_records(FEED)
        assert save_records(records) == {"created": 1, "updated": 0, "skipped": 0}
        obj = Newsletter.objects.get()
        assert obj.title == "A & B"
        assert obj.subtitle == "Plus we’re discussing A & B"
        assert obj.card_image == "https://example.com/image.jpg"
        assert obj.body == ""
        assert obj.created.isoformat() == "2026-10-05T17:16:45+00:00"
        assert save_records(records)["skipped"] == 1
        obj.slug = "my-custom-slug"
        obj.is_draft = True
        obj.metadata["editor_note"] = "Keep this"
        obj.save()
        records[0]["title"] = "Updated title"
        records[0]["subtitle"] = "Updated subtitle"
        assert save_records(records)["updated"] == 1
        obj.refresh_from_db()
        assert obj.slug == "my-custom-slug"
        assert obj.subtitle == "Updated subtitle"
        assert obj.is_draft
        assert obj.metadata["editor_note"] == "Keep this"

    def test_optional_thumbnail_and_invalid_feed(self):
        records = substack_records(
            FEED.replace(
                b'<enclosure url="https://example.com/image.jpg" type="image/jpeg"/>',
                b"",
            )
        )
        assert records[0]["card_image"] == ""
        with pytest.raises(ValueError):
            substack_records(b"<html/>")

    def test_missing_and_empty_subtitles(self):
        for description in (b"", b"<description/>", b"<description> </description>"):
            feed = FEED.replace(
                b"<description><![CDATA[Plus we&#8217;re discussing A &amp; B]]></description>",
                description,
            )
            assert substack_records(feed)[0]["subtitle"] == ""
        post = {
            "title": "A & B",
            "canonical_url": "https://simonw.substack.com/p/a-b",
            "post_date": "2026-10-05T17:16:45Z",
        }
        for fields in ({}, {"subtitle": None}, {"subtitle": ""}):
            assert substack_archive_records([{**post, **fields}])[0]["subtitle"] == ""

    def test_dry_run_and_invalid_batch_write_nothing(self):
        records = substack_records(FEED)
        assert save_records(records, dry_run=True)["created"] == 1
        assert not Newsletter.objects.exists()
        invalid = {**records[0], "import_ref": "invalid", "title": "x" * 256}
        with pytest.raises(ValidationError):
            save_records([*records, invalid])
        assert not Newsletter.objects.exists()

    @patch("blog.newsletter_importers.requests.get")
    def test_substack_import_and_http_failure(self, get):
        get.return_value = Mock(content=FEED)
        assert import_substack()["created"] == 1
        get.assert_called_once_with("https://simonw.substack.com/feed", timeout=30)
        get.return_value.raise_for_status.assert_called_once()
        get.return_value.raise_for_status.side_effect = ValueError("Failed download")
        with pytest.raises(ValueError):
            import_substack()
        assert Newsletter.objects.count() == 1

    def test_admin_can_inspect_imported_content(self):
        obj = self.sponsor()
        obj.save()
        self.client.force_login(
            User.objects.create_superuser("newsletters", "n@example.com", "pw")
        )
        assertContains(self.client.get("/admin/blog/newsletter/"), "Sponsor digest")
        response = self.client.get(f"/admin/blog/newsletter/{obj.pk}/change/")
        assertContains(response, "Content and visibility")
        assertContains(response, "Import details")
        assertContains(response, 'name="subtitle"')
        assertNotContains(response, 'name="search_document"')
        assertContains(
            self.client.get("/admin/blog/newsletter/?kind__exact=sponsor&q=pangolin"),
            "Sponsor digest",
        )

    def test_admin_validates_public_body_and_updates_search_index(self):
        obj = self.sponsor(is_public=False, body="")
        obj.save()
        self.client.force_login(
            User.objects.create_superuser("editor", "editor@example.com", "pw")
        )
        url = f"/admin/blog/newsletter/{obj.pk}/change/"
        data = {
            "kind": "sponsor",
            "title": obj.title,
            "slug": obj.slug,
            "created_0": "2026-09-04",
            "created_1": "05:50:18",
            "url": obj.url,
            "is_public": "on",
            "body": "",
            "_save": "Save",
        }
        response = self.client.post(url, data)
        assertContains(response, "Public sponsor issues need their content.")
        obj.refresh_from_db()
        assert not obj.is_public
        data["body"] = "Public pangolin content."
        with self.commit_callbacks():
            response = self.client.post(url, data)
        assert response.status_code == 302
        obj.refresh_from_db()
        assert obj.is_public
        assert obj.search_document is not None
        data["is_draft"] = "on"
        with self.commit_callbacks():
            assert self.client.post(url, data).status_code == 302
        obj.refresh_from_db()
        assert obj.search_document is None

    @patch("blog.newsletter_importers.requests.get")
    def test_archive_pagination_and_rss_share_identity(self, get):
        post = {
            "title": "A & B",
            "subtitle": "Plus we’re discussing A & B",
            "canonical_url": "https://simonw.substack.com/p/a-b",
            "post_date": "2026-10-05T17:16:45.123Z",
            "cover_image": "https://example.com/image.jpg",
        }
        older = {
            **post,
            "canonical_url": "https://simonw.substack.com/p/older",
            "cover_image": None,
        }
        get.side_effect = [
            Mock(json=Mock(return_value=[post])),
            Mock(json=Mock(return_value=[older])),
            Mock(json=Mock(return_value=[])),
        ]
        assert import_substack_archive()["created"] == 2
        assert [call.kwargs["params"]["offset"] for call in get.call_args_list] == [
            0,
            12,
            24,
        ]
        assert save_records(substack_records(FEED))["skipped"] == 1
        get.side_effect = [
            Mock(json=Mock(return_value=[post])),
            Mock(json=Mock(return_value=[post])),
        ]
        with pytest.raises(ValueError):
            import_substack_archive()
        assert Newsletter.objects.count() == 2


@pytest.mark.django_db
class TestNewsletterImporterView:
    @pytest.fixture(autouse=True)
    def setup(self, client, commit_callbacks, db):
        self.client = client
        self.commit_callbacks = commit_callbacks
        self.admin = User.objects.create_superuser(
            "importer", "importer@example.com", "pw"
        )
        self.client.force_login(self.admin)

    def post(self, importer, **kwargs):
        return self.client.post(
            "/api/run-importer/",
            {"importer": importer, **kwargs},
            content_type="application/json",
        )

    def test_buttons_and_staff_access(self):
        response = self.client.get("/admin/importers/")
        assertContains(response, 'data-importer="substack_latest"')
        assertContains(response, 'data-importer="substack_all"')
        assertContains(response, "Import latest")
        assertContains(response, "Import all")
        assertContains(response, "Beat Importers")
        self.client.logout()
        assert self.post("substack_latest").status_code == 302
        self.client.force_login(User.objects.create_user("reader"))
        assert self.post("substack_all").status_code == 302
        self.client.force_login(self.admin)
        assert self.client.get("/api/run-importer/").status_code == 405
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        assert (
            csrf_client.post(
                "/api/run-importer/",
                {"importer": "substack_all"},
                content_type="application/json",
            ).status_code
            == 403
        )

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="")
    @patch("blog.newsletter_importers.requests.get")
    def test_private_button_disabled_without_token(self, get):
        response = self.client.get("/admin/importers/")
        button = BeautifulSoup(response.content, "html.parser").select_one(
            '[data-importer="monthly_private"]'
        )
        assert button.has_attr("disabled")
        assertContains(response, "GH_API_SIMONW_PRIVATE_MONTHLY")
        assert self.post("monthly_private").status_code == 400
        get.assert_not_called()

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="example-secret-token")
    @patch("blog.newsletter_importers.import_private_monthly")
    def test_private_button_enabled_without_exposing_token(self, importer):
        response = self.client.get("/admin/importers/")
        button = BeautifulSoup(response.content, "html.parser").select_one(
            '[data-importer="monthly_private"]'
        )
        assert not button.has_attr("disabled")
        assertNotContains(response, "example-secret-token")
        importer.return_value = {"created": 0, "updated": 0, "skipped": 0, "items": []}
        assert self.post("monthly_private").status_code == 200
        importer.assert_called_once_with()
        importer.side_effect = ValueError(
            "example-secret-token private response content"
        )
        response = self.post("monthly_private")
        assert response.status_code == 500
        assert "example-secret-token" not in response.content.decode()
        self.client.logout()
        assert self.post("monthly_private").status_code == 302

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="")
    @patch("blog.newsletter_importers.requests.get")
    def test_public_monthly_button_imports_batches_without_token(self, get):
        page = self.client.get("/admin/importers/")
        button = BeautifulSoup(page.content, "html.parser").select_one(
            '[data-importer="monthly_public"]'
        )
        assert button is not None
        assert not button.has_attr("disabled")
        index = [
            {"filename": "2026-08-august.md", "sent_at": "2026-09-04T05:50:18Z"},
            {"filename": "2026-09-september.md", "sent_at": "2026-10-03T21:21:39Z"},
        ]
        get.side_effect = [
            Mock(json=Mock(return_value=index)),
            Mock(content=b"# August digest\n\nPublic pangolin content."),
            Mock(json=Mock(return_value=index)),
            Mock(content=b"# September digest\n\nMore content."),
        ]
        with self.commit_callbacks():
            response = self.post("monthly_public")
        assert response.status_code == 200
        assert response.json()["created"] == 1
        assert response.json()["next_offset"] == 1
        assert "August digest" in response.json()["items_html"]
        issue = Newsletter.objects.get()
        assert issue.search_document is not None
        assert issue.get_absolute_url() in response.json()["items_html"]
        response = self.post("monthly_public", offset=1)
        assert response.json()["created"] == 1
        assert response.json()["next_offset"] is None
        assert Newsletter.objects.count() == 2
        assert all(
            (call.args[0].startswith(MONTHLY_RAW) for call in get.call_args_list)
        )
        get.reset_mock()
        get.side_effect = [Mock(json=Mock(return_value=[]))]
        assert self.post("monthly_public").json()["next_offset"] is None
        for offset in (-1, "0", True, 12000):
            assert self.post("monthly_public", offset=offset).status_code == 400
        assert get.call_count == 1

    @override_settings(
        GH_API_SIMONW_PRIVATE_MONTHLY="example-secret-token", TIME_ZONE="UTC"
    )
    @patch("blog.newsletter_importers.monthly_index", return_value=[])
    @patch("blog.newsletter_importers.requests.get")
    def test_private_rate_limit_messages(self, get, index):
        cases = [
            (
                403,
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1791517857"},
                {},
                "October 09 at 03:50 AM UTC",
            ),
            (429, {"Retry-After": "60"}, {}, "Try again in 60 seconds"),
            (
                403,
                {},
                {"message": "API rate limit exceeded: example-secret-token"},
                "Please try again later",
            ),
            (
                403,
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "invalid"},
                {},
                "Please try again later",
            ),
        ]
        for status, headers, data, expected in cases:
            get.return_value = Mock(
                status_code=status, headers=headers, json=Mock(return_value=data)
            )
            response = self.post("monthly_private")
            assert response.status_code == 429
            assert "GitHub API rate limit exceeded" in response.json()["error"]
            assert expected in response.json()["error"]
            assert "example-secret-token" not in response.content.decode()
        get.return_value = Mock(
            status_code=403,
            headers={},
            json=Mock(return_value={"message": "Resource not accessible"}),
        )
        response = self.post("monthly_private")
        assert response.status_code == 500
        assert "rate limit" not in response.json()["error"]
        assert not Newsletter.objects.exists()

    @patch("blog.newsletter_importers.requests.get")
    def test_latest_repeat_and_editorial_preservation(self, get):
        get.return_value = Mock(content=FEED)
        result = self.post("substack_latest").json()
        assert result["created"] == 1
        assert result["total"] == 1
        assert "A &amp; B" in result["items_html"]
        obj = Newsletter.objects.get()
        assert f"/admin/blog/newsletter/{obj.pk}/change/" in result["items_html"]
        obj.slug = "custom"
        obj.is_draft = True
        obj.save()
        assert self.post("substack_latest").json()["skipped"] == 1
        get.return_value = Mock(content=FEED.replace(b"A &amp; B", b"Revised title"))
        assert self.post("substack_latest").json()["updated"] == 1
        obj.refresh_from_db()
        assert obj.slug == "custom"
        assert obj.is_draft
        assert obj.body == ""
        assert Newsletter.objects.count() == 1
        get.assert_called_with("https://simonw.substack.com/feed", timeout=30)

    @patch("blog.newsletter_importers.requests.get")
    def test_all_pages_rss_identity_and_end(self, get):
        post = {
            "title": "A & B",
            "subtitle": "Plus we’re discussing A & B",
            "canonical_url": "https://simonw.substack.com/p/a-b",
            "post_date": "2026-10-05T17:16:45.123Z",
            "cover_image": "https://example.com/image.jpg",
        }
        save_records(substack_records(FEED))
        get.return_value = Mock(json=Mock(return_value=[post]))
        first = self.post("substack_all").json()
        assert first["skipped"] == 1
        assert first["next_offset"] == 12
        get.return_value = Mock(
            json=Mock(
                return_value=[
                    {**post, "canonical_url": "https://simonw.substack.com/p/older"}
                ]
            )
        )
        second = self.post("substack_all", offset=12).json()
        assert second["created"] == 1
        assert second["next_offset"] == 24
        get.return_value = Mock(json=Mock(return_value=[]))
        last = self.post("substack_all", offset=24).json()
        assert last["next_offset"] is None
        assert Newsletter.objects.count() == 2
        assert [call.kwargs["params"]["offset"] for call in get.call_args_list] == [
            0,
            12,
            24,
        ]

    @patch("blog.newsletter_importers.requests.get")
    def test_import_all_backfills_existing_subtitle_and_is_repeatable(self, get):
        save_records(substack_records(FEED))
        obj = Newsletter.objects.get()
        obj.subtitle = ""
        obj.slug = "custom-slug"
        obj.is_draft = True
        obj.save()
        get.return_value = Mock(
            json=Mock(
                return_value=[
                    {
                        "title": obj.title,
                        "subtitle": "Plus we’re discussing A & B",
                        "canonical_url": obj.url,
                        "post_date": obj.created.isoformat(),
                        "cover_image": obj.card_image,
                    }
                ]
            )
        )
        result = self.post("substack_all").json()
        assert result["updated"] == 1
        assert result["created"] == 0
        obj.refresh_from_db()
        assert obj.subtitle == "Plus we’re discussing A & B"
        assert obj.slug == "custom-slug"
        assert obj.is_draft
        assert self.post("substack_all").json()["skipped"] == 1
        assert Newsletter.objects.count() == 1

    @patch("blog.newsletter_importers.requests.get")
    def test_failed_batch_and_validation(self, get):
        get.return_value = Mock(json=Mock(return_value={"error": "broken"}))
        response = self.post("substack_all")
        assert response.status_code == 500
        assert "Expected a list" in response.json()["error"]
        assert Newsletter.objects.count() == 0
        get.reset_mock()
        for offset in (-12, 1, 12000, "12", True):
            assert self.post("substack_all", offset=offset).status_code == 400
        get.assert_not_called()


@pytest.mark.django_db
class TestNewsletterPage:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

    def issue(self, **overrides):
        fields = dict(
            kind="sponsor",
            title="Monthly example",
            slug="monthly-example",
            body="# Monthly example\n\nHello **world**.\n\n## Section\n\n[Link](https://example.com/)\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n```python\nprint(1)\n```",
            is_public=True,
            url="https://github.com/example/monthly",
            created=datetime.datetime(2026, 9, 4, tzinfo=datetime.timezone.utc),
        )
        fields.update(overrides)
        return Newsletter.objects.create(**fields)

    def test_index_order_destinations_lazy_images_and_draft_privacy(self):
        public = self.issue()
        private = self.issue(
            slug="private",
            title="Private issue",
            is_public=False,
            body="Unreleased secret content",
            created=public.created + datetime.timedelta(days=1),
        )
        external = self.issue(
            kind="substack",
            slug="external",
            title="External issue",
            body="",
            url="https://simonw.substack.com/p/example",
            card_image="https://example.com/image.jpg",
            created=public.created + datetime.timedelta(days=2),
        )
        self.issue(slug="draft", title="Hidden draft", is_draft=True)
        response = self.client.get(reverse("newsletters"))
        assert list(response.context["newsletters"]) == [external, private, public]
        soup = BeautifulSoup(response.content, "html.parser")
        links = [a["href"] for a in soup.select(".newsletter-list h3 a")]
        assert links == [external.url, private.url, "/newsletters/monthly-example/"]
        assert soup.select_one(".newsletter-list img")["loading"] == "lazy"
        assertContains(response, "Sponsors only")
        prompt = soup.select_one(".newsletter-sponsors-only")
        assert "Private issue" in prompt.text
        assert (
            prompt.select_one(".newsletter-sponsor-link")["href"]
            == "https://github.com/sponsors/simonw/"
        )
        assert (
            prompt.select_one(".newsletter-existing-sponsor a")["href"] == private.url
        )
        assert len(soup.select(".newsletter-sponsor-prompt")) == 1
        assertNotContains(response, "Hidden draft")
        assertNotContains(response, "Unreleased secret content")
        assert public.get_absolute_url() == "/newsletters/monthly-example/"
        assert external.get_absolute_url() == external.url
        assert private.get_absolute_url() == private.url

    def test_subtitles_render_as_plain_text_in_listings(self, subtests):
        self.issue(
            kind="substack",
            slug="with-subtitle",
            body="",
            subtitle='Plus <script>alert("hello")</script> & more',
        )
        self.issue(slug="without-subtitle")
        for url in (
            "/newsletters/",
            "/newsletters/2026/",
            "/2026/Sep/",
            "/2026/Sep/4/",
        ):
            with subtests.test(url=url):
                soup = BeautifulSoup(self.client.get(url).content, "html.parser")
                subtitles = soup.select(".newsletter-subtitle")
                assert len(subtitles) == 1
                assert (
                    subtitles[0].get_text()
                    == 'Plus <script>alert("hello")</script> & more'
                )
                assert subtitles[0].find("script") is None

    def test_index_latest_ten_and_complete_year_pages(self):
        for i in range(55):
            self.issue(slug=f"issue-{i}", title=f"Issue {i}")
        older = self.issue(
            slug="older",
            title="Older issue",
            created=datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc),
        )
        self.issue(
            slug="hidden-year",
            is_draft=True,
            created=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
        )
        response = self.client.get(reverse("newsletters"), {"page": 2})
        assert [n.slug for n in response.context["newsletters"]] == [
            f"issue-{i}" for i in range(54, 44, -1)
        ]
        assert "page_obj" not in response.context
        soup = BeautifulSoup(response.content, "html.parser")
        assert [a["href"] for a in soup.select(".newsletter-years li a")] == [
            "/newsletters/2026/",
            "/newsletters/2025/",
        ]
        response = self.client.get("/newsletters/2026/")
        assert len(response.context["newsletters"]) == 55
        assertNotContains(response, "Older issue")
        assert list(self.client.get("/newsletters/2025/").context["newsletters"]) == [
            older
        ]
        for year in (2024, 2023, "0000"):
            assert self.client.get(f"/newsletters/{year}/").status_code == 404

    def test_year_slugs_are_reserved(self):
        issue = Newsletter(
            kind="substack", title="Example", slug="2026", url="https://example.com/"
        )
        with pytest.raises(ValidationError):
            issue.full_clean()

    def test_day_and_month_archives_include_newsletter_listings_without_bodies(self):
        public = self.issue(title="Public newsletter", body="Full public body")
        private = self.issue(
            slug="private",
            title="Private newsletter",
            is_public=False,
            body="Private body must not leak",
            preview_headings="Public preview heading",
        )
        substack = self.issue(
            slug="substack",
            kind="substack",
            title="Substack newsletter",
            body="",
            url="https://simonw.substack.com/p/example",
            card_image="https://example.com/image.jpg",
        )
        self.issue(slug="draft", title="Draft newsletter", is_draft=True)
        for url in ("/2026/Sep/4/", "/2026/Sep/"):
            response = self.client.get(url)
            assert response.status_code == 200
            items = response.context["items"]
            assert {item["obj"].pk for item in items} == {
                public.pk,
                private.pk,
                substack.pk,
            }
            soup = BeautifulSoup(response.content, "html.parser")
            assert len(soup.select('[data-type="newsletter"]')) == 3
            assertContains(response, public.get_absolute_url())
            assertContains(response, private.url)
            assertContains(response, substack.url)
            assertContains(response, "Public preview heading")
            assertNotContains(response, "Private body must not leak")
            assertNotContains(response, "Full public body")
            assertNotContains(response, "Draft newsletter")
            assert soup.select_one('[data-type="newsletter"] img')["loading"] == "lazy"
            assertContains(response, 'title="3 newsletters"')
        assertContains(response, "3 newsletters")
        assertNotContains(response, "/search/?type=newsletter")

    def test_year_archive_counts_newsletters_without_listing_titles(self):
        self.issue(title="Never list this title")
        self.issue(slug="second", title="Second newsletter", is_public=False)
        self.issue(slug="draft", is_draft=True)
        self.issue(
            slug="october",
            created=datetime.datetime(2026, 10, 3, tzinfo=datetime.timezone.utc),
        )
        response = self.client.get("/2026/")
        assertContains(response, "2 newsletters")
        assertContains(response, "1 newsletter")
        assertNotContains(response, "Never list this title")
        assertNotContains(response, "Second newsletter")
        assert [month["date"].month for month in response.context["months"]] == [9, 10]
        assert all((not month["entries"] for month in response.context["months"]))

    def test_day_navigation_and_calendar_skip_draft_newsletters(self):
        for day, draft in ((2, False), (3, True), (4, False), (5, True), (6, False)):
            self.issue(
                slug=f"day-{day}",
                is_draft=draft,
                created=datetime.datetime(2026, 9, day, tzinfo=datetime.timezone.utc),
            )
        response = self.client.get("/2026/Sep/4/")
        assert response.context["previous_day"] == datetime.date(2026, 9, 2)
        assert response.context["next_day"] == datetime.date(2026, 9, 6)
        assertNotContains(response, 'href="/2026/Sep/3/"')
        assertNotContains(response, 'href="/2026/Sep/5/"')
        assert self.client.get("/2026/Sep/3/").status_code == 404

    def test_newsletters_remain_absent_from_homepage_and_tag_pages(self):
        from .factories import EntryFactory
        from .models import Tag

        entry = EntryFactory()
        entry.tags.add(Tag.objects.create(tag="example"))
        self.issue(title="Newsletter stays separate")
        for url in ("/", "/tags/example/"):
            response = self.client.get(url)
            assert response.status_code == 200
            assertNotContains(response, "Newsletter stays separate")

    def test_preview_headings_are_plain_text_and_shown_for_all_monthly_issues(self):
        issue = self.issue(
            is_public=False,
            body="",
            preview_headings=" First topic \n\nA <script>heading</script>\nLast topic",
        )
        assert issue.preview_heading_list() == [
            "First topic",
            "A <script>heading</script>",
            "Last topic",
        ]
        for url in ("/newsletters/", "/newsletters/2026/"):
            response = self.client.get(url)
            assertContains(response, "A &lt;script&gt;heading&lt;/script&gt;")
            soup = BeautifulSoup(response.content, "html.parser")
            assert [
                li.text for li in soup.select(".newsletter-preview-headings li")
            ] == issue.preview_heading_list()
            assert soup.select_one(".newsletter-preview-headings script") is None
        assert issue.index_components() == {}
        issue.is_public = True
        issue.body = "Public content"
        issue.save()
        for url in ("/newsletters/", "/newsletters/2026/"):
            response = self.client.get(url)
            assertContains(response, "First topic")
            assertContains(response, "A &lt;script&gt;heading&lt;/script&gt;")
            assertNotContains(response, "Read this issue on GitHub")
        assert "First topic" not in issue.index_components()["C"]
        issue.kind = "substack"
        issue.is_public = False
        issue.save()
        assertNotContains(self.client.get("/newsletters/"), "First topic")

    def test_detail_renders_markdown_with_entry_layout_and_one_title(self):
        issue = self.issue()
        issue.body += "\n\n### Subsection\n\nMore content."
        issue.save()
        response = self.client.get(issue.get_absolute_url())
        assertTemplateUsed(response, "item_base.html")
        soup = BeautifulSoup(response.content, "html.parser")
        body = soup.select_one(".newsletter-body")
        assert body.select_one("strong").text == "world"
        assert body.select_one("h3#section").text == "Section"
        assert body.select_one("h4#subsection").text == "Subsection"
        assert body.select_one("table") is not None
        assert body.select_one("pre code.language-python") is not None
        assert body.select_one("h1") is None
        assert len([h for h in body.select("h2") if h.text == issue.title]) == 1
        assertContains(response, 'href="/newsletters/"')
        breadcrumbs = soup.select_one('nav[aria-label="Breadcrumb"]')
        assert [a["href"] for a in breadcrumbs.select("a")] == [
            "/newsletters/",
            "/newsletters/2026/",
        ]
        assert breadcrumbs.select_one('[aria-current="page"]').text == issue.title

    def test_unreleased_drafts_external_and_missing_issues_have_no_local_page(self):
        for overrides in (
            {"is_public": False},
            {"is_draft": True},
            {"kind": "substack", "body": ""},
            {"body": ""},
        ):
            issue = self.issue(slug=f"issue-{Newsletter.objects.count()}", **overrides)
            response = self.client.get(reverse("newsletter_detail", args=[issue.slug]))
            assert response.status_code == 404
            assertNotContains(response, "Hello", status_code=404)
        assert self.client.get("/newsletters/missing/").status_code == 404

    def test_empty_index_and_existing_substack_shortcut(self):
        assertContains(self.client.get("/newsletters/"), "No newsletters yet.")
        assertRedirects(
            self.client.get("/newsletter/"),
            "https://simonw.substack.com/",
            fetch_redirect_response=False,
        )


@pytest.mark.django_db
class TestNewsletterSearch:
    @pytest.fixture(autouse=True)
    def setup(self, client, commit_callbacks):
        self.client = client
        self.commit_callbacks = commit_callbacks

    def issue(self, **overrides):
        fields = dict(
            kind="sponsor",
            title="Monthly pangolin news",
            slug=f"issue-{Newsletter.objects.count()}",
            body="A capybara and a **quokka**.",
            is_public=True,
            url="https://github.com/example/monthly",
            preview_headings="Hiddenpreviewtoken",
            created=datetime.datetime(2026, 1, 2, 12, tzinfo=datetime.timezone.utc),
            metadata={"issue_month": "2025-12"},
        )
        fields.update(overrides)
        with self.commit_callbacks():
            issue = Newsletter.objects.create(**fields)
        issue.refresh_from_db()
        return issue

    def context(self, **params):
        from .search import search

        return search(RequestFactory().get("/search/", params), return_context=True)

    def test_title_and_body_search_mixed_results_and_local_links(self):
        from .factories import EntryFactory

        issue = self.issue()
        with self.commit_callbacks():
            entry = EntryFactory(
                title="Pangolin article", body="<p>A regular article.</p>"
            )
        response = self.client.get("/search/", {"q": "pangolin"})
        assert response.context["total"] == 2
        assert {result["type"] for result in response.context["results"]} == {
            "entry",
            "newsletter",
        }
        assertContains(response, issue.get_absolute_url())
        assertContains(response, entry.get_absolute_url())
        assertContains(response, "Monthly newsletter")
        assertContains(response, "A capybara and a quokka.")
        assertNotContains(response, "Hiddenpreviewtoken")
        assert {
            "type": "newsletter",
            "label": "Newsletter",
            "n": 1,
        } in response.context["type_counts"]
        assert self.context(q="capybara")["total"] == 1
        assert self.context(q="hiddenpreviewtoken")["total"] == 0

    def test_private_draft_and_substack_excluded_even_with_stale_vectors(self):
        public = self.issue()
        for overrides in (
            {"is_public": False},
            {"is_draft": True},
            {"kind": "substack"},
            {"body": ""},
        ):
            excluded = self.issue(**overrides)
            Newsletter.objects.filter(pk=excluded.pk).update(
                search_document=public.search_document
            )
        for params in (
            {},
            {"type": "newsletter"},
            {"q": "capybara"},
            {"q": "pangolin", "type": "newsletter"},
        ):
            context = self.context(**params)
            assert context["total"] == 1
            assert context["results"][0]["obj"].pk == public.pk
            assert context["type_counts"] == [
                {"type": "newsletter", "label": "Newsletter", "n": 1}
            ]

    def test_type_and_date_filters_use_original_send_date(self):
        issue = self.issue()
        january = self.context(type="newsletter", year="2026", month="1")
        assert january["total"] == 1
        assert january["selected"]["type_label"] == "Newsletter"
        assert january["title"] == "Newsletters in January, 2026"
        assert january["year_counts"][0]["year"].year == 2026
        assert january["month_counts"][0]["month"].month == 1
        assert january["tag_counts"] == []
        for params in (
            {"type": "entry"},
            {"year": "2025"},
            {"month": "12"},
            {"q": "capybara to:2026-01-02"},
        ):
            assert self.context(**params)["total"] == 0
        assert self.context(q="capybara from:2026-01-02 to:2026-01-03")["total"] == 1

    @override_settings(TIME_ZONE="America/Los_Angeles")
    def test_date_filter_boundaries_are_aware_and_use_default_timezone(self, subtests):
        start = datetime.datetime(2026, 1, 2, 8, tzinfo=datetime.timezone.utc)
        end = start + datetime.timedelta(days=1)
        before = self.issue(created=start - datetime.timedelta(seconds=1))
        at_start = self.issue(created=start)
        before_end = self.issue(created=end - datetime.timedelta(seconds=1))
        at_end = self.issue(created=end)
        cases = (
            ("from:2026-01-02", {at_start.pk, before_end.pk, at_end.pk}),
            ("to:2026-01-03", {before.pk, at_start.pk, before_end.pk}),
            ("from:2026-01-02 to:2026-01-03", {at_start.pk, before_end.pk}),
        )
        with warnings.catch_warnings(), timezone.override("Asia/Tokyo"):
            warnings.filterwarnings(
                "error", r"DateTimeField .* received a naive datetime", RuntimeWarning
            )
            for query, expected in cases:
                with subtests.test(query=query):
                    context = self.context(q=query)
                    assert {
                        result["obj"].pk for result in context["results"]
                    } == expected
                    if "from:" in query:
                        assert context["selected"]["from_date"] == start.date()
                    if "to:" in query:
                        assert context["selected"]["to_date"] == end.date()

    def test_tags_exclude_untagged_newsletters_but_negative_filters_allow_them(self):
        from .factories import EntryFactory
        from .models import Tag

        self.issue()
        tag = Tag.objects.create(tag="animals")
        with self.commit_callbacks():
            entry = EntryFactory(title="Pangolin article", body="<p>capybara</p>")
            entry.tags.add(tag)
        context = self.context(q="pangolin", tag="animals")
        assert [result["type"] for result in context["results"]] == ["entry"]
        assert self.context(type="newsletter", tag="animals")["total"] == 0
        context = self.context(q="pangolin", **{"exclude.tag": "animals"})
        assert [result["type"] for result in context["results"]] == ["newsletter"]

    def test_search_changes_when_issue_is_published_edited_or_hidden(self):
        issue = self.issue(is_public=False)
        assert self.context(q="capybara")["total"] == 0
        issue.is_public = True
        with self.commit_callbacks():
            issue.save()
        assert self.context(q="capybara")["total"] == 1
        issue.body = "An aardvark"
        with self.commit_callbacks():
            issue.save()
        assert self.context(q="capybara")["total"] == 0
        assert self.context(q="aardvark")["total"] == 1
        issue.is_draft = True
        with self.commit_callbacks():
            issue.save()
        assert self.context(q="aardvark")["total"] == 0

    def test_bulk_tagging_excludes_newsletters(self):
        self.issue()
        self.client.force_login(
            User.objects.create_superuser("tagger", "t@example.com", "pw")
        )
        response = self.client.get("/admin/bulk-tag/", {"q": "pangolin"})
        assert response.status_code == 200
        assert response.context["total"] == 0
        assert response.context["type_counts"] == []

    def test_id_filter_and_pagination(self):
        from .search import search

        issues = [
            self.issue(
                created=datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc)
            )
            for day in range(1, 4)
        ]
        response = self.client.get("/search/", {"newsletters": str(issues[0].pk)})
        assert response.context["total"] == 1
        assertContains(response, "Filtered to specific newsletters")
        assert (
            BeautifulSoup(response.content, "html.parser").select_one(
                ".id-filter-notice a"
            )["href"]
            == "?"
        )
        context = search(
            RequestFactory().get("/search/", {"type": "newsletter", "page": 2}),
            return_context=True,
            per_page=2,
        )
        assert context["total"] == 3
        assert [result["obj"].pk for result in context["results"]] == [issues[0].pk]

    def test_reindex_all_rebuilds_public_and_clears_private_documents(self):
        public = self.issue()
        private = self.issue(is_public=False)
        Newsletter.objects.filter(pk=private.pk).update(
            search_document=public.search_document
        )
        Newsletter.objects.filter(pk=public.pk).update(search_document=None)
        with self.commit_callbacks():
            call_command("reindex_all", stdout=io.StringIO())
        public.refresh_from_db()
        private.refresh_from_db()
        assert public.search_document is not None
        assert private.search_document is None


@pytest.mark.django_db
class TestMonthlyImport:
    @pytest.fixture(autouse=True)
    def setup(self, commit_callbacks):
        self.commit_callbacks = commit_callbacks

    filename = "2026-08-august.md"
    body = "# August digest\n\nPublic **content**. Revised.\n\n## First **topic**\n\n```md\n## Not a heading\n```\n\n### Subsection\n\n## Second [topic](https://example.com/)\n"

    def response(self, data=None, text="", links=None):
        return Mock(
            json=Mock(return_value=data),
            content=text.encode("utf-8"),
            links=links or {},
        )

    def index_entry(self, filename=None, sent_at="2026-09-04T05:50:18Z"):
        return {"filename": filename or self.filename, "sent_at": sent_at}

    @patch("blog.newsletter_importers.requests.get")
    def test_public_http_import_dates_and_repeat(self, get):
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text=self.body),
        ]
        with self.commit_callbacks():
            assert import_monthly()["created"] == 1
        issue = Newsletter.objects.get()
        assert issue.created.isoformat() == "2026-09-04T05:50:18+00:00"
        assert issue.body == self.body.strip()
        assert issue.title == "August digest"
        assert issue.preview_heading_list() == ["First topic", "Second topic"]
        assert issue.is_public
        assert issue.search_document is not None
        assert issue.metadata["issue_month"] == "2026-08"
        assert [c.args[0] for c in get.call_args_list] == [
            MONTHLY_RAW + "/index.json",
            MONTHLY_RAW + "/" + self.filename,
        ]
        # Reimports use the established send date, with no API request.
        get.reset_mock()
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text=self.body),
        ]
        assert import_monthly()["skipped"] == 1
        assert get.call_count == 2

    @patch("blog.newsletter_importers.requests.get")
    def test_public_reimport_backfills_missing_headings(self, get):
        existing = Newsletter.objects.create(
            import_ref="monthly:" + self.filename,
            kind="sponsor",
            title="August digest",
            slug="existing-public-monthly",
            url=MONTHLY_RAW + "/" + self.filename,
            is_public=True,
            body=self.body,
        )
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text=self.body),
        ]
        assert import_monthly()["updated"] == 1
        existing.refresh_from_db()
        assert existing.preview_heading_list() == ["First topic", "Second topic"]
        assert Newsletter.objects.count() == 1

    @patch("blog.newsletter_importers.requests.get")
    def test_public_promotion_preserves_editorial_fields_and_date(self, get):
        date = datetime.datetime(2026, 9, 4, 5, 50, 18, tzinfo=datetime.timezone.utc)
        existing = Newsletter.objects.create(
            import_ref="monthly:" + self.filename,
            kind="sponsor",
            title="Coming soon",
            slug="existing-monthly",
            url="https://github.com/example/private",
            is_public=False,
            created=date,
            preview_headings="A preview",
            metadata={"editor_note": "Keep"},
        )
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text=self.body),
        ]
        with self.commit_callbacks():
            assert import_monthly()["updated"] == 1
        existing.refresh_from_db()
        assert Newsletter.objects.count() == 1
        assert existing.is_searchable
        assert existing.search_document is not None
        assert existing.slug == "existing-monthly"
        assert existing.created == date
        assert existing.preview_headings == "A preview"
        assert existing.metadata["editor_note"] == "Keep"

    @patch("blog.newsletter_importers.requests.get")
    def test_dry_run_fallback_title_and_index_date(self, get):
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text="An issue without a heading. Café."),
        ]
        records = monthly_records()
        assert records[0]["title"] == "LLM digest: August 2026"
        assert "Café" in records[0]["body"]
        assert records[0]["created"].day == 4
        assert save_records(records, dry_run=True)["created"] == 1
        assert not Newsletter.objects.exists()

    @patch("blog.newsletter_importers.requests.get")
    def test_invalid_index_is_rejected_before_fetching_content(self, get):
        for index in (
            {},
            [self.filename],
            [123],
            [self.index_entry("../secret.md")],
            [self.index_entry(), self.index_entry()],
        ):
            get.reset_mock()
            get.return_value = self.response(index)
            with pytest.raises(ValueError):
                import_monthly()
            assert get.call_count == 1
        assert not Newsletter.objects.exists()

    @patch("blog.newsletter_importers.requests.get")
    def test_http_failure_leaves_whole_batch_unsaved(self, get):
        import requests

        failed = self.response()
        failed.raise_for_status.side_effect = requests.HTTPError("404")
        get.side_effect = [
            self.response(
                [self.index_entry(), self.index_entry("2026-09-september.md")]
            ),
            self.response(text=self.body),
            failed,
        ]
        with pytest.raises(requests.HTTPError):
            import_monthly()
        assert not Newsletter.objects.exists()

    @patch("blog.newsletter_importers.requests.get")
    def test_missing_or_invalid_send_date_is_not_guessed(self, get):
        for sent_at in (None, "", "invalid", "2026-09-04T00:00:00"):
            get.reset_mock()
            get.return_value = self.response([self.index_entry(sent_at=sent_at)])
            with pytest.raises(ValueError):
                import_monthly()
            assert get.call_count == 1
        assert not Newsletter.objects.exists()


@pytest.mark.django_db
class TestPrivateMonthlyApi:
    @pytest.fixture(autouse=True)
    def setup(self, commit_callbacks, settings):
        self.commit_callbacks = commit_callbacks
        settings.GH_API_SIMONW_PRIVATE_MONTHLY = "example-secret-token"

    @patch("blog.newsletter_importers.requests.get")
    def test_import_metadata_headings_and_repeat(self, get):
        from blog.newsletter_importers import import_private_monthly

        filename = "2026-09-september.md"

        def response(data=None, content=b""):
            return Mock(
                status_code=200, json=Mock(return_value=data), content=content, links={}
            )

        public_index = response(
            [{"filename": "2026-08-august.md", "sent_at": "2026-09-04T05:50:18Z"}]
        )
        listing = response(
            [
                {"type": "file", "name": "2026-08-august.md"},
                {"type": "file", "name": filename},
                {"type": "file", "name": "README.md"},
            ]
        )
        body = response(
            content=b"# September digest\n\nPRIVATE BODY\n\n## First **heading**\n\n```md\n## Not a heading\n```\n\n## Second heading\n"
        )
        get.side_effect = [
            public_index,
            listing,
            response([{"commit": {"committer": {"date": "2026-10-03T21:21:39Z"}}}]),
            body,
        ]
        with self.commit_callbacks():
            assert import_private_monthly()["created"] == 1
        issue = Newsletter.objects.get()
        assert issue.title == "September digest"
        assert issue.preview_heading_list() == ["First heading", "Second heading"]
        assert issue.created.isoformat() == "2026-10-03T21:21:39+00:00"
        assert issue.body == ""
        assert not issue.is_public
        assert issue.search_document is None
        assert "PRIVATE BODY" not in json.dumps(issue.metadata)
        for call in get.call_args_list:
            if call.args[0].startswith("https://api.github.com/"):
                assert (
                    call.kwargs["headers"]["Authorization"]
                    == "Bearer example-secret-token"
                )
                assert not call.kwargs["allow_redirects"]
            else:
                assert "headers" not in call.kwargs
        issue.preview_headings = "Curated preview"
        issue.save()
        get.side_effect = [public_index, listing, body]
        assert import_private_monthly()["skipped"] == 1
        issue.refresh_from_db()
        assert issue.preview_headings == "Curated preview"
        # Already-public local issues must not be demoted even if the public index is stale.
        issue.is_public = True
        issue.body = "Now public"
        issue.save()
        get.side_effect = [public_index, listing]
        assert import_private_monthly()["created"] == 0
        issue.refresh_from_db()
        assert issue.is_public

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="")
    @patch("blog.newsletter_importers.requests.get")
    def test_missing_token_never_requests_sources(self, get):
        from blog.newsletter_importers import import_private_monthly

        with pytest.raises(
            ValueError, match=re.escape("GH_API_SIMONW_PRIVATE_MONTHLY")
        ):
            import_private_monthly()
        get.assert_not_called()
