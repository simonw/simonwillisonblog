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

    def test_merge_tags(self):
        winner_tag = Tag.objects.create(tag="winner")
        loser_tag = Tag.objects.create(tag="loser")

        entry = EntryFactory(tags=[loser_tag])
        blogmark = BlogmarkFactory(tags=[loser_tag])
        quotation = QuotationFactory(tags=[loser_tag])

        response = self.client.post(
            "/admin/merge-tags/",
            {"winner_tag": winner_tag.id, "loser_tag": loser_tag.id},
        )

        self.assertRedirects(response, "/admin/merge-tags/")
        entry.refresh_from_db()
        blogmark.refresh_from_db()
        quotation.refresh_from_db()

        self.assertIn(winner_tag, entry.tags.all())
        self.assertNotIn(loser_tag, entry.tags.all())

        self.assertIn(winner_tag, blogmark.tags.all())
        self.assertNotIn(loser_tag, blogmark.tags.all())

        self.assertIn(winner_tag, quotation.tags.all())
        self.assertNotIn(loser_tag, quotation.tags.all())

        self.assertFalse(Tag.objects.filter(id=loser_tag.id).exists())
        self.assertTrue(
            PreviousTagName.objects.filter(tag=winner_tag, previous_name="loser").exists()
        )
