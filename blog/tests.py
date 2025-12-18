from django.test import TransactionTestCase
from django.contrib.auth.models import User
from blog.templatetags.entry_tags import do_typography_string
from .factories import (
    EntryFactory,
    BlogmarkFactory,
    QuotationFactory,
    NoteFactory,
)
from blog.models import Tag, PreviousTagName, TagMerge
from django.utils import timezone
import datetime
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
                    "id": 1,
                    "tag": "testing",
                    "description": "",
                    "total_entry": 1,
                    "total_blogmark": 1,
                    "total_quotation": 1,
                    "total_note": 1,
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
                    "id": 1,
                    "tag": "testing",
                    "description": "",
                    "total_entry": 2,
                    "total_blogmark": 2,
                    "total_quotation": 2,
                    "total_note": 2,
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
        summary = response.content.decode()
        self.assertNotIn("note", summary)

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
