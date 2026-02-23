import re

from django.test import TransactionTestCase
from django.contrib.auth.models import User
from blog.templatetags.entry_tags import do_typography_string
from .factories import (
    ChapterFactory,
    EntryFactory,
    BlogmarkFactory,
    GuideFactory,
    QuotationFactory,
    NoteFactory,
    BeatFactory,
    SponsorMessageFactory,
)
from blog.models import Tag, PreviousTagName, TagMerge, ChapterChange
from django.utils import timezone
import datetime
from datetime import timedelta
import json
import xml.etree.ElementTree as ET


class BlogTests(TransactionTestCase):
    def test_homepage(self):
        db_entries = [
            EntryFactory(),
            EntryFactory(),
            EntryFactory(),
        ]
        BlogmarkFactory()
        QuotationFactory()
        NoteFactory()
        response = self.client.get("/")
        entries = response.context["entries"]
        self.assertEqual(
            [e.pk for e in entries],
            [e.pk for e in sorted(db_entries, key=lambda e: e.created, reverse=True)],
        )

    def test_django_header_plugin(self):
        response = self.client.get("/")
        self.assertIn("Django-Composition", response)

    def test_other_pages(self):
        entry = EntryFactory()
        blogmark = BlogmarkFactory()
        quotation = QuotationFactory()
        note = NoteFactory()
        for path in (
            "/",
            "/{}/".format(entry.created.year),
            entry.get_absolute_url(),
            blogmark.get_absolute_url(),
            quotation.get_absolute_url(),
            note.get_absolute_url(),
            "/{}/".format(entry.created.year),
            "/atom/everything/",
        ):
            response = self.client.get(path)
            assert response.status_code == 200

    def test_entry(self):
        entry = EntryFactory()
        response = self.client.get(entry.get_absolute_url())
        self.assertTemplateUsed(response, "entry.html")
        self.assertEqual(response.context["entry"].pk, entry.pk)

    def test_blogmark(self):
        blogmark = BlogmarkFactory()
        response = self.client.get(blogmark.get_absolute_url())
        self.assertTemplateUsed(response, "blogmark.html")
        self.assertEqual(response.context["blogmark"].pk, blogmark.pk)

    def test_quotation(self):
        quotation = QuotationFactory()
        response = self.client.get(quotation.get_absolute_url())
        self.assertTemplateUsed(response, "quotation.html")
        self.assertEqual(response.context["quotation"].pk, quotation.pk)

    def test_note(self):
        note = NoteFactory()
        response = self.client.get(note.get_absolute_url())
        self.assertTemplateUsed(response, "note.html")
        self.assertEqual(response.context["note"].pk, note.pk)

    def test_cache_header_for_old_content(self):
        old_date = timezone.now() - datetime.timedelta(days=181)
        entry = EntryFactory(created=old_date)
        response = self.client.get(entry.get_absolute_url())
        assert response.headers["cache-control"] == "s-maxage=%d" % (24 * 60 * 60)

    def test_no_cache_header_for_recent_content(self):
        recent_entry = EntryFactory(created=timezone.now())
        response = self.client.get(recent_entry.get_absolute_url())
        assert "cache-control" not in response.headers

    def test_archive_year(self):
        quotation = QuotationFactory()
        response = self.client.get("/{}/".format(quotation.created.year))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "archive_year.html")

    def test_markup(self):
        entry = EntryFactory(
            title="Hello & goodbye",
            body="<p>First paragraph</p><p>Second paragraph</p>",
        )
        response = self.client.get(entry.get_absolute_url())
        self.assertContains(
            response,
            """
            <h2>Hello &amp; goodbye</h2>
        """,
            html=True,
        )
        self.assertContains(
            response,
            """
            <p>First paragraph</p><p>Second paragraph</p>
        """.strip(),
        )

    def test_update_blogmark_runs_commit_hooks(self):
        # This was throwing errors on upgrade Django 2.2 to 2.2.1
        blogmark = BlogmarkFactory()
        assert blogmark.pk
        blogmark.commentary = "hello there"
        blogmark.save()

    def test_do_typography_string(self):
        for input, expected in (
            ("Hello, world", "Hello, world"),
            ('Hello, "world"!', "Hello, “world”!"),
            ("Hello, world's!", "Hello, world’s!"),
            ('Hello, <"world"!', "Hello, <“world”!"),
            # Do not do these ones:
            ('Hello, <"world">!', 'Hello, <"world">!'),
            ("Hello, <'world'>!", "Hello, <'world'>!"),
            # This caused a recursion error at one point
            (
                """Should you pin your library's dependencies using "click>=7,<8" or "click~=7.0"? Henry Schreiner's short answer is no, and his long answer is an exhaustive essay covering every conceivable aspect of this thorny Python packaging problem.""",
                'Should you pin your library\'s dependencies using "click>=7,<8" or "click~=7.0"? Henry Schreiner\'s short answer is no, and his long answer is an exhaustive essay covering every conceivable aspect of this thorny Python packaging problem.',
            ),
        ):
            self.assertEqual(do_typography_string(input), expected)

    def test_rename_tag_creates_previous_tag_name(self):
        tag = Tag.objects.create(tag="old-name")
        tag.entry_set.create(
            title="Test entry",
            body="Test entry body",
            created="2020-01-01T00:00:00+00:00",
        )
        assert self.client.get("/tags/old-name/").status_code == 200
        assert self.client.get("/tags/new-name/").status_code == 404
        tag.rename_tag("new-name")
        self.assertEqual(tag.tag, "new-name")
        previous_tag_name = PreviousTagName.objects.get(tag=tag)
        self.assertEqual(previous_tag_name.previous_name, "old-name")
        assert self.client.get("/tags/old-name/").status_code == 301
        assert self.client.get("/tags/new-name/").status_code == 200

    def test_tag_with_hyphen(self):
        tag = Tag.objects.create(tag="tag-with-hyphen")
        self.assertEqual(tag.tag, "tag-with-hyphen")

    def test_draft_items_not_displayed(self):
        draft_entry = EntryFactory(is_draft=True, title="draftentry")
        draft_blogmark = BlogmarkFactory(is_draft=True, link_title="draftblogmark")
        draft_quotation = QuotationFactory(is_draft=True, source="draftquotation")
        draft_note = NoteFactory(is_draft=True, body="draftnote")
        testing = Tag.objects.get_or_create(tag="testing")[0]

        live_entry = EntryFactory(title="publishedentry", created=draft_entry.created)
        live_blogmark = BlogmarkFactory(
            link_title="publishedblogmark", created=draft_blogmark.created
        )
        live_quotation = QuotationFactory(
            source="publishedquotation", created=draft_quotation.created
        )
        live_note = NoteFactory(body="publishednote", created=draft_note.created)

        for obj in (
            draft_entry,
            draft_blogmark,
            draft_quotation,
            draft_note,
            live_entry,
            live_blogmark,
            live_quotation,
            live_note,
        ):
            obj.tags.add(testing)

        paths = (
            "/",  # Homepage
            "/{}/".format(draft_entry.created.year),
            "/{}/{}/".format(
                draft_entry.created.year, draft_entry.created.strftime("%b")
            ),
            "/{}/{}/{}/".format(
                draft_entry.created.year,
                draft_entry.created.strftime("%b"),
                draft_entry.created.day,
            ),
            "/search/?q=testing",
            "/tags/testing/",
            live_entry.get_absolute_url(),
        )

        counts = json.loads(self.client.get("/tags-autocomplete/?q=testing").content)
        assert counts == {
            "tags": [
                {
                    "id": testing.id,
                    "tag": "testing",
                    "description": "",
                    "total_entry": 1,
                    "total_blogmark": 1,
                    "total_quotation": 1,
                    "total_note": 1,
                    "total_beat": 0,
                    "is_exact_match": 1,
                    "count": 4,
                }
            ]
        }

        for path in paths:
            response = self.client.get(path)
            self.assertNotContains(response, "draftentry")

        robots_fragment = '<meta name="robots" content="noindex">'
        draft_warning_fragment = "This is a draft post"

        for obj in (draft_entry, draft_blogmark, draft_quotation, draft_note):
            response2 = self.client.get(obj.get_absolute_url())
            self.assertContains(response2, robots_fragment)
            self.assertContains(response2, draft_warning_fragment)
            assert (
                response2.headers["cache-control"]
                == "private, no-cache, no-store, must-revalidate"
            )

            # Publish it
            obj.is_draft = False
            obj.save()

            response3 = self.client.get(obj.get_absolute_url())
            self.assertNotContains(response3, robots_fragment)
            self.assertNotContains(response3, draft_warning_fragment)
            assert "cache-control" not in response3.headers

        counts2 = json.loads(self.client.get("/tags-autocomplete/?q=testing").content)
        assert counts2 == {
            "tags": [
                {
                    "id": testing.id,
                    "tag": "testing",
                    "description": "",
                    "total_entry": 2,
                    "total_blogmark": 2,
                    "total_quotation": 2,
                    "total_note": 2,
                    "total_beat": 0,
                    "is_exact_match": 1,
                    "count": 8,
                }
            ]
        }

        for path in paths:
            response4 = self.client.get(path)
            self.assertContains(response4, "draftentry")

    def test_draft_items_not_in_feeds(self):
        draft_entry = EntryFactory(is_draft=True, title="draftentry")
        draft_blogmark = BlogmarkFactory(is_draft=True, link_title="draftblogmark")
        draft_quotation = QuotationFactory(is_draft=True, source="draftquotation")

        response1 = self.client.get("/atom/entries/")
        self.assertNotContains(response1, draft_entry.title)

        response2 = self.client.get("/atom/links/")
        self.assertNotContains(response2, draft_blogmark.link_title)

        response3 = self.client.get("/atom/everything/")
        self.assertNotContains(response3, draft_entry.title)
        self.assertNotContains(response3, draft_blogmark.link_title)
        self.assertNotContains(response3, draft_quotation.source)

        # Change draft status and check they show up
        draft_entry.is_draft = False
        draft_entry.save()

        draft_blogmark.is_draft = False
        draft_blogmark.save()

        draft_quotation.is_draft = False
        draft_quotation.save()

        response4 = self.client.get("/atom/entries/")
        self.assertContains(response4, draft_entry.title)

        response5 = self.client.get("/atom/links/")
        self.assertContains(response5, draft_blogmark.link_title)

        response6 = self.client.get("/atom/everything/")
        self.assertContains(response6, draft_entry.title)
        self.assertContains(response6, draft_blogmark.link_title)
        self.assertContains(response6, draft_quotation.source)

    def test_entries_feed_includes_subscribe_note(self):
        EntryFactory()
        response = self.client.get("/atom/entries/")
        self.assertIn(
            "You are only seeing the",
            response.content.decode(),
        )

    def test_og_description_strips_markdown(self):
        blogmark = BlogmarkFactory(
            commentary="This **has** *markdown*", use_markdown=True
        )
        response = self.client.get(blogmark.get_absolute_url())
        self.assertContains(
            response,
            '<meta property="og:description" content="This has markdown"',
            html=False,
        )

        note = NoteFactory(body="A note with **bold** text")
        response2 = self.client.get(note.get_absolute_url())
        self.assertContains(
            response2,
            '<meta property="og:description" content="A note with bold text"',
            html=False,
        )

    def test_og_description_escapes_quotes(self):
        blogmark = BlogmarkFactory(
            commentary='Fun new "live music model" release', use_markdown=True
        )
        response = self.client.get(blogmark.get_absolute_url())
        self.assertContains(
            response,
            '<meta property="og:description" content="Fun new &quot;live music model&quot; release"',
            html=False,
        )

    def test_blogmark_title_used_for_page_and_feed(self):
        blogmark_with_title = BlogmarkFactory(
            link_title="Link Title", title="Custom Title"
        )
        blogmark_without_title = BlogmarkFactory(link_title="Another Link")

        # Page title uses custom title if provided
        response = self.client.get(blogmark_with_title.get_absolute_url())
        self.assertContains(response, "<title>Custom Title</title>", html=False)

        response2 = self.client.get(blogmark_without_title.get_absolute_url())
        self.assertContains(response2, "<title>Another Link</title>", html=False)

        # Atom feeds use title if present otherwise link_title
        feed_response = self.client.get("/atom/links/")
        root = ET.fromstring(feed_response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        titles = [e.find("atom:title", ns).text for e in root.findall("atom:entry", ns)]
        self.assertIn("Custom Title", titles)
        self.assertIn("Another Link", titles)
        self.assertNotIn("Link Title", titles)

        feed_response2 = self.client.get("/atom/everything/")
        root2 = ET.fromstring(feed_response2.content)
        titles2 = [
            e.find("atom:title", ns).text for e in root2.findall("atom:entry", ns)
        ]
        self.assertIn("Custom Title", titles2)
        self.assertIn("Another Link", titles2)
        self.assertNotIn("Link Title", titles2)

    def test_og_description_escapes_quotes_entry(self):
        entry = EntryFactory(body='<p>Entry with "quotes" in it</p>')
        response = self.client.get(entry.get_absolute_url())
        self.assertContains(
            response,
            '<meta property="og:description" content="Entry with “quotes” in it"',
            html=False,
        )

    def test_og_description_escapes_quotes_note(self):
        note = NoteFactory(body='Note with "quotes" inside')
        response = self.client.get(note.get_absolute_url())
        self.assertContains(
            response,
            '<meta property="og:description" content="Note with &quot;quotes&quot; inside"',
            html=False,
        )

    def test_og_description_escapes_quotes_quotation(self):
        quotation = QuotationFactory(quotation='A "quoted" statement', source="Someone")
        response = self.client.get(quotation.get_absolute_url())
        self.assertContains(
            response,
            '<meta property="og:description" content="A &quot;quoted&quot; statement"',
            html=False,
        )

    def test_og_description_escapes_quotes_tag_page(self):
        tag = Tag.objects.create(tag="test", description='Tag with "quotes"')
        entry = EntryFactory()
        entry.tags.add(tag)
        response = self.client.get("/tags/test/")
        self.assertContains(
            response,
            '<meta property="og:description" content="1 posts tagged ‘test’. Tag with &quot;quotes&quot;"',
            html=False,
        )

    def test_top_tags_page(self):
        for i in range(1, 12):
            tag = Tag.objects.create(tag=f"tag{i}")
            for j in range(i):
                entry = EntryFactory(title=f"Entry{i}-{j}")
                entry.tags.add(tag)
        response = self.client.get("/top-tags/")
        assert response.status_code == 200
        tags_info = response.context["tags_info"]
        self.assertEqual(len(tags_info), 10)
        self.assertEqual(tags_info[0]["tag"].tag, "tag11")
        self.assertFalse(any(info["tag"].tag == "tag1" for info in tags_info))
        latest = Tag.objects.get(tag="tag11").entry_set.order_by("-created")[0].title
        self.assertContains(response, latest)

    def test_search_title_displays_full_month_name(self):
        tag = Tag.objects.create(tag="llm-release")
        entry = EntryFactory(
            created=datetime.datetime(2025, 7, 1, tzinfo=datetime.timezone.utc)
        )
        entry.tags.add(tag)
        response = self.client.get("/search/?tag=llm-release&year=2025&month=7")
        self.assertContains(
            response,
            "Posts tagged llm-release in July, 2025",
        )

    def test_quotations_feed(self):
        quotation = QuotationFactory(source="Test Source")
        response = self.client.get("/atom/quotations/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])
        self.assertContains(response, "Quotations")
        self.assertContains(response, "Test Source")

    def test_notes_feed(self):
        note = NoteFactory(body="Test note body content")
        response = self.client.get("/atom/notes/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/xml", response["Content-Type"])
        self.assertContains(response, "Notes")
        self.assertContains(response, "Test note body content")

    def test_draft_items_not_in_quotations_feed(self):
        draft_quotation = QuotationFactory(is_draft=True, source="draftquotationsource")
        response = self.client.get("/atom/quotations/")
        self.assertNotContains(response, "draftquotationsource")
        draft_quotation.is_draft = False
        draft_quotation.save()
        response2 = self.client.get("/atom/quotations/")
        self.assertContains(response2, "draftquotationsource")

    def test_draft_items_not_in_notes_feed(self):
        draft_note = NoteFactory(is_draft=True, body="draftnotebody")
        response = self.client.get("/atom/notes/")
        self.assertNotContains(response, "draftnotebody")
        draft_note.is_draft = False
        draft_note.save()
        response2 = self.client.get("/atom/notes/")
        self.assertContains(response2, "draftnotebody")

    def test_quotations_feed_has_cors_and_cache_headers(self):
        QuotationFactory()
        response = self.client.get("/atom/quotations/")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        self.assertIn("s-maxage", response["Cache-Control"])

    def test_notes_feed_has_cors_and_cache_headers(self):
        NoteFactory()
        response = self.client.get("/atom/notes/")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        self.assertIn("s-maxage", response["Cache-Control"])

    def test_archive_month_shows_search_and_counts(self):
        created = datetime.datetime(2025, 7, 1, tzinfo=datetime.timezone.utc)
        EntryFactory(created=created)
        EntryFactory(created=created)
        BlogmarkFactory(created=created)
        QuotationFactory(created=created)
        response = self.client.get("/2025/Jul/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<input type="hidden" name="year" value="2025">',
        )
        self.assertContains(
            response,
            '<input type="hidden" name="month" value="7">',
        )
        self.assertContains(response, "4 posts:")
        self.assertContains(response, ">2 entries</a>")
        self.assertContains(response, ">1 link</a>")
        self.assertContains(response, ">1 quote</a>")
        self.assertContains(
            response,
            "/search/?type=entry&year=2025&month=7",
        )
        self.assertContains(
            response,
            "/search/?type=blogmark&year=2025&month=7",
        )
        self.assertContains(
            response,
            "/search/?type=quotation&year=2025&month=7",
        )
        # The summary line (e.g. "4 posts: 2 entries, 1 link, 1 quote")
        # should not mention notes since none were created.
        soup = response.content.decode()
        summary_match = re.search(r"(\d+ posts?:.*?)</p>", soup, re.DOTALL)
        self.assertIsNotNone(summary_match)
        self.assertNotIn("note", summary_match.group(1))

    def test_archive_month_includes_notes(self):
        created = datetime.datetime(2025, 7, 1, tzinfo=datetime.timezone.utc)
        # Add an entry outside July 2025 so the calendar works
        EntryFactory(
            created=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        )
        NoteFactory(created=created)
        QuotationFactory(created=created)
        BlogmarkFactory(created=created)
        response = self.client.get("/2025/Jul/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "3 posts:")
        self.assertContains(response, ">1 note</a>")
        self.assertContains(
            response,
            "/search/?type=note&year=2025&month=7",
        )

    def test_archive_day_navigation_links(self):
        """Day archive page shows previous/next day navigation links."""
        EntryFactory(
            created=datetime.datetime(2024, 12, 20, 12, 0, tzinfo=datetime.timezone.utc)
        )
        EntryFactory(
            created=datetime.datetime(2024, 12, 22, 12, 0, tzinfo=datetime.timezone.utc)
        )
        EntryFactory(
            created=datetime.datetime(2024, 12, 25, 12, 0, tzinfo=datetime.timezone.utc)
        )

        # Middle day: should have both previous and next
        response = self.client.get("/2024/Dec/22/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/2024/Dec/20/")
        self.assertContains(response, "Friday, 20th December 2024")
        self.assertContains(response, "/2024/Dec/25/")
        self.assertContains(response, "Wednesday, 25th December 2024")

        # First day: should have next but no previous
        response = self.client.get("/2024/Dec/20/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/2024/Dec/22/")
        self.assertNotContains(response, "&larr;")

        # Last day: should have previous but no next
        response = self.client.get("/2024/Dec/25/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/2024/Dec/22/")
        self.assertNotContains(response, "&rarr;")

    def test_archive_day_navigation_across_months(self):
        """Day navigation works across month boundaries."""
        EntryFactory(
            created=datetime.datetime(2024, 11, 30, 12, 0, tzinfo=datetime.timezone.utc)
        )
        EntryFactory(
            created=datetime.datetime(2024, 12, 1, 12, 0, tzinfo=datetime.timezone.utc)
        )

        response = self.client.get("/2024/Dec/1/")
        self.assertContains(response, "/2024/Nov/30/")
        self.assertContains(response, "Saturday, 30th November 2024")

    def test_archive_day_navigation_skips_draft_only_days(self):
        """Navigation should skip days that only have draft content."""
        EntryFactory(
            created=datetime.datetime(2024, 12, 20, 12, 0, tzinfo=datetime.timezone.utc)
        )
        EntryFactory(
            created=datetime.datetime(
                2024, 12, 21, 12, 0, tzinfo=datetime.timezone.utc
            ),
            is_draft=True,
        )
        EntryFactory(
            created=datetime.datetime(2024, 12, 22, 12, 0, tzinfo=datetime.timezone.utc)
        )

        response = self.client.get("/2024/Dec/22/")
        self.assertContains(response, "/2024/Dec/20/")
        self.assertNotContains(response, "/2024/Dec/21/")

    def test_archive_day_navigation_across_model_types(self):
        """Navigation finds adjacent days across different content types."""
        BlogmarkFactory(
            created=datetime.datetime(2024, 12, 18, 12, 0, tzinfo=datetime.timezone.utc)
        )
        EntryFactory(
            created=datetime.datetime(2024, 12, 22, 12, 0, tzinfo=datetime.timezone.utc)
        )
        NoteFactory(
            created=datetime.datetime(2024, 12, 28, 12, 0, tzinfo=datetime.timezone.utc)
        )

        response = self.client.get("/2024/Dec/22/")
        self.assertContains(response, "/2024/Dec/18/")
        self.assertContains(response, "/2024/Dec/28/")


class TypeListingTests(TransactionTestCase):
    def test_entries_page(self):
        entry = EntryFactory()
        BlogmarkFactory()
        response = self.client.get("/entries/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Entries")
        self.assertEqual(response.context["selected"]["type"], "entry")
        self.assertTrue(response.context["fixed_type"])

    def test_blogmarks_page(self):
        BlogmarkFactory()
        EntryFactory()
        response = self.client.get("/blogmarks/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blogmarks")
        self.assertEqual(response.context["selected"]["type"], "blogmark")

    def test_quotations_page(self):
        QuotationFactory()
        response = self.client.get("/quotations/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Quotations")
        self.assertEqual(response.context["selected"]["type"], "quotation")

    def test_notes_page(self):
        NoteFactory()
        response = self.client.get("/notes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notes")
        self.assertEqual(response.context["selected"]["type"], "note")

    def test_pagination(self):
        for _ in range(35):
            EntryFactory()
        response = self.client.get("/entries/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["results"]), 30)
        response2 = self.client.get("/entries/?page=2")
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(len(response2.context["results"]), 5)

    def test_search_within_type(self):
        EntryFactory(title="Unique findable title")
        EntryFactory(title="Other entry")
        response = self.client.get("/entries/?q=findable")
        self.assertEqual(response.status_code, 200)

    def test_tag_filtering(self):
        tag = Tag.objects.create(tag="test-listing")
        entry = EntryFactory()
        entry.tags.add(tag)
        EntryFactory()  # no tag
        response = self.client.get("/entries/?tag=test-listing")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 1)

    def test_type_facet_hidden(self):
        EntryFactory()
        response = self.client.get("/entries/")
        self.assertNotContains(response, 'id="facet-types"')

    def test_type_pill_hidden(self):
        EntryFactory()
        response = self.client.get("/entries/")
        self.assertNotContains(response, "Type: entry")

    def test_pagination_no_type_in_query_string(self):
        for _ in range(35):
            EntryFactory()
        response = self.client.get("/entries/")
        self.assertContains(response, "?page=2")
        # Pagination links should not include type=entry
        self.assertNotContains(response, "?type=entry&amp;page=")
        self.assertNotContains(response, "?page=2&amp;type=entry")

    def test_form_action_points_to_search(self):
        EntryFactory()
        response = self.client.get("/entries/")
        self.assertContains(response, 'action="/search/"')

    def test_year_facet_links_to_search(self):
        EntryFactory()
        response = self.client.get("/entries/")
        content = response.content.decode()
        # Year facet links should go to /search/ with type=entry
        self.assertIn("/search/?", content)
        self.assertIn("type=entry", content)

    def test_entries_page_has_feed_icon(self):
        EntryFactory()
        response = self.client.get("/entries/")
        self.assertContains(response, "/atom/entries/")
        self.assertContains(response, "Atom feed")

    def test_blogmarks_page_has_feed_icon(self):
        BlogmarkFactory()
        response = self.client.get("/blogmarks/")
        self.assertContains(response, "/atom/links/")
        self.assertContains(response, "Atom feed")

    def test_quotations_page_has_feed_icon(self):
        QuotationFactory()
        response = self.client.get("/quotations/")
        self.assertContains(response, "/atom/quotations/")
        self.assertContains(response, "Atom feed")

    def test_notes_page_has_feed_icon(self):
        NoteFactory()
        response = self.client.get("/notes/")
        self.assertContains(response, "/atom/notes/")
        self.assertContains(response, "Atom feed")


class MergeTagsTests(TransactionTestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff", password="password", is_staff=True
        )
        self.regular_user = User.objects.create_user(
            username="regular", password="password", is_staff=False
        )

    def test_merge_tags_requires_staff(self):
        """Non-staff users should be redirected to login."""
        response = self.client.get("/admin/merge-tags/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

        self.client.login(username="regular", password="password")
        response = self.client.get("/admin/merge-tags/")
        self.assertEqual(response.status_code, 302)

    def test_merge_tags_page_loads_for_staff(self):
        """Staff users can access the merge tags page."""
        self.client.login(username="staff", password="password")
        response = self.client.get("/admin/merge-tags/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merge Tags")

    def test_merge_tags_shows_confirmation(self):
        """Selecting two tags shows a confirmation screen with counts."""
        source_tag = Tag.objects.create(tag="source-tag")
        dest_tag = Tag.objects.create(tag="dest-tag")

        entry = EntryFactory()
        entry.tags.add(source_tag)
        blogmark = BlogmarkFactory()
        blogmark.tags.add(source_tag)

        self.client.login(username="staff", password="password")
        response = self.client.get(
            "/admin/merge-tags/?source=source-tag&destination=dest-tag"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm Tag Merge")
        self.assertContains(response, "source-tag")
        self.assertContains(response, "dest-tag")

    def test_merge_tags_performs_merge(self):
        """Merging tags re-tags content and deletes the source tag."""
        source_tag = Tag.objects.create(tag="old-tag")
        dest_tag = Tag.objects.create(tag="new-tag")

        entry = EntryFactory()
        entry.tags.add(source_tag)
        blogmark = BlogmarkFactory()
        blogmark.tags.add(source_tag)
        quotation = QuotationFactory()
        quotation.tags.add(source_tag)
        note = NoteFactory()
        note.tags.add(source_tag)

        self.client.login(username="staff", password="password")
        response = self.client.post(
            "/admin/merge-tags/",
            {"source": "old-tag", "destination": "new-tag", "confirm": "yes"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Successfully merged")

        # Verify source tag was deleted
        self.assertFalse(Tag.objects.filter(tag="old-tag").exists())

        # Verify content is now tagged with destination tag
        entry.refresh_from_db()
        blogmark.refresh_from_db()
        quotation.refresh_from_db()
        note.refresh_from_db()

        self.assertIn(dest_tag, entry.tags.all())
        self.assertIn(dest_tag, blogmark.tags.all())
        self.assertIn(dest_tag, quotation.tags.all())
        self.assertIn(dest_tag, note.tags.all())

        self.assertNotIn(source_tag, entry.tags.all())

    def test_merge_creates_previous_tag_name(self):
        """Merging tags creates a PreviousTagName for redirects."""
        source_tag = Tag.objects.create(tag="redirect-from")
        dest_tag = Tag.objects.create(tag="redirect-to")

        entry = EntryFactory()
        entry.tags.add(source_tag)

        self.client.login(username="staff", password="password")
        self.client.post(
            "/admin/merge-tags/",
            {"source": "redirect-from", "destination": "redirect-to", "confirm": "yes"},
        )

        # Verify PreviousTagName was created
        previous = PreviousTagName.objects.get(previous_name="redirect-from")
        self.assertEqual(previous.tag.tag, "redirect-to")

        # Verify redirect works (redirects to /tag/ which then redirects to /tags/)
        response = self.client.get("/tags/redirect-from/")
        self.assertEqual(response.status_code, 301)
        self.assertIn("redirect-to", response.url)

    def test_merge_creates_tag_merge_record(self):
        """Merging tags creates a TagMerge record with details."""
        source_tag = Tag.objects.create(tag="merge-source")
        dest_tag = Tag.objects.create(tag="merge-dest")

        entry = EntryFactory()
        entry.tags.add(source_tag)
        blogmark = BlogmarkFactory()
        blogmark.tags.add(source_tag)

        self.client.login(username="staff", password="password")
        self.client.post(
            "/admin/merge-tags/",
            {"source": "merge-source", "destination": "merge-dest", "confirm": "yes"},
        )

        # Verify TagMerge record was created
        merge_record = TagMerge.objects.get(source_tag_name="merge-source")
        self.assertEqual(merge_record.destination_tag_name, "merge-dest")
        self.assertEqual(merge_record.destination_tag, dest_tag)
        self.assertIn(entry.pk, merge_record.details["entries"]["added"])
        self.assertIn(blogmark.pk, merge_record.details["blogmarks"]["added"])

    def test_merge_handles_items_already_tagged(self):
        """Items that already have the destination tag are tracked separately."""
        source_tag = Tag.objects.create(tag="old-tag")
        dest_tag = Tag.objects.create(tag="new-tag")

        # Entry has only source tag - will get destination added
        entry_needs_tag = EntryFactory()
        entry_needs_tag.tags.add(source_tag)

        # Blogmark has both tags - destination won't be added
        blogmark_has_both = BlogmarkFactory()
        blogmark_has_both.tags.add(source_tag)
        blogmark_has_both.tags.add(dest_tag)

        self.client.login(username="staff", password="password")
        response = self.client.post(
            "/admin/merge-tags/",
            {"source": "old-tag", "destination": "new-tag", "confirm": "yes"},
        )
        self.assertEqual(response.status_code, 200)

        # Verify the success message differentiates
        self.assertContains(response, "Added &#x27;new-tag&#x27; tag to 1 item(s)")
        self.assertContains(
            response, "Removed &#x27;old-tag&#x27; from 1 item(s) that already had"
        )

        # Verify TagMerge record has correct structure
        merge_record = TagMerge.objects.get(source_tag_name="old-tag")
        self.assertIn(entry_needs_tag.pk, merge_record.details["entries"]["added"])
        self.assertIn(
            blogmark_has_both.pk, merge_record.details["blogmarks"]["already_tagged"]
        )

        # Verify both items now have only dest_tag
        entry_needs_tag.refresh_from_db()
        blogmark_has_both.refresh_from_db()
        self.assertIn(dest_tag, entry_needs_tag.tags.all())
        self.assertIn(dest_tag, blogmark_has_both.tags.all())
        self.assertFalse(Tag.objects.filter(tag="old-tag").exists())

    def test_merge_same_tag_error(self):
        """Merging a tag into itself should show an error."""
        tag = Tag.objects.create(tag="same-tag")

        self.client.login(username="staff", password="password")
        response = self.client.get(
            "/admin/merge-tags/?source=same-tag&destination=same-tag"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Source and destination tags must be different")

    def test_merge_nonexistent_tag_error(self):
        """Merging with a nonexistent tag should show an error."""
        Tag.objects.create(tag="existing-tag")

        self.client.login(username="staff", password="password")
        response = self.client.get(
            "/admin/merge-tags/?source=nonexistent&destination=existing-tag"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Source tag &#x27;nonexistent&#x27; not found")

    def test_tag_merge_admin_change_page(self):
        """The TagMerge admin change page should load without errors."""
        # Create a superuser for admin access
        superuser = User.objects.create_superuser(
            username="admin", password="adminpass", email="admin@example.com"
        )

        # Create a TagMerge record directly
        dest_tag = Tag.objects.create(tag="dest-tag")
        merge_record = TagMerge.objects.create(
            source_tag_name="source-tag",
            destination_tag=dest_tag,
            destination_tag_name="dest-tag",
            details={
                "entries": {"added": [1, 2], "already_tagged": []},
                "blogmarks": {"added": [], "already_tagged": [3]},
            },
        )

        self.client.login(username="admin", password="adminpass")
        response = self.client.get(f"/admin/blog/tagmerge/{merge_record.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "source-tag")
        self.assertContains(response, "dest-tag")


class TagThroughModelStrTests(TransactionTestCase):
    """Tests for the monkey-patched __str__ methods on tag through models."""

    def test_entry_tag_through_str(self):
        """Entry tag through model __str__ includes title and admin link."""
        from blog.models import Entry

        tag = Tag.objects.create(tag="test-tag")
        entry = EntryFactory(title="My Test Entry Title")
        entry.tags.add(tag)

        through_obj = Entry.tags.through.objects.get(entry=entry, tag=tag)
        str_repr = str(through_obj)

        self.assertIn("Entry:", str_repr)
        self.assertIn("My Test Entry Title", str_repr)
        self.assertIn(f"/admin/blog/entry/{entry.pk}/change/", str_repr)
        self.assertIn("<a href=", str_repr)

    def test_blogmark_tag_through_str(self):
        """Blogmark tag through model __str__ includes link_title and admin link."""
        from blog.models import Blogmark

        tag = Tag.objects.create(tag="test-tag")
        blogmark = BlogmarkFactory(link_title="Interesting Article")
        blogmark.tags.add(tag)

        through_obj = Blogmark.tags.through.objects.get(blogmark=blogmark, tag=tag)
        str_repr = str(through_obj)

        self.assertIn("Blogmark:", str_repr)
        self.assertIn("Interesting Article", str_repr)
        self.assertIn(f"/admin/blog/blogmark/{blogmark.pk}/change/", str_repr)

    def test_quotation_tag_through_str(self):
        """Quotation tag through model __str__ includes source and admin link."""
        from blog.models import Quotation

        tag = Tag.objects.create(tag="test-tag")
        quotation = QuotationFactory(source="Famous Person")
        quotation.tags.add(tag)

        through_obj = Quotation.tags.through.objects.get(quotation=quotation, tag=tag)
        str_repr = str(through_obj)

        self.assertIn("Quotation:", str_repr)
        self.assertIn("Famous Person", str_repr)
        self.assertIn(f"/admin/blog/quotation/{quotation.pk}/change/", str_repr)

    def test_note_tag_through_str(self):
        """Note tag through model __str__ includes truncated body and admin link."""
        from blog.models import Note

        tag = Tag.objects.create(tag="test-tag")
        note = NoteFactory(body="This is a short note")
        note.tags.add(tag)

        through_obj = Note.tags.through.objects.get(note=note, tag=tag)
        str_repr = str(through_obj)

        self.assertIn("Note:", str_repr)
        self.assertIn("This is a short note", str_repr)
        self.assertIn(f"/admin/blog/note/{note.pk}/change/", str_repr)

    def test_note_tag_through_str_truncates_long_body(self):
        """Note tag through model __str__ truncates long body to 50 chars."""
        from blog.models import Note

        tag = Tag.objects.create(tag="test-tag")
        long_body = "A" * 100  # 100 character body
        note = NoteFactory(body=long_body)
        note.tags.add(tag)

        through_obj = Note.tags.through.objects.get(note=note, tag=tag)
        str_repr = str(through_obj)

        # Should have first 50 chars + "..."
        self.assertIn("A" * 50 + "...", str_repr)
        # Should not have the full 100 chars
        self.assertNotIn("A" * 100, str_repr)


class TagAdminDeleteTests(TransactionTestCase):
    """Tests for the tag admin delete confirmation page."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin", password="adminpass", email="admin@example.com"
        )
        self.client.login(username="admin", password="adminpass")

    def test_tag_delete_confirmation_shows_entry_titles(self):
        """Tag delete confirmation page shows entry titles with admin links."""
        tag = Tag.objects.create(tag="delete-me")
        entry = EntryFactory(title="Entry To Be Affected")
        entry.tags.add(tag)

        response = self.client.get(f"/admin/blog/tag/{tag.pk}/delete/")
        self.assertEqual(response.status_code, 200)

        # Should show the entry title, not just "Entry_tags object (123)"
        self.assertContains(response, "Entry To Be Affected")
        self.assertContains(response, f"/admin/blog/entry/{entry.pk}/change/")

    def test_tag_delete_confirmation_shows_blogmark_titles(self):
        """Tag delete confirmation page shows blogmark titles with admin links."""
        tag = Tag.objects.create(tag="delete-me")
        blogmark = BlogmarkFactory(link_title="Blogmark Link Title")
        blogmark.tags.add(tag)

        response = self.client.get(f"/admin/blog/tag/{tag.pk}/delete/")
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Blogmark Link Title")
        self.assertContains(response, f"/admin/blog/blogmark/{blogmark.pk}/change/")

    def test_tag_delete_confirmation_shows_quotation_sources(self):
        """Tag delete confirmation page shows quotation sources with admin links."""
        tag = Tag.objects.create(tag="delete-me")
        quotation = QuotationFactory(source="Quotation Source Name")
        quotation.tags.add(tag)

        response = self.client.get(f"/admin/blog/tag/{tag.pk}/delete/")
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Quotation Source Name")
        self.assertContains(response, f"/admin/blog/quotation/{quotation.pk}/change/")

    def test_tag_delete_confirmation_shows_note_body(self):
        """Tag delete confirmation page shows note body with admin links."""
        tag = Tag.objects.create(tag="delete-me")
        note = NoteFactory(body="Note body content here")
        note.tags.add(tag)

        response = self.client.get(f"/admin/blog/tag/{tag.pk}/delete/")
        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Note body content here")
        self.assertContains(response, f"/admin/blog/note/{note.pk}/change/")

    def test_tag_delete_confirmation_shows_multiple_content_types(self):
        """Tag delete confirmation shows all content types with proper titles."""
        tag = Tag.objects.create(tag="multi-content-tag")

        entry = EntryFactory(title="Test Entry")
        blogmark = BlogmarkFactory(link_title="Test Blogmark")
        quotation = QuotationFactory(source="Test Quotation")
        note = NoteFactory(body="Test Note")

        entry.tags.add(tag)
        blogmark.tags.add(tag)
        quotation.tags.add(tag)
        note.tags.add(tag)

        response = self.client.get(f"/admin/blog/tag/{tag.pk}/delete/")
        self.assertEqual(response.status_code, 200)

        # All content should be shown with meaningful titles
        self.assertContains(response, "Test Entry")
        self.assertContains(response, "Test Blogmark")
        self.assertContains(response, "Test Quotation")
        self.assertContains(response, "Test Note")

        # All admin links should be present
        self.assertContains(response, f"/admin/blog/entry/{entry.pk}/change/")
        self.assertContains(response, f"/admin/blog/blogmark/{blogmark.pk}/change/")
        self.assertContains(response, f"/admin/blog/quotation/{quotation.pk}/change/")
        self.assertContains(response, f"/admin/blog/note/{note.pk}/change/")


class RandomTagRedirectTests(TransactionTestCase):
    """Tests for the /random/TAG/ endpoint."""

    def test_random_tag_redirect_returns_all_types(self):
        """
        Test that /random/TAG/ can return all four content types.
        Creates one of each type with the same tag and loops until
        all four types have been returned, or fails after 1000 tries.
        """
        tag = Tag.objects.create(tag="random-test-tag")

        entry = EntryFactory(title="Random Test Entry")
        entry.tags.add(tag)

        blogmark = BlogmarkFactory(link_title="Random Test Blogmark")
        blogmark.tags.add(tag)

        quotation = QuotationFactory(source="Random Test Quotation")
        quotation.tags.add(tag)

        note = NoteFactory(body="Random Test Note")
        note.tags.add(tag)

        # Track which content types we've seen
        seen_types = set()
        expected_urls = {
            entry.get_absolute_url(): "entry",
            blogmark.get_absolute_url(): "blogmark",
            quotation.get_absolute_url(): "quotation",
            note.get_absolute_url(): "note",
        }

        max_iterations = 1000
        for i in range(max_iterations):
            response = self.client.get("/random/random-test-tag/")
            self.assertEqual(response.status_code, 302)

            # Get the redirect URL
            redirect_url = response.url

            # Figure out which type this is
            if redirect_url in expected_urls:
                seen_types.add(expected_urls[redirect_url])

            # Check if we've seen all types
            if len(seen_types) == 4:
                break
        else:
            self.fail(
                f"Did not see all 4 content types after {max_iterations} iterations. "
                f"Only saw: {seen_types}"
            )

    def test_random_tag_redirect_has_no_cache_headers(self):
        """Test that /random/TAG/ returns no-cache headers."""
        tag = Tag.objects.create(tag="cache-test-tag")
        entry = EntryFactory()
        entry.tags.add(tag)

        response = self.client.get("/random/cache-test-tag/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.headers["Cache-Control"],
            "private, no-cache, no-store, must-revalidate",
        )
        self.assertEqual(response.headers["Pragma"], "no-cache")
        self.assertEqual(response.headers["Expires"], "0")

    def test_random_tag_redirect_404_for_nonexistent_tag(self):
        """Test that /random/TAG/ returns 404 for nonexistent tag."""
        response = self.client.get("/random/nonexistent-tag/")
        self.assertEqual(response.status_code, 404)

    def test_random_tag_redirect_404_for_empty_tag(self):
        """Test that /random/TAG/ returns 404 for tag with no items."""
        tag = Tag.objects.create(tag="empty-tag")
        response = self.client.get("/random/empty-tag/")
        self.assertEqual(response.status_code, 404)

    def test_random_tag_redirect_excludes_drafts(self):
        """Test that /random/TAG/ excludes draft items."""
        tag = Tag.objects.create(tag="draft-test-tag")

        # Create draft items only
        draft_entry = EntryFactory(is_draft=True)
        draft_entry.tags.add(tag)

        # Should get 404 since only draft items exist
        response = self.client.get("/random/draft-test-tag/")
        self.assertEqual(response.status_code, 404)

        # Now add a published item
        published_entry = EntryFactory(is_draft=False)
        published_entry.tags.add(tag)

        # Should redirect to the published item
        response = self.client.get("/random/draft-test-tag/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, published_entry.get_absolute_url())


class BulkTagIdFilterTests(TransactionTestCase):
    """Tests for filtering search/bulk-tag results by specific IDs."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff", password="password", is_staff=True
        )
        self.client.login(username="staff", password="password")

        # Create test data
        self.entry1 = EntryFactory(title="Entry One")
        self.entry2 = EntryFactory(title="Entry Two")
        self.entry3 = EntryFactory(title="Entry Three")

        self.note1 = NoteFactory(body="Note One")
        self.note2 = NoteFactory(body="Note Two")

        self.quotation1 = QuotationFactory(source="Quotation One")
        self.quotation2 = QuotationFactory(source="Quotation Two")

        self.blogmark1 = BlogmarkFactory(link_title="Blogmark One")
        self.blogmark2 = BlogmarkFactory(link_title="Blogmark Two")

    def test_filter_entries_by_id(self):
        """Filtering by entries= should only show those entries."""
        ids = f"{self.entry1.pk},{self.entry3.pk}"
        response = self.client.get(f"/admin/bulk-tag/?entries={ids}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)
        result_types = {r["type"] for r in response.context["results"]}
        self.assertEqual(result_types, {"entry"})
        result_pks = {r["obj"].pk for r in response.context["results"]}
        self.assertIn(self.entry1.pk, result_pks)
        self.assertIn(self.entry3.pk, result_pks)
        self.assertNotIn(self.entry2.pk, result_pks)

    def test_filter_notes_by_id(self):
        """Filtering by notes= should only show those notes."""
        ids = f"{self.note1.pk}"
        response = self.client.get(f"/admin/bulk-tag/?notes={ids}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 1)
        result_pks = {r["obj"].pk for r in response.context["results"]}
        self.assertIn(self.note1.pk, result_pks)
        self.assertNotIn(self.note2.pk, result_pks)

    def test_filter_multiple_types_by_id(self):
        """Filtering by entries= and notes= should show both types."""
        response = self.client.get(
            f"/admin/bulk-tag/?entries={self.entry1.pk}&notes={self.note2.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)
        result_types = {r["type"] for r in response.context["results"]}
        self.assertEqual(result_types, {"entry", "note"})

    def test_filter_all_four_types_by_id(self):
        """Filtering by all four type params should show all specified items."""
        response = self.client.get(
            f"/admin/bulk-tag/?entries={self.entry1.pk}"
            f"&notes={self.note1.pk}"
            f"&quotations={self.quotation1.pk}"
            f"&blogmarks={self.blogmark1.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 4)
        result_types = {r["type"] for r in response.context["results"]}
        self.assertEqual(result_types, {"entry", "note", "quotation", "blogmark"})

    def test_id_filter_combined_with_search_query(self):
        """ID filters combined with q= should search within filtered items."""
        entry_a = EntryFactory(title="Unique findable alpha term")
        entry_b = EntryFactory(title="Something else entirely")
        response = self.client.get(
            f"/admin/bulk-tag/?entries={entry_a.pk},{entry_b.pk}&q=alpha"
        )
        self.assertEqual(response.status_code, 200)
        # Only entry_a should match because q=alpha filters within the ID set
        self.assertEqual(response.context["total"], 1)
        self.assertEqual(response.context["results"][0]["obj"].pk, entry_a.pk)

    def test_id_filter_shows_filter_message(self):
        """When filtering by IDs, a message should appear indicating active filters."""
        response = self.client.get(
            f"/admin/bulk-tag/?entries={self.entry1.pk}&notes={self.note1.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtered to specific entries, notes")

    def test_id_filter_message_shows_only_active_types(self):
        """Filter message should only list the types being filtered."""
        response = self.client.get(f"/admin/bulk-tag/?entries={self.entry1.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Filtered to specific entries")
        self.assertNotContains(response, "notes")
        self.assertNotContains(response, "quotations")
        self.assertNotContains(response, "blogmarks")

    def test_id_filter_message_has_clear_link(self):
        """Filter message should include a way to clear the filter."""
        response = self.client.get(f"/admin/bulk-tag/?entries={self.entry1.pk}")
        self.assertEqual(response.status_code, 200)
        # Should contain × (cross icon) to clear filters
        self.assertContains(response, "&#x00D7;")

    def test_id_filter_works_on_search_page(self):
        """ID filtering should also work on /search/."""
        response = self.client.get(
            f"/search/?entries={self.entry1.pk},{self.entry2.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)
        result_pks = {r["obj"].pk for r in response.context["results"]}
        self.assertIn(self.entry1.pk, result_pks)
        self.assertIn(self.entry2.pk, result_pks)
        self.assertNotIn(self.entry3.pk, result_pks)

    def test_id_filter_excludes_unspecified_types(self):
        """When ID filters are active, types not mentioned should be excluded."""
        response = self.client.get(f"/admin/bulk-tag/?entries={self.entry1.pk}")
        self.assertEqual(response.status_code, 200)
        # Should only have entry results, no notes/blogmarks/quotations
        result_types = {r["type"] for r in response.context["results"]}
        self.assertEqual(result_types, {"entry"})

    def test_id_filter_invalid_ids_ignored(self):
        """Invalid (non-numeric) IDs should be ignored."""
        response = self.client.get(
            f"/admin/bulk-tag/?entries={self.entry1.pk},abc,999999"
        )
        self.assertEqual(response.status_code, 200)
        # Only the valid existing entry should be found
        self.assertEqual(response.context["total"], 1)

    def test_id_filter_preserves_hidden_fields_in_form(self):
        """ID filter params should be preserved as hidden form fields."""
        response = self.client.get(
            f"/admin/bulk-tag/?entries={self.entry1.pk},{self.entry2.pk}&notes={self.note1.pk}"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(
            f'name="entries" value="{self.entry1.pk},{self.entry2.pk}"', content
        )
        self.assertIn(f'name="notes" value="{self.note1.pk}"', content)


class BeatTests(TransactionTestCase):
    def test_beat_on_homepage(self):
        """Beat should appear on the homepage in the mixed timeline."""
        beat = BeatFactory(title="llm-anthropic 0.24", beat_type="release")
        response = self.client.get("/")
        self.assertContains(response, "llm-anthropic 0.24")

    def test_beat_on_homepage_with_beat_label(self):
        """Beat should render with the correct beat-label CSS class."""
        beat = BeatFactory(title="Test Release Beat", beat_type="release")
        response = self.client.get("/")
        self.assertContains(response, 'class="beat-label release"')
        self.assertContains(response, "Release")

    def test_beat_til_update_label(self):
        """TIL update beat should render with compound badge."""
        beat = BeatFactory(
            title="Using the LLM Python API",
            beat_type="til_update",
            commentary="Added async streaming",
        )
        response = self.client.get("/")
        self.assertContains(response, 'class="beat-label til-update"')
        self.assertContains(response, "til-update-suffix")
        self.assertContains(response, "Added async streaming")

    def test_beat_commentary_optional(self):
        """Beat without commentary should not render beat-commit span."""
        beat = BeatFactory(title="Test Release", beat_type="release", commentary="")
        response = self.client.get("/")
        self.assertContains(response, "Test Release")
        self.assertNotContains(response, "beat-commit")

    def test_beat_commentary_shown(self):
        """Beat with commentary should render beat-commit span."""
        beat = BeatFactory(
            title="Some TIL",
            beat_type="til_update",
            commentary="Updated section on async",
        )
        response = self.client.get("/")
        self.assertContains(response, "beat-commit")
        self.assertContains(response, "Updated section on async")

    def test_beat_on_archive_month(self):
        """Beat should appear on month archive pages."""
        EntryFactory(
            created=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        )
        beat = BeatFactory(
            title="Archive Beat",
            beat_type="tool",
            created=datetime.datetime(2025, 7, 15, tzinfo=datetime.timezone.utc),
        )
        response = self.client.get("/2025/Jul/")
        self.assertContains(response, "Archive Beat")

    def test_beat_on_archive_day(self):
        """Beat should appear on day archive pages."""
        EntryFactory(
            created=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        )
        beat = BeatFactory(
            title="Day Beat",
            beat_type="research",
            created=datetime.datetime(2025, 7, 15, tzinfo=datetime.timezone.utc),
        )
        response = self.client.get("/2025/Jul/15/")
        self.assertContains(response, "Day Beat")

    def test_beat_on_tag_page(self):
        """Beat should appear on tag pages."""
        tag = Tag.objects.create(tag="cloudflare")
        beat = BeatFactory(title="Tagged Beat", beat_type="til")
        beat.tags.add(tag)
        response = self.client.get("/tags/cloudflare/")
        self.assertContains(response, "Tagged Beat")

    def test_beat_in_search(self):
        """Beat should appear in search results."""
        beat = BeatFactory(title="Searchable Beat Title", beat_type="release")
        response = self.client.get("/search/?type=beat")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Searchable Beat Title")

    def test_beat_detail_page(self):
        """Beat should have its own detail page at the standard URL pattern."""
        EntryFactory()  # Needed for calendar widget
        beat = BeatFactory(title="Detail Beat", beat_type="release")
        response = self.client.get(beat.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detail Beat")

    def test_beat_draft_not_on_homepage(self):
        """Draft beats should not appear on the homepage."""
        beat = BeatFactory(title="draftbeat", beat_type="release", is_draft=True)
        response = self.client.get("/")
        self.assertNotContains(response, "draftbeat")

    def test_beat_draft_detail_page_has_warning(self):
        """Draft beats should show a draft warning on their detail page."""
        EntryFactory()  # Needed for calendar widget
        beat = BeatFactory(
            title="Draft Beat Detail", beat_type="release", is_draft=True
        )
        response = self.client.get(beat.get_absolute_url())
        self.assertContains(response, "This is a draft post")

    def test_beat_excluded_from_everything_feed(self):
        """Beat should not appear in the everything Atom feed."""
        beat = BeatFactory(title="Feed Beat Title", beat_type="release")
        response = self.client.get("/atom/everything/")
        self.assertNotContains(response, "Feed Beat Title")

    def test_beat_redirect_by_id(self):
        """Beat should have a /beat/{id} redirect URL."""
        beat = BeatFactory(title="Redirect Beat", beat_type="release")
        response = self.client.get(f"/beat/{beat.pk}")
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, beat.get_absolute_url())

    def test_beats_listing_page(self):
        """Beats should have an /elsewhere/ listing page."""
        beat = BeatFactory(title="Listed Beat", beat_type="release")
        response = self.client.get("/elsewhere/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listed Beat")

    def test_beat_css_loaded(self):
        """Beat CSS classes should be in the stylesheet."""
        beat = BeatFactory(title="CSS Beat", beat_type="release")
        response = self.client.get("/")
        self.assertContains(response, "beat-label")

    def test_beat_all_types_render(self):
        """All beat types should render with their correct label."""
        for beat_type, display in [
            ("release", "Release"),
            ("til", "TIL"),
            ("research", "Research"),
            ("tool", "Tool"),
        ]:
            beat = BeatFactory(title=f"Type {beat_type}", beat_type=beat_type)
        response = self.client.get("/")
        self.assertContains(response, 'class="beat-label release"')
        self.assertContains(response, 'class="beat-label til"')
        self.assertContains(response, 'class="beat-label research"')
        self.assertContains(response, 'class="beat-label tool"')

    def test_beat_in_archive_month_type_counts(self):
        """Beat should appear in archive month type counts."""
        EntryFactory(
            created=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc)
        )
        created = datetime.datetime(2025, 7, 1, tzinfo=datetime.timezone.utc)
        BeatFactory(created=created, beat_type="release")
        EntryFactory(created=created)
        response = self.client.get("/2025/Jul/")
        self.assertContains(response, "beat")


class BeatTypeFacetTests(TransactionTestCase):
    """Tests for surfacing beat types (release, til, etc.) directly in the Type facet."""

    def test_type_counts_include_beat_subtypes(self):
        """Type facet should include beat:release, beat:til etc. instead of just 'beat'."""
        EntryFactory(title="An entry")
        BeatFactory(title="Release beat", beat_type="release")
        BeatFactory(title="TIL beat", beat_type="til")
        BeatFactory(title="Another release", beat_type="release")
        response = self.client.get("/search/?q=")
        type_counts = response.context["type_counts"]
        type_names = [t["type"] for t in type_counts]
        # Should have beat:release and beat:til, not plain "beat"
        self.assertIn("beat:release", type_names)
        self.assertIn("beat:til", type_names)
        self.assertNotIn("beat", type_names)

    def test_type_counts_beat_subtype_counts_correct(self):
        """Each beat subtype should have the correct count."""
        BeatFactory(title="Release 1", beat_type="release")
        BeatFactory(title="Release 2", beat_type="release")
        BeatFactory(title="TIL 1", beat_type="til")
        response = self.client.get("/search/?q=")
        type_counts = response.context["type_counts"]
        counts_by_type = {t["type"]: t["n"] for t in type_counts}
        self.assertEqual(counts_by_type["beat:release"], 2)
        self.assertEqual(counts_by_type["beat:til"], 1)

    def test_filter_by_beat_subtype(self):
        """?type=beat:release should show only release beats."""
        BeatFactory(title="Release beat", beat_type="release")
        BeatFactory(title="TIL beat", beat_type="til")
        EntryFactory(title="An entry")
        response = self.client.get("/search/?type=beat:release")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Release beat")
        self.assertNotContains(response, "TIL beat")
        self.assertNotContains(response, "An entry")

    def test_filter_by_beat_subtype_til(self):
        """?type=beat:til should show only TIL beats."""
        BeatFactory(title="Release beat", beat_type="release")
        BeatFactory(title="TIL beat", beat_type="til")
        response = self.client.get("/search/?type=beat:til")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TIL beat")
        self.assertNotContains(response, "Release beat")

    def test_type_facet_shows_beat_subtype_labels(self):
        """The type facet in the template should show human-readable labels for beat subtypes."""
        BeatFactory(title="A release", beat_type="release")
        BeatFactory(title="A TIL", beat_type="til")
        response = self.client.get("/search/?q=")
        # The template should display human-readable labels, not raw beat:* keys
        self.assertContains(response, ">Release</a>")
        self.assertContains(response, ">TIL</a>")

    def test_selected_type_pill_shows_beat_subtype(self):
        """When filtering by beat:release, the selected filter pill should show the human-readable label."""
        BeatFactory(title="A release", beat_type="release")
        response = self.client.get("/search/?type=beat:release")
        self.assertContains(response, "Type: Release")

    def test_plain_type_beat_still_works(self):
        """?type=beat should still show all beats regardless of subtype."""
        BeatFactory(title="Release beat", beat_type="release")
        BeatFactory(title="TIL beat", beat_type="til")
        response = self.client.get("/search/?type=beat")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Release beat")
        self.assertContains(response, "TIL beat")

    def test_beat_subtype_with_search_query(self):
        """?type=beat:release&q=searchterm should filter by both."""
        BeatFactory(title="Searchable release", beat_type="release")
        BeatFactory(title="Other release", beat_type="release")
        BeatFactory(title="Searchable til", beat_type="til")
        response = self.client.get("/search/?type=beat:release&q=searchable")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Searchable release")
        self.assertNotContains(response, "Other release")
        self.assertNotContains(response, "Searchable til")

    def test_title_uses_beat_subtype_label(self):
        """The page title should reflect the beat subtype when filtered."""
        BeatFactory(title="A release", beat_type="release")
        response = self.client.get("/search/?type=beat:release")
        self.assertIn("Releases", response.context["title"])

    def test_all_beat_subtypes_in_type_counts(self):
        """All beat subtypes with results should appear in type_counts."""
        for beat_type in ["release", "til", "til_update", "research", "tool"]:
            BeatFactory(beat_type=beat_type)
        response = self.client.get("/search/?q=")
        type_counts = response.context["type_counts"]
        type_names = [t["type"] for t in type_counts]
        for beat_type in ["release", "til", "til_update", "research", "tool"]:
            self.assertIn(f"beat:{beat_type}", type_names)

    def test_beats_listing_page_still_works(self):
        """/elsewhere/ should still show all beats."""
        BeatFactory(title="Release beat", beat_type="release")
        BeatFactory(title="TIL beat", beat_type="til")
        response = self.client.get("/elsewhere/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Release beat")
        self.assertContains(response, "TIL beat")


class ImporterViewTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin", "a@b.com", "password")

    def test_importers_page_requires_login(self):
        response = self.client.get("/admin/importers/")
        assert response.status_code == 302

    def test_importers_page_renders(self):
        self.client.login(username="admin", password="password")
        response = self.client.get("/admin/importers/")
        assert response.status_code == 200
        self.assertContains(response, "Beat Importers")
        self.assertContains(response, "Releases")
        self.assertContains(response, "Research")
        self.assertContains(response, "TILs")
        self.assertContains(response, "Tools")
        self.assertContains(response, "Museums")
        # Source URLs should be shown as links
        self.assertContains(response, "releases_cache.json")
        self.assertContains(response, "tools.json")
        self.assertContains(response, "museums.json")

    def test_api_run_importer_requires_login(self):
        response = self.client.post(
            "/api/run-importer/",
            json.dumps({"importer": "releases"}),
            content_type="application/json",
        )
        assert response.status_code == 302

    def test_api_run_importer_requires_post(self):
        self.client.login(username="admin", password="password")
        response = self.client.get("/api/run-importer/")
        assert response.status_code == 405

    def test_api_run_importer_rejects_unknown(self):
        self.client.login(username="admin", password="password")
        response = self.client.post(
            "/api/run-importer/",
            json.dumps({"importer": "nonexistent"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        data = json.loads(response.content)
        assert data["error"] == "Unknown importer"

    def test_api_run_importer_rejects_invalid_json(self):
        self.client.login(username="admin", password="password")
        response = self.client.post(
            "/api/run-importer/",
            "not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_api_run_importer_releases(self):
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "my-repo": {
                "description": "First release",
                "repo": "my-repo",
                "repo_url": "https://github.com/simonw/my-repo",
                "total_releases": 1,
                "releases": [
                    {
                        "release": "1.0",
                        "published_at": "2025-01-15T10:00:00Z",
                        "published_day": "2025-01-15",
                        "url": "https://github.com/simonw/my-repo/releases/tag/1.0",
                    }
                ],
            }
        }
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "releases"}),
                content_type="application/json",
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["created"] == 1
        assert data["total"] == 1
        assert "my-repo 1.0" in data["items_html"]
        assert 'class="beat-label release"' in data["items_html"]

    def test_api_run_importer_tools(self):
        from unittest.mock import patch, MagicMock

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "filename": "test-tool.html",
                "title": "Test Tool",
                "slug": "test-tool",
                "created": "2025-03-01T12:00:00Z",
                "description": "A test tool",
            }
        ]
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "tools"}),
                content_type="application/json",
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["created"] == 1
        assert "Test Tool" in data["items_html"]

    def test_api_run_importer_shows_max_10_items(self):
        from unittest.mock import patch, MagicMock

        releases = {}
        for i in range(15):
            releases["repo-{}".format(i)] = {
                "description": "",
                "repo": "repo-{}".format(i),
                "repo_url": "https://github.com/simonw/repo-{}".format(i),
                "total_releases": 1,
                "releases": [
                    {
                        "release": "1.0",
                        "published_at": "2025-01-{}T10:00:00Z".format(15 + i),
                        "published_day": "2025-01-{}".format(15 + i),
                        "url": "https://github.com/simonw/repo-{}/releases/tag/1.0".format(
                            i
                        ),
                    }
                ],
            }

        mock_response = MagicMock()
        mock_response.json.return_value = releases
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "releases"}),
                content_type="application/json",
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["created"] == 15
        assert data["total"] == 15
        # items_html should only contain 10 items
        assert data["items_html"].count('class="beat segment"') == 10

    def test_api_run_importer_skips_unchanged(self):
        from unittest.mock import patch, MagicMock

        tool_data = [
            {
                "filename": "test-tool.html",
                "title": "Test Tool",
                "slug": "test-tool",
                "created": "2025-03-01T12:00:00Z",
                "description": "A test tool",
            }
        ]

        mock_response = MagicMock()
        mock_response.json.return_value = tool_data
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")

        # First run: creates the tool
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "tools"}),
                content_type="application/json",
            )
        data = json.loads(response.content)
        assert data["created"] == 1
        assert data["updated"] == 0
        assert data["skipped"] == 0

        # Second run with same data: should skip
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "tools"}),
                content_type="application/json",
            )
        data = json.loads(response.content)
        assert data["created"] == 0
        assert data["updated"] == 0
        assert data["skipped"] == 1
        assert data["total"] == 0  # no items to display

        # Third run with changed data: should update
        tool_data[0]["description"] = "Updated description"
        mock_response2 = MagicMock()
        mock_response2.json.return_value = tool_data
        mock_response2.raise_for_status = MagicMock()
        with patch("blog.importers.httpx.get", return_value=mock_response2):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "tools"}),
                content_type="application/json",
            )
        data = json.loads(response.content)
        assert data["created"] == 0
        assert data["updated"] == 1
        assert data["skipped"] == 0
        assert data["total"] == 1

    def test_api_run_importer_museums(self):
        from unittest.mock import patch, MagicMock

        json_text = json.dumps(
            [
                {
                    "name": "Musée Mécanique",
                    "url": "https://www.niche-museums.com/1",
                    "address": "Pier 45, Fishermans Wharf, San Francisco, CA 94133",
                    "description": "A collection of antique arcade games.",
                    "created": "2019-10-23T21:32:12-07:00",
                },
                {
                    "name": "Bigfoot Discovery Museum",
                    "url": "https://www.niche-museums.com/2",
                    "address": "5497 Highway 9, Felton, CA 95018",
                    "description": "Dedicated to the search for Bigfoot.",
                    "created": "2019-10-23T21:32:12-07:00",
                },
            ]
        )

        mock_response = MagicMock()
        mock_response.text = json_text
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "museums"}),
                content_type="application/json",
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["created"] == 2
        assert data["total"] == 2
        assert "Musée Mécanique" in data["items_html"]
        assert 'class="beat-label museum"' in data["items_html"]

    def test_api_run_importer_museums_skips_no_url(self):
        from unittest.mock import patch, MagicMock

        json_text = json.dumps(
            [
                {
                    "name": "Museum Without URL",
                    "address": "Somewhere",
                    "description": "No URL provided.",
                    "created": "2019-10-23T21:32:12-07:00",
                },
                {
                    "name": "Museum With URL",
                    "url": "https://www.niche-museums.com/2",
                    "address": "Elsewhere",
                    "description": "Has a URL.",
                    "created": "2019-10-23T21:32:12-07:00",
                },
            ]
        )

        mock_response = MagicMock()
        mock_response.text = json_text
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "museums"}),
                content_type="application/json",
            )
        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["created"] == 1

    def test_api_run_importer_museums_skips_unchanged(self):
        from unittest.mock import patch, MagicMock

        json_text = json.dumps(
            [
                {
                    "name": "Test Museum",
                    "url": "https://www.niche-museums.com/1",
                    "address": "123 Main St",
                    "description": "A test museum.",
                    "created": "2019-10-23T21:32:12-07:00",
                },
            ]
        )

        mock_response = MagicMock()
        mock_response.text = json_text
        mock_response.raise_for_status = MagicMock()

        self.client.login(username="admin", password="password")

        # First run: creates the museum
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "museums"}),
                content_type="application/json",
            )
        data = json.loads(response.content)
        assert data["created"] == 1
        assert data["skipped"] == 0

        # Second run with same data: should skip
        with patch("blog.importers.httpx.get", return_value=mock_response):
            response = self.client.post(
                "/api/run-importer/",
                json.dumps({"importer": "museums"}),
                content_type="application/json",
            )
        data = json.loads(response.content)
        assert data["created"] == 0
        assert data["skipped"] == 1

    def test_admin_index_has_importers_link(self):
        self.client.login(username="admin", password="password")
        response = self.client.get("/admin/")
        self.assertContains(response, "/admin/importers/")
        self.assertContains(response, "Beat Importers")


