import xml.etree.ElementTree as ET
from django.test import TransactionTestCase
from django.utils import timezone
from .factories import GuideFactory, ChapterFactory
from .models import ChapterChange


class GuideFeedTests(TransactionTestCase):
    def test_guide_feed_url_exists(self):
        """Guide should have a feed URL."""
        guide = GuideFactory()
        response = self.client.get(f"/guides/{guide.slug}.atom")
        self.assertEqual(response.status_code, 200)

    def test_guide_feed_has_atom_content_type(self):
        """Feed should have proper content type."""
        guide = GuideFactory()
        response = self.client.get(f"/guides/{guide.slug}.atom")
        self.assertIn("application/xml", response["Content-Type"])

    def test_guide_feed_includes_new_chapters(self):
        """Feed should include newly created chapters."""
        guide = GuideFactory()
        chapter1 = ChapterFactory(guide=guide, title="Chapter 1", is_draft=False)
        chapter2 = ChapterFactory(guide=guide, title="Chapter 2", is_draft=False)

        response = self.client.get(f"/guides/{guide.slug}.atom")
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall("atom:entry", ns)
        titles = [e.find("atom:title", ns).text for e in entries]

        self.assertIn("Chapter 1", titles)
        self.assertIn("Chapter 2", titles)

    def test_guide_feed_includes_notable_changes(self):
        """Feed should include notable changes to chapters."""
        guide = GuideFactory()
        chapter = ChapterFactory(
            guide=guide,
            title="Chapter",
            body="Original body",
            is_draft=False
        )
        # Create a notable change
        change = ChapterChange.objects.create(
            chapter=chapter,
            created=timezone.now(),
            title="Chapter",
            body="Updated body",
            is_draft=False,
            is_notable=True,
            change_note="Updated the explanation"
        )

        response = self.client.get(f"/guides/{guide.slug}.atom")
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall("atom:entry", ns)
        self.assertGreater(len(entries), 0)
        # Should have an entry for the notable change
        found_change = False
        for entry in entries:
            title = entry.find("atom:title", ns)
            content = entry.find("atom:content", ns) or entry.find("atom:summary", ns)
            if title is not None and "Updated the explanation" in (content.text or ""):
                found_change = True
                break
        self.assertTrue(found_change, "Notable change not found in feed")

    def test_guide_feed_excludes_draft_chapters(self):
        """Feed should not include draft chapters."""
        guide = GuideFactory()
        ChapterFactory(guide=guide, title="Draft Chapter", is_draft=True)
        public_chapter = ChapterFactory(guide=guide, title="Public Chapter", is_draft=False)

        response = self.client.get(f"/guides/{guide.slug}.atom")
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall("atom:entry", ns)
        titles = [e.find("atom:title", ns).text for e in entries]

        self.assertNotIn("Draft Chapter", titles)
        self.assertIn("Public Chapter", titles)

    def test_guide_feed_excludes_draft_guides(self):
        """Feed should not be accessible for draft guides."""
        guide = GuideFactory(is_draft=True)
        ChapterFactory(guide=guide, title="Chapter", is_draft=False)

        response = self.client.get(f"/guides/{guide.slug}.atom")
        self.assertEqual(response.status_code, 404)

    def test_guide_feed_excludes_non_notable_changes(self):
        """Feed should not include non-notable changes to chapters."""
        guide = GuideFactory()
        chapter = ChapterFactory(
            guide=guide,
            title="Chapter",
            body="Original body",
            is_draft=False
        )
        # Create a non-notable change
        change = ChapterChange.objects.create(
            chapter=chapter,
            created=timezone.now(),
            title="Chapter",
            body="Minor update",
            is_draft=False,
            is_notable=False
        )

        response = self.client.get(f"/guides/{guide.slug}.atom")
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        entries = root.findall("atom:entry", ns)
        # Should only have the original chapter creation, not the non-notable change
        self.assertEqual(len(entries), 1)
        title = entries[0].find("atom:title", ns).text
        self.assertEqual(title, "Chapter")

    def test_guide_feed_has_cors_and_cache_headers(self):
        """Feed should have CORS and cache headers."""
        guide = GuideFactory()
        ChapterFactory(guide=guide, is_draft=False)

        response = self.client.get(f"/guides/{guide.slug}.atom")
        self.assertEqual(response["Access-Control-Allow-Origin"], "*")
        self.assertIn("s-maxage", response["Cache-Control"])

    def test_guide_feed_title_format(self):
        """Feed title should include guide name."""
        guide = GuideFactory(title="Python Guide")
        ChapterFactory(guide=guide, is_draft=False)

        response = self.client.get(f"/guides/{guide.slug}.atom")
        root = ET.fromstring(response.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        title = root.find("atom:title", ns).text
        self.assertIn("Python Guide", title)

    def test_guide_detail_page_has_feed_icon(self):
        """Guide detail page should have feed icon link."""
        guide = GuideFactory(is_draft=False)
        ChapterFactory(guide=guide, is_draft=False)

        response = self.client.get(guide.get_absolute_url())
        self.assertContains(response, f"/guides/{guide.slug}.atom")
        self.assertContains(response, "Atom feed")
