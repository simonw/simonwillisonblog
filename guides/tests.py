from django.test import TransactionTestCase

from guides.factories import ChapterFactory, GuideFactory
from guides.views import _build_diff_html, _char_diff_html


class CharDiffHtmlTests(TransactionTestCase):
    def test_highlights_changed_chars(self):
        result = _char_diff_html("hello world", "hello World", is_remove=False)
        self.assertIn('class="char-highlight"', result)
        self.assertIn("W", result)
        self.assertIn("hello ", result)

    def test_remove_side(self):
        result = _char_diff_html("hello world", "hello World", is_remove=True)
        self.assertIn('<span class="char-highlight">w</span>', result)

    def test_insertion(self):
        result = _char_diff_html("abc", "abXc", is_remove=False)
        self.assertIn('<span class="char-highlight">X</span>', result)

    def test_deletion(self):
        result = _char_diff_html("abXc", "abc", is_remove=True)
        self.assertIn('<span class="char-highlight">X</span>', result)

    def test_escapes_html(self):
        result = _char_diff_html("<b>old</b>", "<b>new</b>", is_remove=False)
        self.assertNotIn("<b>", result)
        self.assertIn("&lt;b&gt;", result)


class BuildDiffHtmlTests(TransactionTestCase):
    def test_basic(self):
        diff_lines = [
            "--- a\n",
            "+++ b\n",
            "@@ -1 +1 @@\n",
            "-old line\n",
            "+new line\n",
        ]
        result = _build_diff_html(diff_lines)
        self.assertIn('class="diff-header"', result)
        self.assertIn('class="diff-remove"', result)
        self.assertIn('class="diff-add"', result)
        self.assertIn('class="char-highlight"', result)

    def test_strips_double_newlines(self):
        diff_lines = [
            "--- a\n",
            "+++ b\n",
            "@@ -1 +1 @@\n",
            "-old\n",
            "+new\n",
        ]
        result = _build_diff_html(diff_lines)
        self.assertNotIn("\n\n", result)

    def test_unpaired_lines(self):
        diff_lines = [
            "--- a\n",
            "+++ b\n",
            "@@ -1,2 +1 @@\n",
            "-removed line one\n",
            "-removed line two\n",
            "+added line\n",
        ]
        result = _build_diff_html(diff_lines)
        self.assertIn('class="char-highlight"', result)
        self.assertIn("removed line two", result)

    def test_returns_none_for_empty(self):
        self.assertIsNone(_build_diff_html(None))
        self.assertIsNone(_build_diff_html([]))


class H2HeadingsTests(TransactionTestCase):
    def test_h2_headings_extracts_headings(self):
        guide = GuideFactory(slug="h2-test")
        chapter = ChapterFactory(
            guide=guide,
            slug="ch",
            title="Test",
            body="## First heading\n\nSome text\n\n## Second heading\n\nMore text",
        )
        headings = chapter.h2_headings()
        self.assertEqual(len(headings), 2)
        self.assertEqual(headings[0]["id"], "first-heading")
        self.assertEqual(headings[0]["title"], "First heading")
        self.assertEqual(headings[1]["id"], "second-heading")
        self.assertEqual(headings[1]["title"], "Second heading")

    def test_h2_headings_empty_when_no_h2(self):
        guide = GuideFactory(slug="h2-empty")
        chapter = ChapterFactory(
            guide=guide,
            slug="ch",
            title="Test",
            body="Just a paragraph with no headings.",
        )
        self.assertEqual(chapter.h2_headings(), [])

    def test_h2_headings_ignores_h3(self):
        guide = GuideFactory(slug="h2-h3")
        chapter = ChapterFactory(
            guide=guide,
            slug="ch",
            title="Test",
            body="## H2 heading\n\n### H3 heading\n\nText",
        )
        headings = chapter.h2_headings()
        self.assertEqual(len(headings), 1)
        self.assertEqual(headings[0]["title"], "H2 heading")

    def test_guide_detail_shows_h2_subheadings(self):
        guide = GuideFactory(slug="h2-detail", is_draft=False)
        ChapterFactory(
            guide=guide,
            slug="ch1",
            title="Chapter One",
            body="## Sub one\n\nText\n\n## Sub two\n\nMore",
            is_draft=False,
        )
        response = self.client.get("/guides/h2-detail/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("#sub-one", content)
        self.assertIn("#sub-two", content)
        self.assertIn("Sub one", content)
        self.assertIn("Sub two", content)


class ChapterChangesCharHighlightTests(TransactionTestCase):
    def test_changes_page_has_char_highlights(self):
        guide = GuideFactory(slug="pg-char1")
        chapter = ChapterFactory(
            guide=guide,
            title="Ch",
            body="I released the code to GitHub without paying attention",
            slug="ch",
        )
        chapter.body = "I released the code to GitHub) without paying attention"
        chapter.save()
        response = self.client.get("/guides/pg-char1/ch/changes/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("char-highlight", content)
        self.assertIn("diff-add", content)
        self.assertIn("diff-remove", content)