class SponsorMessageTests(TransactionTestCase):
    def test_no_sponsor_message_no_banner(self):
        EntryFactory()
        response = self.client.get("/")
        self.assertNotContains(response, 'id="sponsored-banner"')

    def test_active_sponsor_message_shows_banner(self):
        SponsorMessageFactory(
            name="Acme Corp",
            message="Build faster with Acme.",
            learn_more_url="https://acme.example.com/",
            color_scheme="ocean",
        )
        EntryFactory()
        response = self.client.get("/")
        self.assertContains(response, "Acme Corp")
        self.assertContains(response, "Build faster with Acme.")
        self.assertContains(response, "https://acme.example.com/")
        self.assertContains(response, "sponsor-scheme-ocean")

    def test_inactive_sponsor_message_hidden(self):
        SponsorMessageFactory(is_active=False, name="Hidden Sponsor")
        EntryFactory()
        response = self.client.get("/")
        self.assertNotContains(response, "Hidden Sponsor")

    def test_expired_sponsor_message_hidden(self):
        SponsorMessageFactory(
            name="Expired Sponsor",
            display_from=timezone.now() - timedelta(days=30),
            display_until=timezone.now() - timedelta(days=1),
        )
        EntryFactory()
        response = self.client.get("/")
        self.assertNotContains(response, "Expired Sponsor")

    def test_future_sponsor_message_hidden(self):
        SponsorMessageFactory(
            name="Future Sponsor",
            display_from=timezone.now() + timedelta(days=1),
            display_until=timezone.now() + timedelta(days=30),
        )
        EntryFactory()
        response = self.client.get("/")
        self.assertNotContains(response, "Future Sponsor")

    def test_highest_pk_selected(self):
        SponsorMessageFactory(name="First Sponsor", color_scheme="warm")
        SponsorMessageFactory(name="Second Sponsor", color_scheme="sage")
        EntryFactory()
        response = self.client.get("/")
        self.assertContains(response, "Second Sponsor")
        self.assertNotContains(response, "First Sponsor")

    def test_banner_on_smallhead_pages(self):
        SponsorMessageFactory(name="Detail Sponsor")
        entry = EntryFactory()
        response = self.client.get(entry.get_absolute_url())
        self.assertContains(response, "Detail Sponsor")

    def test_banner_always_visible_no_display_none(self):
        SponsorMessageFactory(name="Visible Sponsor", color_scheme="sage")
        EntryFactory()
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn('id="sponsored-banner"', content)
        # Banner should not be hidden with display:none
        idx = content.index('id="sponsored-banner"')
        banner_tag = content[content.rfind("<", 0, idx) : content.index(">", idx) + 1]
        self.assertNotIn("display:none", banner_tag)
        self.assertNotIn("display: none", banner_tag)

    def test_about_sponsor_preview_no_active_message(self):
        response = self.client.get("/about/?sponsor-preview=1")
        self.assertEqual(response.status_code, 200)


