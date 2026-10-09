import datetime
import io
import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.contrib.postgres.search import SearchQuery
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from bs4 import BeautifulSoup

from .models import Newsletter
from .newsletter_importers import (
    import_substack,
    import_substack_archive,
    import_monthly,
    monthly_records,
    MONTHLY_RAW,
    save_records,
    substack_records,
)

FEED = b"""<rss version="2.0"><channel><item>
<title>A &amp; B</title><link>https://simonw.substack.com/p/a-b</link>
<pubDate>Mon, 05 Oct 2026 17:16:45 GMT</pubDate>
<enclosure url="https://example.com/image.jpg" type="image/jpeg"/>
<description>Duplicate content should not be stored</description>
</item></channel></rss>"""


class NewsletterTests(TestCase):
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
        with self.captureOnCommitCallbacks(execute=True):
            obj.save()
        self.assertTrue(
            Newsletter.objects.filter(search_document=SearchQuery("pangolin")).exists()
        )
        for fields in (
            {"is_public": False},
            {"is_public": True, "is_draft": True},
            {"is_draft": False, "kind": Newsletter.Kind.SUBSTACK},
        ):
            for key, value in fields.items():
                setattr(obj, key, value)
            with self.captureOnCommitCallbacks(execute=True):
                obj.save()
            obj.refresh_from_db()
            self.assertIsNone(obj.search_document)

    def test_validation_separates_listing_and_public_body(self):
        obj = self.sponsor(is_public=False, body="")
        obj.full_clean()
        obj.is_public = True
        with self.assertRaises(ValidationError):
            obj.full_clean()
        obj.kind = Newsletter.Kind.SUBSTACK
        obj.body = "Not metadata"
        with self.assertRaises(ValidationError):
            obj.full_clean()

    def test_substack_import_is_repeatable_and_metadata_only(self):
        records = substack_records(FEED)
        self.assertEqual(
            save_records(records), {"created": 1, "updated": 0, "skipped": 0}
        )
        obj = Newsletter.objects.get()
        self.assertEqual(obj.title, "A & B")
        self.assertEqual(obj.card_image, "https://example.com/image.jpg")
        self.assertEqual(obj.body, "")
        self.assertEqual(obj.created.isoformat(), "2026-10-05T17:16:45+00:00")
        self.assertEqual(save_records(records)["skipped"], 1)
        obj.slug = "my-custom-slug"
        obj.is_draft = True
        obj.metadata["editor_note"] = "Keep this"
        obj.save()
        records[0]["title"] = "Updated title"
        self.assertEqual(save_records(records)["updated"], 1)
        obj.refresh_from_db()
        self.assertEqual(obj.slug, "my-custom-slug")
        self.assertTrue(obj.is_draft)
        self.assertEqual(obj.metadata["editor_note"], "Keep this")

    def test_optional_thumbnail_and_invalid_feed(self):
        records = substack_records(
            FEED.replace(
                b'<enclosure url="https://example.com/image.jpg" type="image/jpeg"/>',
                b"",
            )
        )
        self.assertEqual(records[0]["card_image"], "")
        with self.assertRaises(ValueError):
            substack_records(b"<html/>")

    def test_dry_run_and_invalid_batch_write_nothing(self):
        records = substack_records(FEED)
        self.assertEqual(save_records(records, dry_run=True)["created"], 1)
        self.assertFalse(Newsletter.objects.exists())
        invalid = {**records[0], "import_ref": "invalid", "title": "x" * 256}
        with self.assertRaises(ValidationError):
            save_records([*records, invalid])
        self.assertFalse(Newsletter.objects.exists())

    @patch("blog.newsletter_importers.requests.get")
    def test_substack_import_and_http_failure(self, get):
        get.return_value = Mock(content=FEED)
        self.assertEqual(import_substack()["created"], 1)
        get.assert_called_once_with("https://simonw.substack.com/feed", timeout=30)
        get.return_value.raise_for_status.assert_called_once()
        get.return_value.raise_for_status.side_effect = ValueError("Failed download")
        with self.assertRaises(ValueError):
            import_substack()
        self.assertEqual(Newsletter.objects.count(), 1)

    def test_admin_can_inspect_imported_content(self):
        obj = self.sponsor()
        obj.save()
        self.client.force_login(
            User.objects.create_superuser("newsletters", "n@example.com", "pw")
        )
        self.assertContains(
            self.client.get("/admin/blog/newsletter/"), "Sponsor digest"
        )
        response = self.client.get(f"/admin/blog/newsletter/{obj.pk}/change/")
        self.assertContains(response, "Content and visibility")
        self.assertContains(response, "Import details")
        self.assertNotContains(response, 'name="search_document"')
        self.assertContains(
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
        self.assertContains(response, "Public sponsor issues need their content.")
        obj.refresh_from_db()
        self.assertFalse(obj.is_public)
        data["body"] = "Public pangolin content."
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        obj.refresh_from_db()
        self.assertTrue(obj.is_public)
        self.assertIsNotNone(obj.search_document)
        data["is_draft"] = "on"
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url, data).status_code, 302)
        obj.refresh_from_db()
        self.assertIsNone(obj.search_document)

    @patch("blog.newsletter_importers.requests.get")
    def test_archive_pagination_and_rss_share_identity(self, get):
        post = {
            "title": "A & B",
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
        self.assertEqual(import_substack_archive()["created"], 2)
        self.assertEqual(
            [call.kwargs["params"]["offset"] for call in get.call_args_list],
            [0, 12, 24],
        )
        self.assertEqual(save_records(substack_records(FEED))["skipped"], 1)
        get.side_effect = [
            Mock(json=Mock(return_value=[post])),
            Mock(json=Mock(return_value=[post])),
        ]
        with self.assertRaises(ValueError):
            import_substack_archive()
        self.assertEqual(Newsletter.objects.count(), 2)


class NewsletterImporterViewTests(TestCase):
    def setUp(self):
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
        self.assertContains(response, 'data-importer="substack_latest"')
        self.assertContains(response, 'data-importer="substack_all"')
        self.assertContains(response, "Import latest")
        self.assertContains(response, "Import all")
        self.assertContains(response, "Beat Importers")
        self.client.logout()
        self.assertEqual(self.post("substack_latest").status_code, 302)
        self.client.force_login(User.objects.create_user("reader"))
        self.assertEqual(self.post("substack_all").status_code, 302)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/api/run-importer/").status_code, 405)
        from django.test import Client

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(
            csrf_client.post(
                "/api/run-importer/",
                {"importer": "substack_all"},
                content_type="application/json",
            ).status_code,
            403,
        )

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="")
    @patch("blog.newsletter_importers.requests.get")
    def test_private_button_disabled_without_token(self, get):
        response = self.client.get("/admin/importers/")
        button = BeautifulSoup(response.content, "html.parser").select_one(
            '[data-importer="monthly_private"]'
        )
        self.assertTrue(button.has_attr("disabled"))
        self.assertContains(response, "GH_API_SIMONW_PRIVATE_MONTHLY")
        self.assertEqual(self.post("monthly_private").status_code, 400)
        get.assert_not_called()

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="example-secret-token")
    @patch("blog.newsletter_importers.import_private_monthly")
    def test_private_button_enabled_without_exposing_token(self, importer):
        response = self.client.get("/admin/importers/")
        button = BeautifulSoup(response.content, "html.parser").select_one(
            '[data-importer="monthly_private"]'
        )
        self.assertFalse(button.has_attr("disabled"))
        self.assertNotContains(response, "example-secret-token")
        importer.return_value = {"created": 0, "updated": 0, "skipped": 0, "items": []}
        self.assertEqual(self.post("monthly_private").status_code, 200)
        importer.assert_called_once_with()
        importer.side_effect = ValueError(
            "example-secret-token private response content"
        )
        response = self.post("monthly_private")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("example-secret-token", response.content.decode())
        self.client.logout()
        self.assertEqual(self.post("monthly_private").status_code, 302)

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="")
    @patch("blog.newsletter_importers.requests.get")
    def test_public_monthly_button_imports_batches_without_token(self, get):
        page = self.client.get("/admin/importers/")
        button = BeautifulSoup(page.content, "html.parser").select_one(
            '[data-importer="monthly_public"]'
        )
        self.assertIsNotNone(button)
        self.assertFalse(button.has_attr("disabled"))
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
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post("monthly_public")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["next_offset"], 1)
        self.assertIn("August digest", response.json()["items_html"])
        issue = Newsletter.objects.get()
        self.assertIsNotNone(issue.search_document)
        self.assertIn(issue.get_absolute_url(), response.json()["items_html"])
        response = self.post("monthly_public", offset=1)
        self.assertEqual(response.json()["created"], 1)
        self.assertIsNone(response.json()["next_offset"])
        self.assertEqual(Newsletter.objects.count(), 2)
        self.assertTrue(
            all(call.args[0].startswith(MONTHLY_RAW) for call in get.call_args_list)
        )
        get.reset_mock()
        get.side_effect = [Mock(json=Mock(return_value=[]))]
        self.assertIsNone(self.post("monthly_public").json()["next_offset"])
        for offset in (-1, "0", True, 12000):
            self.assertEqual(
                self.post("monthly_public", offset=offset).status_code, 400
            )
        self.assertEqual(get.call_count, 1)

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
            self.assertEqual(response.status_code, 429)
            self.assertIn("GitHub API rate limit exceeded", response.json()["error"])
            self.assertIn(expected, response.json()["error"])
            self.assertNotIn("example-secret-token", response.content.decode())
        get.return_value = Mock(
            status_code=403,
            headers={},
            json=Mock(return_value={"message": "Resource not accessible"}),
        )
        response = self.post("monthly_private")
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("rate limit", response.json()["error"])
        self.assertFalse(Newsletter.objects.exists())

    @patch("blog.newsletter_importers.requests.get")
    def test_latest_repeat_and_editorial_preservation(self, get):
        get.return_value = Mock(content=FEED)
        result = self.post("substack_latest").json()
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["total"], 1)
        self.assertIn("A &amp; B", result["items_html"])
        obj = Newsletter.objects.get()
        self.assertIn(f"/admin/blog/newsletter/{obj.pk}/change/", result["items_html"])
        obj.slug = "custom"
        obj.is_draft = True
        obj.save()
        self.assertEqual(self.post("substack_latest").json()["skipped"], 1)
        get.return_value = Mock(content=FEED.replace(b"A &amp; B", b"Revised title"))
        self.assertEqual(self.post("substack_latest").json()["updated"], 1)
        obj.refresh_from_db()
        self.assertEqual(obj.slug, "custom")
        self.assertTrue(obj.is_draft)
        self.assertEqual(obj.body, "")
        self.assertEqual(Newsletter.objects.count(), 1)
        get.assert_called_with("https://simonw.substack.com/feed", timeout=30)

    @patch("blog.newsletter_importers.requests.get")
    def test_all_pages_rss_identity_and_end(self, get):
        post = {
            "title": "A & B",
            "canonical_url": "https://simonw.substack.com/p/a-b",
            "post_date": "2026-10-05T17:16:45.123Z",
            "cover_image": "https://example.com/image.jpg",
        }
        save_records(substack_records(FEED))
        get.return_value = Mock(json=Mock(return_value=[post]))
        first = self.post("substack_all").json()
        self.assertEqual(first["skipped"], 1)
        self.assertEqual(first["next_offset"], 12)
        get.return_value = Mock(
            json=Mock(
                return_value=[
                    {**post, "canonical_url": "https://simonw.substack.com/p/older"}
                ]
            )
        )
        second = self.post("substack_all", offset=12).json()
        self.assertEqual(second["created"], 1)
        self.assertEqual(second["next_offset"], 24)
        get.return_value = Mock(json=Mock(return_value=[]))
        last = self.post("substack_all", offset=24).json()
        self.assertIsNone(last["next_offset"])
        self.assertEqual(Newsletter.objects.count(), 2)
        self.assertEqual(
            [call.kwargs["params"]["offset"] for call in get.call_args_list],
            [0, 12, 24],
        )

    @patch("blog.newsletter_importers.requests.get")
    def test_failed_batch_and_validation(self, get):
        get.return_value = Mock(json=Mock(return_value={"error": "broken"}))
        response = self.post("substack_all")
        self.assertEqual(response.status_code, 500)
        self.assertIn("Expected a list", response.json()["error"])
        self.assertEqual(Newsletter.objects.count(), 0)
        get.reset_mock()
        for offset in (-12, 1, 12000, "12", True):
            self.assertEqual(self.post("substack_all", offset=offset).status_code, 400)
        get.assert_not_called()


