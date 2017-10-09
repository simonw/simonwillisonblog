from django.test import TestCase
from .factories import (
    EntryFactory,
    BlogmarkFactory,
    QuotationFactory,
)


class BlogTests(TestCase):
    def test_homepage(self):
        db_entries = [
            EntryFactory(),
            EntryFactory(),
            EntryFactory(),
        ]
        BlogmarkFactory()
        QuotationFactory()
        response = self.client.get('/')
        entries = response.context['entries']
        self.assertEqual(
            [e.pk for e in entries],
            [e.pk for e in sorted(
                db_entries,
                key=lambda e: e.created, reverse=True
            )]
        )

    def test_entry(self):
        entry = EntryFactory()
        response = self.client.get(entry.get_absolute_url())
        self.assertTemplateUsed(response, 'entry.html')
        self.assertEqual(response.context['entry'].pk, entry.pk)

    def test_private_items_404(self):
        for obj in (
            EntryFactory(private=True),
            BlogmarkFactory(private=True),
            QuotationFactory(private=True),
        ):
            response = self.client.get(obj.get_absolute_url())
            self.assertEqual(response.status_code, 404)

    def test_blogmark(self):
        blogmark = BlogmarkFactory()
        response = self.client.get(blogmark.get_absolute_url())
        self.assertTemplateUsed(response, 'blogmark.html')
        self.assertEqual(response.context['blogmark'].pk, blogmark.pk)

    def test_quotation(self):
        quotation = QuotationFactory()
        response = self.client.get(quotation.get_absolute_url())
        self.assertTemplateUsed(response, 'quotation.html')
        self.assertEqual(response.context['quotation'].pk, quotation.pk)