class GuideTests(TransactionTestCase):
    def test_guide_index(self):
        guide = GuideFactory(title="Test Guide", description="A test guide")
        ChapterFactory(guide=guide, title="Chapter 1", order=1)
        ChapterFactory(guide=guide, title="Chapter 2", order=2)
        response = self.client.get("/guides/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Guide")
        self.assertContains(response, "2 chapters")

    def test_guide_index_hides_drafts(self):
        GuideFactory(title="Published Guide")
        GuideFactory(title="Draft Guide", is_draft=True)
        response = self.client.get("/guides/")
        self.assertContains(response, "Published Guide")
        self.assertNotContains(response, "Draft Guide")

    def test_guide_detail(self):
        guide = GuideFactory(
            title="My Guide", slug="my-guide", description="Guide desc"
        )
        ch1 = ChapterFactory(guide=guide, title="First Chapter", slug="first", order=1)
        ch2 = ChapterFactory(
            guide=guide, title="Second Chapter", slug="second", order=2
        )
        response = self.client.get("/guides/my-guide/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Guide")
        self.assertContains(response, "First Chapter")
        self.assertContains(response, "Second Chapter")

    def test_guide_detail_hides_draft_chapters(self):
        guide = GuideFactory(slug="g1")
        ChapterFactory(guide=guide, title="Visible Chapter", slug="visible", order=1)
        ChapterFactory(
            guide=guide, title="Draft Chapter", slug="draft", order=2, is_draft=True
        )
        response = self.client.get("/guides/g1/")
        self.assertContains(response, "Visible Chapter")
        self.assertNotContains(response, "Draft Chapter")

    def test_draft_guide_404_for_anonymous(self):
        GuideFactory(slug="draft-guide", is_draft=True)
        response = self.client.get("/guides/draft-guide/")
        self.assertEqual(response.status_code, 404)

    def test_draft_guide_visible_for_staff(self):
        User.objects.create_superuser("admin", "admin@example.com", "password")
        self.client.login(username="admin", password="password")
        GuideFactory(slug="draft-guide", title="Secret Guide", is_draft=True)
        response = self.client.get("/guides/draft-guide/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secret Guide")

    def test_chapter_detail(self):
        guide = GuideFactory(slug="g2")
        ChapterFactory(
            guide=guide,
            title="My Chapter",
            slug="my-chapter",
            body="**bold text**",
            order=1,
        )
        response = self.client.get("/guides/g2/my-chapter/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Chapter")
        self.assertContains(response, "<strong>bold text</strong>")

    def test_draft_chapter_404_for_anonymous(self):
        guide = GuideFactory(slug="g3")
        ChapterFactory(guide=guide, slug="draft-ch", is_draft=True)
        response = self.client.get("/guides/g3/draft-ch/")
        self.assertEqual(response.status_code, 404)

    def test_draft_chapter_visible_for_staff(self):
        User.objects.create_superuser("admin", "admin@example.com", "password")
        self.client.login(username="admin", password="password")
        guide = GuideFactory(slug="g4")
        ChapterFactory(guide=guide, slug="draft-ch", title="Draft Ch", is_draft=True)
        response = self.client.get("/guides/g4/draft-ch/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Draft Ch")

    def test_chapter_ordering(self):
        guide = GuideFactory(slug="g5")
        ChapterFactory(guide=guide, title="Second", slug="second", order=2)
        ChapterFactory(guide=guide, title="First", slug="first", order=1)
        ChapterFactory(guide=guide, title="Third", slug="third", order=3)
        response = self.client.get("/guides/g5/")
        content = response.content.decode()
        first_pos = content.index("First")
        second_pos = content.index("Second")
        third_pos = content.index("Third")
        self.assertLess(first_pos, second_pos)
        self.assertLess(second_pos, third_pos)

    def test_chapter_navigation(self):
        guide = GuideFactory(slug="g6")
        ChapterFactory(guide=guide, title="Ch 1", slug="ch-1", order=1)
        ChapterFactory(guide=guide, title="Ch 2", slug="ch-2", order=2)
        ChapterFactory(guide=guide, title="Ch 3", slug="ch-3", order=3)
        # First chapter: no previous, has next
        response = self.client.get("/guides/g6/ch-1/")
        self.assertNotContains(response, "Ch 0")
        self.assertContains(response, "Ch 2")
        # Middle chapter: has both
        response = self.client.get("/guides/g6/ch-2/")
        self.assertContains(response, "Ch 1")
        self.assertContains(response, "Ch 3")
        # Last chapter: has previous, no next
        response = self.client.get("/guides/g6/ch-3/")
        self.assertContains(response, "Ch 2")

    def test_chapter_navigation_skips_draft_chapters(self):
        """Next/previous links on non-draft chapter pages should skip draft chapters."""
        guide = GuideFactory(slug="g-nav-draft")
        ChapterFactory(guide=guide, title="Ch 1", slug="ch-1", order=1)
        ChapterFactory(
            guide=guide, title="Ch 2 Draft", slug="ch-2", order=2, is_draft=True
        )
        ChapterFactory(guide=guide, title="Ch 3", slug="ch-3", order=3)
        # Ch 1 should link to Ch 3 (skipping draft Ch 2)
        response = self.client.get("/guides/g-nav-draft/ch-1/")
        self.assertContains(response, "Ch 3")
        self.assertNotContains(response, "Ch 2 Draft")
        # Ch 3 should link back to Ch 1 (skipping draft Ch 2)
        response = self.client.get("/guides/g-nav-draft/ch-3/")
        self.assertContains(response, "Ch 1")
        self.assertNotContains(response, "Ch 2 Draft")

    def test_chapter_navigation_skips_drafts_for_staff(self):
        """Staff viewing a non-draft chapter should also skip drafts in navigation."""
        from django.contrib.auth.models import User

        User.objects.create_superuser("navstaff", "s@s.com", "pass")
        self.client.login(username="navstaff", password="pass")
        guide = GuideFactory(slug="g-nav-staff")
        ChapterFactory(guide=guide, title="Ch A", slug="ch-a", order=1)
        ChapterFactory(
            guide=guide, title="Ch B Draft", slug="ch-b", order=2, is_draft=True
        )
        ChapterFactory(guide=guide, title="Ch C", slug="ch-c", order=3)
        # Staff on non-draft Ch A: next should be Ch C, not draft Ch B
        response = self.client.get("/guides/g-nav-staff/ch-a/")
        self.assertContains(response, "Ch C")
        self.assertNotContains(response, "Ch B Draft")
        # Staff on non-draft Ch C: previous should be Ch A
        response = self.client.get("/guides/g-nav-staff/ch-c/")
        self.assertContains(response, "Ch A")
        self.assertNotContains(response, "Ch B Draft")

    def test_chapter_in_draft_guide_404(self):
        guide = GuideFactory(slug="draft-g", is_draft=True)
        ChapterFactory(guide=guide, slug="ch1")
        response = self.client.get("/guides/draft-g/ch1/")
        self.assertEqual(response.status_code, 404)

    def test_guide_get_absolute_url(self):
        guide = GuideFactory(slug="test-guide")
        self.assertEqual(guide.get_absolute_url(), "/guides/test-guide/")

    def test_chapter_get_absolute_url(self):
        guide = GuideFactory(slug="test-guide")
        chapter = ChapterFactory(guide=guide, slug="test-chapter")
        self.assertEqual(chapter.get_absolute_url(), "/guides/test-guide/test-chapter/")