class NewsletterPageTests(TestCase):
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
        self.assertEqual(
            list(response.context["newsletters"]), [external, private, public]
        )
        soup = BeautifulSoup(response.content, "html.parser")
        links = [a["href"] for a in soup.select(".newsletter-list h3 a")]
        self.assertEqual(
            links, [external.url, private.url, "/newsletters/monthly-example/"]
        )
        self.assertEqual(soup.select_one(".newsletter-list img")["loading"], "lazy")
        self.assertContains(response, "Sponsors only")
        prompt = soup.select_one(".newsletter-sponsors-only")
        self.assertIn("Private issue", prompt.text)
        self.assertEqual(
            prompt.select_one(".newsletter-sponsor-link")["href"],
            "https://github.com/sponsors/simonw/",
        )
        self.assertEqual(
            prompt.select_one(".newsletter-existing-sponsor a")["href"], private.url
        )
        self.assertEqual(len(soup.select(".newsletter-sponsor-prompt")), 1)
        self.assertNotContains(response, "Hidden draft")
        self.assertNotContains(response, "Unreleased secret content")
        self.assertEqual(public.get_absolute_url(), "/newsletters/monthly-example/")
        self.assertEqual(external.get_absolute_url(), external.url)
        self.assertEqual(private.get_absolute_url(), private.url)

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
        self.assertEqual(
            [n.slug for n in response.context["newsletters"]],
            [f"issue-{i}" for i in range(54, 44, -1)],
        )
        self.assertNotIn("page_obj", response.context)
        soup = BeautifulSoup(response.content, "html.parser")
        self.assertEqual(
            [a["href"] for a in soup.select(".newsletter-years li a")],
            ["/newsletters/2026/", "/newsletters/2025/"],
        )
        response = self.client.get("/newsletters/2026/")
        self.assertEqual(len(response.context["newsletters"]), 55)
        self.assertNotContains(response, "Older issue")
        self.assertEqual(
            list(self.client.get("/newsletters/2025/").context["newsletters"]), [older]
        )
        for year in (2024, 2023, "0000"):
            self.assertEqual(self.client.get(f"/newsletters/{year}/").status_code, 404)

    def test_year_slugs_are_reserved(self):
        issue = Newsletter(
            kind="substack", title="Example", slug="2026", url="https://example.com/"
        )
        with self.assertRaises(ValidationError):
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
            self.assertEqual(response.status_code, 200)
            items = response.context["items"]
            self.assertEqual(
                {item["obj"].pk for item in items}, {public.pk, private.pk, substack.pk}
            )
            soup = BeautifulSoup(response.content, "html.parser")
            self.assertEqual(len(soup.select('[data-type="newsletter"]')), 3)
            self.assertContains(response, public.get_absolute_url())
            self.assertContains(response, private.url)
            self.assertContains(response, substack.url)
            self.assertContains(response, "Public preview heading")
            self.assertNotContains(response, "Private body must not leak")
            self.assertNotContains(response, "Full public body")
            self.assertNotContains(response, "Draft newsletter")
            self.assertEqual(
                soup.select_one('[data-type="newsletter"] img')["loading"], "lazy"
            )
            self.assertContains(response, 'title="3 newsletters"')
        self.assertContains(response, "3 newsletters")
        self.assertNotContains(response, "/search/?type=newsletter")

    def test_year_archive_counts_newsletters_without_listing_titles(self):
        self.issue(title="Never list this title")
        self.issue(slug="second", title="Second newsletter", is_public=False)
        self.issue(slug="draft", is_draft=True)
        self.issue(
            slug="october",
            created=datetime.datetime(2026, 10, 3, tzinfo=datetime.timezone.utc),
        )
        response = self.client.get("/2026/")
        self.assertContains(response, "2 newsletters")
        self.assertContains(response, "1 newsletter")
        self.assertNotContains(response, "Never list this title")
        self.assertNotContains(response, "Second newsletter")
        self.assertEqual(
            [month["date"].month for month in response.context["months"]], [9, 10]
        )
        self.assertTrue(
            all(not month["entries"] for month in response.context["months"])
        )

    def test_day_navigation_and_calendar_skip_draft_newsletters(self):
        for day, draft in ((2, False), (3, True), (4, False), (5, True), (6, False)):
            self.issue(
                slug=f"day-{day}",
                is_draft=draft,
                created=datetime.datetime(2026, 9, day, tzinfo=datetime.timezone.utc),
            )
        response = self.client.get("/2026/Sep/4/")
        self.assertEqual(response.context["previous_day"], datetime.date(2026, 9, 2))
        self.assertEqual(response.context["next_day"], datetime.date(2026, 9, 6))
        self.assertNotContains(response, 'href="/2026/Sep/3/"')
        self.assertNotContains(response, 'href="/2026/Sep/5/"')
        self.assertEqual(self.client.get("/2026/Sep/3/").status_code, 404)

    def test_newsletters_remain_absent_from_homepage_and_tag_pages(self):
        from .factories import EntryFactory
        from .models import Tag

        entry = EntryFactory()
        entry.tags.add(Tag.objects.create(tag="example"))
        self.issue(title="Newsletter stays separate")
        for url in ("/", "/tags/example/"):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Newsletter stays separate")

    def test_preview_headings_are_plain_text_and_shown_for_all_monthly_issues(self):
        issue = self.issue(
            is_public=False,
            body="",
            preview_headings=" First topic \n\nA <script>heading</script>\nLast topic",
        )
        self.assertEqual(
            issue.preview_heading_list(),
            ["First topic", "A <script>heading</script>", "Last topic"],
        )
        for url in ("/newsletters/", "/newsletters/2026/"):
            response = self.client.get(url)
            self.assertContains(response, "A &lt;script&gt;heading&lt;/script&gt;")
            soup = BeautifulSoup(response.content, "html.parser")
            self.assertEqual(
                [li.text for li in soup.select(".newsletter-preview-headings li")],
                issue.preview_heading_list(),
            )
            self.assertIsNone(soup.select_one(".newsletter-preview-headings script"))
        self.assertEqual(issue.index_components(), {})
        issue.is_public = True
        issue.body = "Public content"
        issue.save()
        for url in ("/newsletters/", "/newsletters/2026/"):
            response = self.client.get(url)
            self.assertContains(response, "First topic")
            self.assertContains(response, "A &lt;script&gt;heading&lt;/script&gt;")
            self.assertNotContains(response, "Read this issue on GitHub")
        self.assertNotIn("First topic", issue.index_components()["C"])
        issue.kind = "substack"
        issue.is_public = False
        issue.save()
        self.assertNotContains(self.client.get("/newsletters/"), "First topic")

    def test_detail_renders_markdown_with_entry_layout_and_one_title(self):
        issue = self.issue()
        response = self.client.get(issue.get_absolute_url())
        self.assertTemplateUsed(response, "item_base.html")
        soup = BeautifulSoup(response.content, "html.parser")
        body = soup.select_one(".newsletter-body")
        self.assertEqual(body.select_one("strong").text, "world")
        self.assertEqual(body.select_one("h2#section").text, "Section")
        self.assertIsNotNone(body.select_one("table"))
        self.assertIsNotNone(body.select_one("pre code.language-python"))
        self.assertIsNone(body.select_one("h1"))
        self.assertEqual(
            len([h for h in body.select("h2") if h.text == issue.title]), 1
        )
        self.assertContains(response, 'href="/newsletters/"')
        breadcrumbs = soup.select_one('nav[aria-label="Breadcrumb"]')
        self.assertEqual(
            [a["href"] for a in breadcrumbs.select("a")],
            ["/newsletters/", "/newsletters/2026/"],
        )
        self.assertEqual(
            breadcrumbs.select_one('[aria-current="page"]').text, issue.title
        )

    def test_unreleased_drafts_external_and_missing_issues_have_no_local_page(self):
        for overrides in (
            {"is_public": False},
            {"is_draft": True},
            {"kind": "substack", "body": ""},
            {"body": ""},
        ):
            issue = self.issue(slug=f"issue-{Newsletter.objects.count()}", **overrides)
            response = self.client.get(reverse("newsletter_detail", args=[issue.slug]))
            self.assertEqual(response.status_code, 404)
            self.assertNotContains(response, "Hello", status_code=404)
        self.assertEqual(self.client.get("/newsletters/missing/").status_code, 404)

    def test_empty_index_and_existing_substack_shortcut(self):
        self.assertContains(self.client.get("/newsletters/"), "No newsletters yet.")
        self.assertRedirects(
            self.client.get("/newsletter/"),
            "https://simonw.substack.com/",
            fetch_redirect_response=False,
        )


