from django.test import TransactionTestCase
from blog.templatetags.entry_tags import do_typography_string
from .factories import (
    EntryFactory,
    BlogmarkFactory,
    QuotationFactory,
)
from blog.models import Tag, PreviousTagName


class BlogTests(TransactionTestCase):
    def test_homepage(self):
        db_entries = [
            EntryFactory(),
            EntryFactory(),
            EntryFactory(),
        ]
        BlogmarkFactory()
        QuotationFactory()
        response = self.client.get("/")
        entries = response.context["entries"]
        self.assertEqual(
            [e.pk for e in entries],
            [e.pk for e in sorted(db_entries, key=lambda e: e.created, reverse=True)],
        )

    def test_other_pages(self):
        entry = EntryFactory()
        blogmark = BlogmarkFactory()
        quotation = QuotationFactory()
        for path in (
            "/",
            "/{}/".format(entry.created.year),
            entry.get_absolute_url(),
            blogmark.get_absolute_url(),
            quotation.get_absolute_url(),
            "/{}/".format(entry.created.year),
            "/atom/everything/",
        ):
            response = self.client.get("/")
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
            created="2020-01-01",
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
        testing = Tag.objects.get_or_create(tag="testing")[0]

        live_entry = EntryFactory(title="publishedentry", created=draft_entry.created)
        live_blogmark = BlogmarkFactory(
            link_title="publishedblogmark", created=draft_blogmark.created
        )
        live_quotation = QuotationFactory(
            source="publishedquotation", created=draft_quotation.created
        )

        for obj in (
            draft_entry,
            draft_blogmark,
            draft_quotation,
            live_entry,
            live_blogmark,
            live_quotation,
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

        for path in paths:
            response = self.client.get(path)
            self.assertNotContains(response, "draftentry")

        robots_fragment = '<meta name="robots" content="noindex">'
        draft_warning_fragment = "This is a draft post"

        for obj in (draft_entry, draft_blogmark, draft_quotation):
            response2 = self.client.get(obj.get_absolute_url())
            self.assertContains(response2, robots_fragment)
            self.assertContains(response2, draft_warning_fragment)

            # Publish it
            obj.is_draft = False
            obj.save()

            response3 = self.client.get(obj.get_absolute_url())
            self.assertNotContains(response3, robots_fragment)
            self.assertNotContains(response3, draft_warning_fragment)

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
