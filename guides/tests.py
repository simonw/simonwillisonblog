import pytest
from django.contrib.auth.models import User
from pytest_django.asserts import assertContains, assertNotContains

from guides.factories import ChapterFactory, GuideFactory
from guides.models import Guide
from guides.views import _build_diff_html, _char_diff_html


class TestCharDiffHtml:
    def test_highlights_changed_chars(self):
        result = _char_diff_html("hello world", "hello World", is_remove=False)
        assert 'class="char-highlight"' in result
        assert "W" in result
        assert "hello " in result

    def test_remove_side(self):
        result = _char_diff_html("hello world", "hello World", is_remove=True)
        assert '<span class="char-highlight">w</span>' in result

    def test_insertion(self):
        result = _char_diff_html("abc", "abXc", is_remove=False)
        assert '<span class="char-highlight">X</span>' in result

    def test_deletion(self):
        result = _char_diff_html("abXc", "abc", is_remove=True)
        assert '<span class="char-highlight">X</span>' in result

    def test_escapes_html(self):
        result = _char_diff_html("<b>old</b>", "<b>new</b>", is_remove=False)
        assert "<b>" not in result
        assert "&lt;b&gt;" in result


class TestBuildDiffHtml:
    def test_basic(self):
        diff_lines = [
            "--- a\n",
            "+++ b\n",
            "@@ -1 +1 @@\n",
            "-old line\n",
            "+new line\n",
        ]
        result = _build_diff_html(diff_lines)
        assert 'class="diff-header"' in result
        assert 'class="diff-remove"' in result
        assert 'class="diff-add"' in result
        assert 'class="char-highlight"' in result

    def test_strips_double_newlines(self):
        diff_lines = [
            "--- a\n",
            "+++ b\n",
            "@@ -1 +1 @@\n",
            "-old\n",
            "+new\n",
        ]
        result = _build_diff_html(diff_lines)
        assert "\n\n" not in result

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
        assert 'class="char-highlight"' in result
        assert "removed line two" in result

    def test_returns_none_for_empty(self):
        assert _build_diff_html(None) is None
        assert _build_diff_html([]) is None


@pytest.mark.django_db
class TestH2Headings:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

    def test_h2_headings_extracts_headings(self):
        guide = GuideFactory(slug="h2-test")
        chapter = ChapterFactory(
            guide=guide,
            slug="ch",
            title="Test",
            body="## First heading\n\nSome text\n\n## Second heading\n\nMore text",
        )
        headings = chapter.h2_headings()
        assert len(headings) == 2
        assert headings[0]["id"] == "first-heading"
        assert headings[0]["title"] == "First heading"
        assert headings[1]["id"] == "second-heading"
        assert headings[1]["title"] == "Second heading"

    def test_h2_headings_empty_when_no_h2(self):
        guide = GuideFactory(slug="h2-empty")
        chapter = ChapterFactory(
            guide=guide,
            slug="ch",
            title="Test",
            body="Just a paragraph with no headings.",
        )
        assert chapter.h2_headings() == []

    def test_h2_headings_ignores_h3(self):
        guide = GuideFactory(slug="h2-h3")
        chapter = ChapterFactory(
            guide=guide,
            slug="ch",
            title="Test",
            body="## H2 heading\n\n### H3 heading\n\nText",
        )
        headings = chapter.h2_headings()
        assert len(headings) == 1
        assert headings[0]["title"] == "H2 heading"

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
        assert response.status_code == 200
        content = response.content.decode()
        assert "#sub-one" in content
        assert "#sub-two" in content
        assert "Sub one" in content
        assert "Sub two" in content


@pytest.mark.django_db
class TestChapterChangesCharHighlight:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

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
        assert response.status_code == 200
        content = response.content.decode()
        assert "char-highlight" in content
        assert "diff-add" in content
        assert "diff-remove" in content