class NewsletterSearchTests(TestCase):
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
        with self.captureOnCommitCallbacks(execute=True):
            issue = Newsletter.objects.create(**fields)
        issue.refresh_from_db()
        return issue

    def context(self, **params):
        from .search import search

        return search(RequestFactory().get("/search/", params), return_context=True)

    def test_title_and_body_search_mixed_results_and_local_links(self):
        from .factories import EntryFactory

        issue = self.issue()
        with self.captureOnCommitCallbacks(execute=True):
            entry = EntryFactory(
                title="Pangolin article", body="<p>A regular article.</p>"
            )
        response = self.client.get("/search/", {"q": "pangolin"})
        self.assertEqual(response.context["total"], 2)
        self.assertEqual(
            {result["type"] for result in response.context["results"]},
            {"entry", "newsletter"},
        )
        self.assertContains(response, issue.get_absolute_url())
        self.assertContains(response, entry.get_absolute_url())
        self.assertContains(response, "Monthly newsletter")
        self.assertContains(response, "A capybara and a quokka.")
        self.assertNotContains(response, "Hiddenpreviewtoken")
        self.assertIn(
            {"type": "newsletter", "label": "Newsletter", "n": 1},
            response.context["type_counts"],
        )
        self.assertEqual(self.context(q="capybara")["total"], 1)
        self.assertEqual(self.context(q="hiddenpreviewtoken")["total"], 0)

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
            self.assertEqual(context["total"], 1)
            self.assertEqual(context["results"][0]["obj"].pk, public.pk)
            self.assertEqual(
                context["type_counts"],
                [{"type": "newsletter", "label": "Newsletter", "n": 1}],
            )

    def test_type_and_date_filters_use_original_send_date(self):
        issue = self.issue()
        january = self.context(type="newsletter", year="2026", month="1")
        self.assertEqual(january["total"], 1)
        self.assertEqual(january["selected"]["type_label"], "Newsletter")
        self.assertEqual(january["title"], "Newsletters in January, 2026")
        self.assertEqual(january["year_counts"][0]["year"].year, 2026)
        self.assertEqual(january["month_counts"][0]["month"].month, 1)
        self.assertEqual(january["tag_counts"], [])
        for params in (
            {"type": "entry"},
            {"year": "2025"},
            {"month": "12"},
            {"q": "capybara to:2026-01-02"},
        ):
            self.assertEqual(self.context(**params)["total"], 0)
        self.assertEqual(
            self.context(q="capybara from:2026-01-02 to:2026-01-03")["total"], 1
        )

    def test_tags_exclude_untagged_newsletters_but_negative_filters_allow_them(self):
        from .factories import EntryFactory
        from .models import Tag

        self.issue()
        tag = Tag.objects.create(tag="animals")
        with self.captureOnCommitCallbacks(execute=True):
            entry = EntryFactory(title="Pangolin article", body="<p>capybara</p>")
            entry.tags.add(tag)
        context = self.context(q="pangolin", tag="animals")
        self.assertEqual([result["type"] for result in context["results"]], ["entry"])
        self.assertEqual(self.context(type="newsletter", tag="animals")["total"], 0)
        context = self.context(q="pangolin", **{"exclude.tag": "animals"})
        self.assertEqual(
            [result["type"] for result in context["results"]], ["newsletter"]
        )

    def test_search_changes_when_issue_is_published_edited_or_hidden(self):
        issue = self.issue(is_public=False)
        self.assertEqual(self.context(q="capybara")["total"], 0)
        issue.is_public = True
        with self.captureOnCommitCallbacks(execute=True):
            issue.save()
        self.assertEqual(self.context(q="capybara")["total"], 1)
        issue.body = "An aardvark"
        with self.captureOnCommitCallbacks(execute=True):
            issue.save()
        self.assertEqual(self.context(q="capybara")["total"], 0)
        self.assertEqual(self.context(q="aardvark")["total"], 1)
        issue.is_draft = True
        with self.captureOnCommitCallbacks(execute=True):
            issue.save()
        self.assertEqual(self.context(q="aardvark")["total"], 0)

    def test_bulk_tagging_excludes_newsletters(self):
        self.issue()
        self.client.force_login(
            User.objects.create_superuser("tagger", "t@example.com", "pw")
        )
        response = self.client.get("/admin/bulk-tag/", {"q": "pangolin"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 0)
        self.assertEqual(response.context["type_counts"], [])

    def test_id_filter_and_pagination(self):
        from .search import search

        issues = [
            self.issue(
                created=datetime.datetime(2026, 1, day, tzinfo=datetime.timezone.utc)
            )
            for day in range(1, 4)
        ]
        response = self.client.get("/search/", {"newsletters": str(issues[0].pk)})
        self.assertEqual(response.context["total"], 1)
        self.assertContains(response, "Filtered to specific newsletters")
        self.assertEqual(
            BeautifulSoup(response.content, "html.parser").select_one(
                ".id-filter-notice a"
            )["href"],
            "?",
        )
        context = search(
            RequestFactory().get("/search/", {"type": "newsletter", "page": 2}),
            return_context=True,
            per_page=2,
        )
        self.assertEqual(context["total"], 3)
        self.assertEqual(
            [result["obj"].pk for result in context["results"]], [issues[0].pk]
        )

    def test_reindex_all_rebuilds_public_and_clears_private_documents(self):
        public = self.issue()
        private = self.issue(is_public=False)
        Newsletter.objects.filter(pk=private.pk).update(
            search_document=public.search_document
        )
        Newsletter.objects.filter(pk=public.pk).update(search_document=None)
        with self.captureOnCommitCallbacks(execute=True):
            call_command("reindex_all", stdout=io.StringIO())
        public.refresh_from_db()
        private.refresh_from_db()
        self.assertIsNotNone(public.search_document)
        self.assertIsNone(private.search_document)


class MonthlyImportTests(TestCase):
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
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(import_monthly()["created"], 1)
        issue = Newsletter.objects.get()
        self.assertEqual(issue.created.isoformat(), "2026-09-04T05:50:18+00:00")
        self.assertEqual(issue.body, self.body.strip())
        self.assertEqual(issue.title, "August digest")
        self.assertEqual(issue.preview_heading_list(), ["First topic", "Second topic"])
        self.assertTrue(issue.is_public)
        self.assertIsNotNone(issue.search_document)
        self.assertEqual(issue.metadata["issue_month"], "2026-08")
        self.assertEqual(
            [c.args[0] for c in get.call_args_list],
            [
                MONTHLY_RAW + "/index.json",
                MONTHLY_RAW + "/" + self.filename,
            ],
        )
        # Reimports use the established send date, with no API request.
        get.reset_mock()
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text=self.body),
        ]
        self.assertEqual(import_monthly()["skipped"], 1)
        self.assertEqual(get.call_count, 2)

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
        self.assertEqual(import_monthly()["updated"], 1)
        existing.refresh_from_db()
        self.assertEqual(existing.preview_heading_list(), ["First topic", "Second topic"])
        self.assertEqual(Newsletter.objects.count(), 1)

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
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(import_monthly()["updated"], 1)
        existing.refresh_from_db()
        self.assertEqual(Newsletter.objects.count(), 1)
        self.assertTrue(existing.is_searchable)
        self.assertIsNotNone(existing.search_document)
        self.assertEqual(existing.slug, "existing-monthly")
        self.assertEqual(existing.created, date)
        self.assertEqual(existing.preview_headings, "A preview")
        self.assertEqual(existing.metadata["editor_note"], "Keep")

    @patch("blog.newsletter_importers.requests.get")
    def test_dry_run_fallback_title_and_index_date(self, get):
        get.side_effect = [
            self.response([self.index_entry()]),
            self.response(text="An issue without a heading. Café."),
        ]
        records = monthly_records()
        self.assertEqual(records[0]["title"], "LLM digest: August 2026")
        self.assertIn("Café", records[0]["body"])
        self.assertEqual(records[0]["created"].day, 4)
        self.assertEqual(save_records(records, dry_run=True)["created"], 1)
        self.assertFalse(Newsletter.objects.exists())

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
            with self.assertRaises(ValueError):
                import_monthly()
            self.assertEqual(get.call_count, 1)
        self.assertFalse(Newsletter.objects.exists())

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
        with self.assertRaises(requests.HTTPError):
            import_monthly()
        self.assertFalse(Newsletter.objects.exists())

    @patch("blog.newsletter_importers.requests.get")
    def test_missing_or_invalid_send_date_is_not_guessed(self, get):
        for sent_at in (None, "", "invalid", "2026-09-04T00:00:00"):
            get.reset_mock()
            get.return_value = self.response([self.index_entry(sent_at=sent_at)])
            with self.assertRaises(ValueError):
                import_monthly()
            self.assertEqual(get.call_count, 1)
        self.assertFalse(Newsletter.objects.exists())


