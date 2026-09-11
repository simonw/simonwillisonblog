from django.contrib.auth.models import User
from django.test import TransactionTestCase

from guides.factories import ChapterFactory, GuideFactory
from guides.models import Guide
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


class ChapterChangesVisibilityTests(TransactionTestCase):
    def test_public_history_excludes_draft_revisions(self):
        chapter = ChapterFactory(
            title="DRAFT_PRIVATE_TITLE",
            body="DRAFT_PRIVATE_BODY",
            is_draft=True,
        )
        chapter.changes.update(change_note="DRAFT_PRIVATE_NOTE")
        url = chapter.get_absolute_url()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url + "changes/").status_code, 404)

        chapter.title = "Published title"
        chapter.body = "Public first version\n"
        chapter.is_draft = False
        chapter.save()
        publication = chapter.changes.latest("created")
        chapter.body += "\nPublic second paragraph\n"
        chapter.save()

        reader = User.objects.create_user("reader")
        for authenticated in (False, True):
            with self.subTest(authenticated=authenticated):
                if authenticated:
                    self.client.force_login(reader)
                detail = self.client.get(url)
                self.assertContains(detail, "Public second paragraph")
                self.assertEqual(detail.context["chapter_num_changes"], 2)
                self.assertEqual(detail.context["chapter_created"], publication.created)
                history = self.client.get(url + "changes/")
                self.assertContains(history, '<div class="change-entry">', count=2)
                self.assertContains(history, "Public second paragraph")
                for response in (detail, history):
                    self.assertNotContains(response, "DRAFT_PRIVATE")

    def test_public_history_skips_drafts_between_public_revisions(self):
        chapter = ChapterFactory(title="Title", body="Public original\n")
        chapter.is_draft = True
        chapter.body += "\nINTERMEDIATE_PRIVATE_BODY\n"
        chapter.save()
        chapter.changes.filter(is_draft=True).update(
            change_note="INTERMEDIATE_PRIVATE_NOTE"
        )
        chapter.is_draft = False
        chapter.body = "Public original\n\nPublic addition\n"
        chapter.save()

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        self.assertNotContains(response, "INTERMEDIATE_PRIVATE")
        self.assertContains(response, "Public addition")
        self.assertContains(response, '<div class="change-entry">', count=2)

    def test_public_history_excludes_revisions_from_draft_guide(self):
        guide = GuideFactory(is_draft=True)
        chapter = ChapterFactory(
            guide=guide,
            title="GUIDE_PRIVATE_TITLE",
            body="GUIDE_PRIVATE_BODY",
            is_draft=False,
        )
        chapter.changes.update(change_note="GUIDE_PRIVATE_NOTE")
        url = chapter.get_absolute_url()
        self.assertEqual(self.client.get(url + "changes/").status_code, 404)
        chapter.title = "Published title"
        chapter.body = "Public first version\n"
        chapter.save()
        guide.is_draft = False
        guide.save()

        response = self.client.get(url + "changes/")
        self.assertNotContains(response, "GUIDE_PRIVATE")
        self.assertContains(response, "No changes recorded for this chapter.")
        chapter.body += "\nPublic second paragraph\n"
        chapter.save()
        chapter.body += "\nPublic third paragraph\n"
        chapter.save()
        response = self.client.get(url + "changes/")
        self.assertNotContains(response, "GUIDE_PRIVATE")
        self.assertContains(response, "Public third paragraph")
        self.assertContains(response, '<div class="change-entry">', count=2)

    def test_staff_can_see_private_history_without_caching(self):
        chapter = ChapterFactory(body="STAFF_ONLY_BODY", is_draft=True)
        chapter.changes.update(change_note="STAFF_ONLY_NOTE")
        chapter.body = "Published body"
        chapter.is_draft = False
        chapter.save()
        self.client.force_login(User.objects.create_user("staff", is_staff=True))

        history = self.client.get(chapter.get_absolute_url() + "changes/")
        self.assertContains(history, "STAFF_ONLY_NOTE")
        self.assertContains(history, '<div class="change-entry">', count=2)
        detail = self.client.get(chapter.get_absolute_url())
        self.assertEqual(detail.context["chapter_num_changes"], 2)
        for response in (detail, history):
            self.assertIn("private", response["Cache-Control"])
            self.assertIn("no-store", response["Cache-Control"])

    def test_history_with_unknown_guide_visibility_is_staff_only(self):
        chapter = ChapterFactory(body="LEGACY_PRIVATE_BODY")
        chapter.changes.update(
            guide_is_draft=None, change_note="LEGACY_PRIVATE_NOTE"
        )
        url = chapter.get_absolute_url()
        response = self.client.get(url + "changes/")
        self.assertContains(response, "No changes recorded for this chapter.")
        self.assertNotContains(response, "LEGACY_PRIVATE_NOTE")
        self.assertEqual(self.client.get(url).context["chapter_num_changes"], 0)

        chapter.body = "Published body"
        chapter.save()
        response = self.client.get(url + "changes/")
        self.assertNotContains(response, "LEGACY_PRIVATE")
        self.assertContains(response, '<div class="change-entry">', count=1)
        self.client.force_login(User.objects.create_user("staff", is_staff=True))
        response = self.client.get(url + "changes/")
        self.assertContains(response, "LEGACY_PRIVATE_NOTE")
        self.assertContains(response, '<div class="change-entry">', count=2)

    def test_guide_visibility_uses_database_instead_of_cached_relation(self):
        guide = GuideFactory(is_draft=False)
        chapter = ChapterFactory(guide=guide, body="Public original\n")
        Guide.objects.filter(pk=guide.pk).update(is_draft=True)
        # The chapter still has the previously published guide cached.
        self.assertFalse(chapter.guide.is_draft)
        chapter.body += "\nTEMPORARILY_PRIVATE_BODY\n"
        chapter.save()
        private_change = chapter.changes.latest("created")
        self.assertTrue(private_change.guide_is_draft)
        private_change.change_note = "TEMPORARILY_PRIVATE_NOTE"
        private_change.save()
        chapter.body = "Public original\n\nPublic addition\n"
        chapter.save()
        Guide.objects.filter(pk=guide.pk).update(is_draft=False)

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        self.assertNotContains(response, "TEMPORARILY_PRIVATE")
        self.assertContains(response, '<div class="change-entry">', count=1)

    def test_partial_save_does_not_publish_unsaved_draft_status(self):
        chapter = ChapterFactory(body="PARTIAL_SAVE_PRIVATE_BODY", is_draft=True)
        chapter.title = "Edited draft title"
        chapter.is_draft = False
        chapter.save(update_fields=["title"])
        self.assertTrue(chapter.changes.latest("created").is_draft)
        chapter.body = "Published body"
        chapter.save()

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        self.assertNotContains(response, "PARTIAL_SAVE_PRIVATE")
        self.assertContains(response, '<div class="change-entry">', count=1)

    def test_partial_save_does_not_record_unsaved_body(self):
        chapter = ChapterFactory(body="Published body")
        chapter.title = "Updated title"
        chapter.body = "UNSAVED_PRIVATE_BODY"
        chapter.save(update_fields=["title"])
        self.assertEqual(chapter.changes.latest("created").body, "Published body")

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        self.assertNotContains(response, "UNSAVED_PRIVATE")


class GuideSitemapTests(TransactionTestCase):
    def test_sitemap_excludes_drafts_and_chapters_in_draft_guides(self):
        public_guide = GuideFactory(is_draft=False)
        public_chapter = ChapterFactory(guide=public_guide, is_draft=False)
        draft_chapter = ChapterFactory(guide=public_guide, is_draft=True)
        draft_guide = GuideFactory(slug="unpublished-guide", is_draft=True)
        hidden_chapter = ChapterFactory(
            guide=draft_guide, slug="unpublished-guide-chapter", is_draft=False
        )
        hidden_draft = ChapterFactory(guide=draft_guide, is_draft=True)

        response = self.client.get("/sitemap.xml")
        self.assertContains(response, public_chapter.get_absolute_url())
        for chapter in (draft_chapter, hidden_chapter, hidden_draft):
            self.assertNotContains(response, chapter.get_absolute_url())
        self.assertNotContains(response, draft_guide.slug)

        draft_guide.is_draft = False
        draft_guide.save()
        response = self.client.get("/sitemap.xml")
        self.assertContains(response, hidden_chapter.get_absolute_url())
        self.assertNotContains(response, hidden_draft.get_absolute_url())
