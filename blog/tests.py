from django.test import TransactionTestCase
from .factories import (
    EntryFactory,
    BlogmarkFactory,
    QuotationFactory,
)


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