@override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="example-secret-token")
class PrivateMonthlyApiTests(TestCase):
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
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(import_private_monthly()["created"], 1)
        issue = Newsletter.objects.get()
        self.assertEqual(issue.title, "September digest")
        self.assertEqual(
            issue.preview_heading_list(), ["First heading", "Second heading"]
        )
        self.assertEqual(issue.created.isoformat(), "2026-10-03T21:21:39+00:00")
        self.assertEqual(issue.body, "")
        self.assertFalse(issue.is_public)
        self.assertIsNone(issue.search_document)
        self.assertNotIn("PRIVATE BODY", json.dumps(issue.metadata))
        for call in get.call_args_list:
            if call.args[0].startswith("https://api.github.com/"):
                self.assertEqual(
                    call.kwargs["headers"]["Authorization"],
                    "Bearer example-secret-token",
                )
                self.assertFalse(call.kwargs["allow_redirects"])
            else:
                self.assertNotIn("headers", call.kwargs)
        issue.preview_headings = "Curated preview"
        issue.save()
        get.side_effect = [public_index, listing, body]
        self.assertEqual(import_private_monthly()["skipped"], 1)
        issue.refresh_from_db()
        self.assertEqual(issue.preview_headings, "Curated preview")
        # Already-public local issues must not be demoted even if the public index is stale.
        issue.is_public = True
        issue.body = "Now public"
        issue.save()
        get.side_effect = [public_index, listing]
        self.assertEqual(import_private_monthly()["created"], 0)
        issue.refresh_from_db()
        self.assertTrue(issue.is_public)

    @override_settings(GH_API_SIMONW_PRIVATE_MONTHLY="")
    @patch("blog.newsletter_importers.requests.get")
    def test_missing_token_never_requests_sources(self, get):
        from blog.newsletter_importers import import_private_monthly

        with self.assertRaisesMessage(ValueError, "GH_API_SIMONW_PRIVATE_MONTHLY"):
            import_private_monthly()
        get.assert_not_called()