class ChapterEverywhereTests(TransactionTestCase):
    """Tests for chapters showing up in homepage, archives, search, feeds, calendar."""

    def _make_chapter(self, **kwargs):
        defaults = {
            "title": "Test Chapter",
            "body": "Chapter body with **bold**",
            "is_draft": False,
        }
        defaults.update(kwargs)
        if "guide" not in defaults:
            defaults["guide"] = GuideFactory(is_draft=False)
        return ChapterFactory(**defaults)

    def test_chapter_on_homepage(self):
        chapter = self._make_chapter()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, chapter.title)
        self.assertContains(response, chapter.guide.title)

    def test_draft_chapter_not_on_homepage(self):
        chapter = self._make_chapter(title="Draft Chapter", is_draft=True)
        response = self.client.get("/")
        self.assertNotContains(response, "Draft Chapter")

    def test_chapter_in_draft_guide_not_on_homepage(self):
        guide = GuideFactory(is_draft=True)
        chapter = self._make_chapter(guide=guide, title="Hidden Chapter")
        response = self.client.get("/")
        self.assertNotContains(response, "Hidden Chapter")

    def test_chapter_on_day_archive(self):
        chapter = self._make_chapter()
        # Calendar widget needs at least one Entry
        EntryFactory(created=chapter.created)
        url = "/{}/".format(chapter.created.strftime("%Y/%b/%-d"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, chapter.title)
        self.assertContains(response, chapter.guide.title)

    def test_draft_chapter_not_on_day_archive(self):
        chapter = self._make_chapter(title="Draft Day Chapter", is_draft=True)
        # Create a non-draft item on the same day so the page exists
        EntryFactory(created=chapter.created)
        url = "/{}/".format(chapter.created.strftime("%Y/%b/%-d"))
        response = self.client.get(url)
        self.assertNotContains(response, "Draft Day Chapter")

    def test_chapter_on_month_archive(self):
        chapter = self._make_chapter()
        # Calendar widget needs at least one Entry
        EntryFactory(created=chapter.created)
        url = "/{}/".format(chapter.created.strftime("%Y/%b"))
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, chapter.title)

    def test_chapter_on_tag_archive(self):
        tag = Tag.objects.create(tag="testchaptertag")
        chapter = self._make_chapter()
        chapter.tags.add(tag)
        response = self.client.get("/tags/testchaptertag/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, chapter.title)
        self.assertContains(response, chapter.guide.title)

    def test_draft_chapter_not_on_tag_archive(self):
        tag = Tag.objects.create(tag="testdrafttag")
        chapter = self._make_chapter(title="Draft Tagged", is_draft=True)
        chapter.tags.add(tag)
        # Also add a published item so the tag page exists
        entry = EntryFactory()
        entry.tags.add(tag)
        response = self.client.get("/tags/testdrafttag/")
        self.assertNotContains(response, "Draft Tagged")

    def test_chapter_in_draft_guide_not_on_tag_archive(self):
        tag = Tag.objects.create(tag="guidedrafttag")
        guide = GuideFactory(is_draft=True)
        chapter = self._make_chapter(guide=guide, title="Guide Draft Tagged")
        chapter.tags.add(tag)
        entry = EntryFactory()
        entry.tags.add(tag)
        response = self.client.get("/tags/guidedrafttag/")
        self.assertNotContains(response, "Guide Draft Tagged")

    def test_chapter_in_search(self):
        chapter = self._make_chapter(
            title="Searchable Chapter", body="unique searchterm here"
        )
        # Update search index
        from django.contrib.postgres.search import SearchVector
        from django.db.models import Value, TextField
        from blog.models import Chapter
        import operator
        from functools import reduce

        components = chapter.index_components()
        search_vectors = []
        for weight, text in components.items():
            search_vectors.append(
                SearchVector(Value(text, output_field=TextField()), weight=weight)
            )
        Chapter.objects.filter(pk=chapter.pk).update(
            search_document=reduce(operator.add, search_vectors)
        )

        response = self.client.get("/search/?q=searchterm")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Searchable Chapter")

    def test_chapter_in_everything_feed(self):
        chapter = self._make_chapter(title="Feed Chapter")
        response = self.client.get("/atom/everything/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Feed Chapter")
        self.assertContains(response, chapter.guide.title)

    def test_draft_chapter_not_in_everything_feed(self):
        self._make_chapter(title="Draft Feed Chapter", is_draft=True)
        response = self.client.get("/atom/everything/")
        self.assertNotContains(response, "Draft Feed Chapter")

    def test_chapter_guide_breadcrumb_style(self):
        """Chapter should show guide name with > and no underline."""
        chapter = self._make_chapter()
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn(chapter.guide.title, content)
        self.assertIn("&gt;", content)
        self.assertIn("border-bottom: none", content)
        self.assertIn("text-decoration: none", content)

    def test_chapter_body_rendered_as_markdown(self):
        chapter = self._make_chapter(body="- item one\n- item two\n- item three")
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("<li>", content)
        self.assertIn("item one", content)

    def test_chapter_has_tags(self):
        """Chapter (extending BaseModel) should support tags."""
        tag = Tag.objects.create(tag="chaptertest")
        chapter = self._make_chapter()
        chapter.tags.add(tag)
        self.assertEqual(
            list(chapter.tags.values_list("tag", flat=True)), ["chaptertest"]
        )

    def test_chapter_index_components(self):
        """Chapter should return title, body, and tags for search indexing."""
        tag = Tag.objects.create(tag="indextest")
        chapter = self._make_chapter(title="Index Title", body="Index Body")
        chapter.tags.add(tag)
        components = chapter.index_components()
        self.assertEqual(components["A"], "Index Title")
        self.assertEqual(components["C"], "Index Body")
        self.assertIn("indextest", components["B"])

    def test_chapter_word_count_inline_with_last_paragraph(self):
        """When chapter has >3 paragraphs, word count should be inline in the last shown paragraph, not a separate <p>."""
        body = "Para one.\n\nPara two.\n\nPara three.\n\nPara four."
        chapter = self._make_chapter(body=body)
        response = self.client.get("/")
        content = response.content.decode()
        # The word count link should NOT be in its own <p>
        self.assertNotIn("<p><span", content)
        # It should appear inline before </p>
        self.assertIn("words</a>]</span></p>", content)
        # The third paragraph text and the word count should be in the same <p>
        self.assertIn("Para three.", content)
        self.assertIn("word", content)

    def test_chapter_short_body_no_word_count(self):
        """When chapter has <=3 paragraphs, no word count should be shown."""
        body = "Para one.\n\nPara two.\n\nPara three."
        chapter = self._make_chapter(body=body)
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("Para one.", content)
        self.assertIn("Para three.", content)
        self.assertNotIn("words</a>]", content)

    def test_chapter_single_paragraph_no_word_count(self):
        """A chapter with a single paragraph should not show word count."""
        chapter = self._make_chapter(body="Just one paragraph.")
        response = self.client.get("/")
        content = response.content.decode()
        self.assertIn("Just one paragraph.", content)
        self.assertNotIn("words</a>]", content)
        self.assertNotIn("word</a>]", content)

    def test_chapter_word_count_on_tag_page(self):
        """Word count should also be inline on tag archive pages."""
        body = "Para one.\n\nPara two.\n\nPara three.\n\nPara four."
        tag = Tag.objects.create(tag="excerpttest")
        chapter = self._make_chapter(body=body)
        chapter.tags.add(tag)
        response = self.client.get("/tags/excerpttest/")
        content = response.content.decode()
        self.assertNotIn("<p><span", content)
        self.assertIn("words</a>]</span></p>", content)


class ChapterChangeTests(TransactionTestCase):
    def test_change_recorded_on_create(self):
        """Creating a new chapter should automatically create a ChapterChange."""
        guide = GuideFactory(slug="cg1")
        chapter = ChapterFactory(guide=guide, title="New", body="Body", slug="new")
        changes = list(ChapterChange.objects.filter(chapter=chapter))
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0].title, "New")
        self.assertEqual(changes[0].body, "Body")
        self.assertEqual(changes[0].created, chapter.created)

    def test_change_recorded_on_title_edit(self):
        guide = GuideFactory(slug="cg2")
        chapter = ChapterFactory(guide=guide, title="Original", body="Body", slug="ch")
        chapter.title = "Updated"
        chapter.save()
        changes = list(
            ChapterChange.objects.filter(chapter=chapter).order_by("created")
        )
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0].title, "Original")
        self.assertEqual(changes[1].title, "Updated")
        self.assertEqual(changes[1].body, "Body")

    def test_change_recorded_on_body_edit(self):
        guide = GuideFactory(slug="cg3")
        chapter = ChapterFactory(guide=guide, title="Title", body="Old body", slug="ch")
        chapter.body = "New body"
        chapter.save()
        changes = list(
            ChapterChange.objects.filter(chapter=chapter).order_by("created")
        )
        self.assertEqual(len(changes), 2)
        self.assertEqual(changes[0].body, "Old body")
        self.assertEqual(changes[1].body, "New body")
        self.assertEqual(changes[1].title, "Title")

    def test_change_recorded_on_is_draft_edit(self):
        guide = GuideFactory(slug="cg4")
        chapter = ChapterFactory(
            guide=guide, title="Title", body="Body", slug="ch", is_draft=True
        )
        chapter.is_draft = False
        chapter.save()
        changes = list(
            ChapterChange.objects.filter(chapter=chapter).order_by("created")
        )
        self.assertEqual(len(changes), 2)
        self.assertTrue(changes[0].is_draft)
        self.assertFalse(changes[1].is_draft)

    def test_no_change_on_untracked_field_edit(self):
        """Editing order should not create an additional ChapterChange."""
        guide = GuideFactory(slug="cg5")
        chapter = ChapterFactory(guide=guide, title="Title", body="Body", slug="ch")
        chapter.order = 99
        chapter.save()
        # Only the initial creation change should exist
        self.assertEqual(ChapterChange.objects.filter(chapter=chapter).count(), 1)

    def test_multiple_changes_recorded(self):
        guide = GuideFactory(slug="cg6")
        chapter = ChapterFactory(guide=guide, title="V1", body="Body", slug="ch")
        chapter.title = "V2"
        chapter.save()
        chapter.title = "V3"
        chapter.save()
        changes = list(
            ChapterChange.objects.filter(chapter=chapter).order_by("created")
        )
        self.assertEqual(len(changes), 3)
        self.assertEqual(changes[0].title, "V1")
        self.assertEqual(changes[1].title, "V2")
        self.assertEqual(changes[2].title, "V3")

    def test_change_defaults(self):
        guide = GuideFactory(slug="cg7")
        chapter = ChapterFactory(guide=guide, title="Title", body="Body", slug="ch")
        change = ChapterChange.objects.filter(chapter=chapter).first()
        self.assertFalse(change.is_notable)
        self.assertEqual(change.change_note, "")

    def test_change_str(self):
        guide = GuideFactory(slug="cg8")
        chapter = ChapterFactory(
            guide=guide, title="My Chapter", body="Body", slug="ch"
        )
        chapter.title = "Updated Chapter"
        chapter.save()
        change = ChapterChange.objects.filter(chapter=chapter).order_by("created").last()
        self.assertIn("Updated Chapter", str(change))