@pytest.mark.django_db
class TestChapterChangesVisibility:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

    def test_public_history_excludes_draft_revisions(self, subtests):
        chapter = ChapterFactory(
            title="DRAFT_PRIVATE_TITLE",
            body="DRAFT_PRIVATE_BODY",
            is_draft=True,
        )
        chapter.changes.update(change_note="DRAFT_PRIVATE_NOTE")
        url = chapter.get_absolute_url()
        assert self.client.get(url).status_code == 404
        assert self.client.get(url + "changes/").status_code == 404

        chapter.title = "Published title"
        chapter.body = "Public first version\n"
        chapter.is_draft = False
        chapter.save()
        publication = chapter.changes.latest("created")
        chapter.body += "\nPublic second paragraph\n"
        chapter.save()

        reader = User.objects.create_user("reader")
        for authenticated in (False, True):
            with subtests.test(authenticated=authenticated):
                if authenticated:
                    self.client.force_login(reader)
                detail = self.client.get(url)
                assertContains(detail, "Public second paragraph")
                assert detail.context["chapter_num_changes"] == 2
                assert detail.context["chapter_created"] == publication.created
                history = self.client.get(url + "changes/")
                assertContains(history, '<div class="change-entry">', count=2)
                assertContains(history, "Public second paragraph")
                for response in (detail, history):
                    assertNotContains(response, "DRAFT_PRIVATE")

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
        assertNotContains(response, "INTERMEDIATE_PRIVATE")
        assertContains(response, "Public addition")
        assertContains(response, '<div class="change-entry">', count=2)

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
        assert self.client.get(url + "changes/").status_code == 404
        chapter.title = "Published title"
        chapter.body = "Public first version\n"
        chapter.save()
        guide.is_draft = False
        guide.save()

        response = self.client.get(url + "changes/")
        assertNotContains(response, "GUIDE_PRIVATE")
        assertContains(response, "No changes recorded for this chapter.")
        chapter.body += "\nPublic second paragraph\n"
        chapter.save()
        chapter.body += "\nPublic third paragraph\n"
        chapter.save()
        response = self.client.get(url + "changes/")
        assertNotContains(response, "GUIDE_PRIVATE")
        assertContains(response, "Public third paragraph")
        assertContains(response, '<div class="change-entry">', count=2)

    def test_staff_can_see_private_history_without_caching(self):
        chapter = ChapterFactory(body="STAFF_ONLY_BODY", is_draft=True)
        chapter.changes.update(change_note="STAFF_ONLY_NOTE")
        chapter.body = "Published body"
        chapter.is_draft = False
        chapter.save()
        self.client.force_login(User.objects.create_user("staff", is_staff=True))

        history = self.client.get(chapter.get_absolute_url() + "changes/")
        assertContains(history, "STAFF_ONLY_NOTE")
        assertContains(history, '<div class="change-entry">', count=2)
        detail = self.client.get(chapter.get_absolute_url())
        assert detail.context["chapter_num_changes"] == 2
        for response in (detail, history):
            assert "private" in response["Cache-Control"]
            assert "no-store" in response["Cache-Control"]

    def test_history_with_unknown_guide_visibility_is_staff_only(self):
        chapter = ChapterFactory(body="LEGACY_PRIVATE_BODY")
        chapter.changes.update(guide_is_draft=None, change_note="LEGACY_PRIVATE_NOTE")
        url = chapter.get_absolute_url()
        response = self.client.get(url + "changes/")
        assertContains(response, "No changes recorded for this chapter.")
        assertNotContains(response, "LEGACY_PRIVATE_NOTE")
        assert self.client.get(url).context["chapter_num_changes"] == 0

        chapter.body = "Published body"
        chapter.save()
        response = self.client.get(url + "changes/")
        assertNotContains(response, "LEGACY_PRIVATE")
        assertContains(response, '<div class="change-entry">', count=1)
        self.client.force_login(User.objects.create_user("staff", is_staff=True))
        response = self.client.get(url + "changes/")
        assertContains(response, "LEGACY_PRIVATE_NOTE")
        assertContains(response, '<div class="change-entry">', count=2)

    def test_guide_visibility_uses_database_instead_of_cached_relation(self):
        guide = GuideFactory(is_draft=False)
        chapter = ChapterFactory(guide=guide, body="Public original\n")
        Guide.objects.filter(pk=guide.pk).update(is_draft=True)
        # The chapter still has the previously published guide cached.
        assert not chapter.guide.is_draft
        chapter.body += "\nTEMPORARILY_PRIVATE_BODY\n"
        chapter.save()
        private_change = chapter.changes.latest("created")
        assert private_change.guide_is_draft
        private_change.change_note = "TEMPORARILY_PRIVATE_NOTE"
        private_change.save()
        chapter.body = "Public original\n\nPublic addition\n"
        chapter.save()
        Guide.objects.filter(pk=guide.pk).update(is_draft=False)

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        assertNotContains(response, "TEMPORARILY_PRIVATE")
        assertContains(response, '<div class="change-entry">', count=1)

    def test_partial_save_does_not_publish_unsaved_draft_status(self):
        chapter = ChapterFactory(body="PARTIAL_SAVE_PRIVATE_BODY", is_draft=True)
        chapter.title = "Edited draft title"
        chapter.is_draft = False
        chapter.save(update_fields=["title"])
        assert chapter.changes.latest("created").is_draft
        chapter.body = "Published body"
        chapter.save()

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        assertNotContains(response, "PARTIAL_SAVE_PRIVATE")
        assertContains(response, '<div class="change-entry">', count=1)

    def test_partial_save_does_not_record_unsaved_body(self):
        chapter = ChapterFactory(body="Published body")
        chapter.title = "Updated title"
        chapter.body = "UNSAVED_PRIVATE_BODY"
        chapter.save(update_fields=["title"])
        assert chapter.changes.latest("created").body == "Published body"

        response = self.client.get(chapter.get_absolute_url() + "changes/")
        assertNotContains(response, "UNSAVED_PRIVATE")


@pytest.mark.django_db
class TestGuideSitemap:
    @pytest.fixture(autouse=True)
    def setup(self, client):
        self.client = client

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
        assertContains(response, public_chapter.get_absolute_url())
        for chapter in (draft_chapter, hidden_chapter, hidden_draft):
            assertNotContains(response, chapter.get_absolute_url())
        assertNotContains(response, draft_guide.slug)

        draft_guide.is_draft = False
        draft_guide.save()
        response = self.client.get("/sitemap.xml")
        assertContains(response, hidden_chapter.get_absolute_url())
        assertNotContains(response, hidden_draft.get_absolute_url())