class ChapterChangesPageTests(TransactionTestCase):
    def test_changes_page_initial_version(self):
        """Creating a chapter auto-creates a ChapterChange shown as initial version."""
        guide = GuideFactory(slug="pg2")
        chapter = ChapterFactory(guide=guide, title="Ch", body="Body", slug="ch")
        response = self.client.get("/guides/pg2/ch/changes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Initial version")

    def test_changes_page_shows_diff(self):
        guide = GuideFactory(slug="pg3")
        chapter = ChapterFactory(guide=guide, title="Ch", body="Line one", slug="ch")
        chapter.body = "Line two"
        chapter.save()
        response = self.client.get("/guides/pg3/ch/changes/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("diff-add", content)
        self.assertIn("diff-remove", content)

    def test_changes_page_shows_title_diff(self):
        guide = GuideFactory(slug="pg4")
        chapter = ChapterFactory(guide=guide, title="Old Title", body="Body", slug="ch")
        chapter.title = "New Title"
        chapter.save()
        response = self.client.get("/guides/pg4/ch/changes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Title")

    def test_changes_page_shows_draft_status_change(self):
        guide = GuideFactory(slug="pg5")
        chapter = ChapterFactory(
            guide=guide, title="Ch", body="Body", slug="ch", is_draft=True
        )
        chapter.is_draft = False
        chapter.save()
        # Must be staff to view a chapter whose guide is not draft but chapter was draft
        User.objects.create_superuser("admin", "a@b.com", "pw")
        self.client.login(username="admin", password="pw")
        response = self.client.get("/guides/pg5/ch/changes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Draft status changed")

    def test_changes_page_shows_change_note(self):
        guide = GuideFactory(slug="pg6")
        chapter = ChapterFactory(guide=guide, title="Ch", body="Body", slug="ch")
        # Add a change_note to the auto-created initial change
        change = ChapterChange.objects.get(chapter=chapter)
        change.change_note = "Initial import"
        change.save()
        response = self.client.get("/guides/pg6/ch/changes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Initial import")

    def test_changes_page_draft_chapter_404_for_anonymous(self):
        guide = GuideFactory(slug="pg7")
        ChapterFactory(guide=guide, slug="draft-ch", is_draft=True)
        response = self.client.get("/guides/pg7/draft-ch/changes/")
        self.assertEqual(response.status_code, 404)

    def test_changes_page_draft_guide_404_for_anonymous(self):
        guide = GuideFactory(slug="pg8", is_draft=True)
        ChapterFactory(guide=guide, slug="ch")
        response = self.client.get("/guides/pg8/ch/changes/")
        self.assertEqual(response.status_code, 404)

    def test_changes_page_draft_visible_for_staff(self):
        User.objects.create_superuser("admin", "a@b.com", "pw")
        self.client.login(username="admin", password="pw")
        guide = GuideFactory(slug="pg9", is_draft=True)
        chapter = ChapterFactory(guide=guide, title="Secret Ch", slug="ch")
        response = self.client.get("/guides/pg9/ch/changes/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Secret Ch")

    def test_changes_page_breadcrumb(self):
        guide = GuideFactory(slug="pg10", title="My Guide")
        chapter = ChapterFactory(
            guide=guide, title="My Chapter", body="Body", slug="ch"
        )
        response = self.client.get("/guides/pg10/ch/changes/")
        self.assertContains(response, "My Guide")
        self.assertContains(response, "My Chapter")
        self.assertContains(response, "/guides/pg10/")
        self.assertContains(response, "/guides/pg10/ch/")
