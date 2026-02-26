import json

from django.contrib.auth.models import User
from django.test import TransactionTestCase

from blog.factories import EntryFactory
from blog.models import Tag
from guides.factories import ChapterFactory, GuideFactory, GuideSectionFactory
from guides.models import ChapterChange


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
        guide = GuideFactory(slug="g5", description="")
        ChapterFactory(guide=guide, title="Xalpha", slug="second", order=2)
        ChapterFactory(guide=guide, title="Xbravo", slug="first", order=1)
        ChapterFactory(guide=guide, title="Xcharlie", slug="third", order=3)
        response = self.client.get("/guides/g5/")
        content = response.content.decode()
        first_pos = content.index("Xbravo")
        second_pos = content.index("Xalpha")
        third_pos = content.index("Xcharlie")
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
        from guides.models import Chapter
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


class GuideSectionTests(TransactionTestCase):
    def test_create_section(self):
        guide = GuideFactory(slug="sec-guide")
        section = GuideSectionFactory(guide=guide, title="Basics", slug="basics", order=1)
        self.assertEqual(section.guide, guide)
        self.assertEqual(section.title, "Basics")
        self.assertEqual(section.slug, "basics")
        self.assertEqual(section.order, 1)
        self.assertEqual(str(section), "Basics")

    def test_section_unique_together(self):
        guide = GuideFactory(slug="sec-guide2")
        GuideSectionFactory(guide=guide, slug="basics", order=1)
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            GuideSectionFactory(guide=guide, slug="basics", order=2)

    def test_section_ordering(self):
        guide = GuideFactory(slug="sec-guide3")
        GuideSectionFactory(guide=guide, title="Second", slug="second", order=2)
        GuideSectionFactory(guide=guide, title="First", slug="first", order=1)
        sections = list(guide.sections.all())
        self.assertEqual(sections[0].title, "First")
        self.assertEqual(sections[1].title, "Second")

    def test_chapter_section_fk(self):
        guide = GuideFactory(slug="sec-fk")
        section = GuideSectionFactory(guide=guide, slug="basics", order=1)
        chapter = ChapterFactory(
            guide=guide, title="Ch In Section", slug="ch-in-sec", order=0, section=section
        )
        self.assertEqual(chapter.section, section)
        self.assertIn(chapter, list(section.chapters.all()))

    def test_chapter_section_nullable(self):
        guide = GuideFactory(slug="sec-null")
        chapter = ChapterFactory(guide=guide, slug="standalone", order=0)
        self.assertIsNone(chapter.section)

    def test_chapter_section_set_null_on_delete(self):
        guide = GuideFactory(slug="sec-del")
        section = GuideSectionFactory(guide=guide, slug="temp", order=1)
        chapter = ChapterFactory(
            guide=guide, slug="orphan", order=0, section=section
        )
        section.delete()
        chapter.refresh_from_db()
        self.assertIsNone(chapter.section)

    def test_build_guide_toc_mixed(self):
        from guides.views import build_guide_toc

        guide = GuideFactory(slug="toc-mixed")
        standalone = ChapterFactory(
            guide=guide, title="Intro", slug="intro", order=0
        )
        section = GuideSectionFactory(
            guide=guide, title="Basics", slug="basics", order=1
        )
        ch_in_sec1 = ChapterFactory(
            guide=guide, title="Glossary", slug="glossary", order=0, section=section
        )
        ch_in_sec2 = ChapterFactory(
            guide=guide, title="Install", slug="install", order=1, section=section
        )

        toc = build_guide_toc(guide)
        self.assertEqual(len(toc), 2)
        self.assertEqual(toc[0]["type"], "chapter")
        self.assertEqual(toc[0]["chapter"], standalone)
        self.assertEqual(toc[1]["type"], "section")
        self.assertEqual(toc[1]["section"], section)
        self.assertEqual(toc[1]["chapters"], [ch_in_sec1, ch_in_sec2])

    def test_build_guide_toc_hides_empty_sections(self):
        from guides.views import build_guide_toc

        guide = GuideFactory(slug="toc-empty")
        GuideSectionFactory(guide=guide, title="Empty", slug="empty", order=1)
        ChapterFactory(guide=guide, title="Solo", slug="solo", order=0)

        toc = build_guide_toc(guide)
        self.assertEqual(len(toc), 1)
        self.assertEqual(toc[0]["type"], "chapter")

    def test_build_guide_toc_hides_draft_chapters(self):
        from guides.views import build_guide_toc

        guide = GuideFactory(slug="toc-drafts")
        section = GuideSectionFactory(guide=guide, slug="sec", order=1)
        ChapterFactory(
            guide=guide, slug="draft-ch", order=0, section=section, is_draft=True
        )
        # Section has only draft chapters, so should be hidden
        toc = build_guide_toc(guide)
        self.assertEqual(len(toc), 0)

    def test_flatten_toc(self):
        from guides.views import build_guide_toc, flatten_toc

        guide = GuideFactory(slug="toc-flat")
        ch1 = ChapterFactory(guide=guide, title="Intro", slug="intro", order=0)
        section = GuideSectionFactory(guide=guide, slug="basics", order=1)
        ch2 = ChapterFactory(
            guide=guide, slug="glossary", order=0, section=section
        )
        ch3 = ChapterFactory(
            guide=guide, slug="install", order=1, section=section
        )

        toc = build_guide_toc(guide)
        flat = flatten_toc(toc)
        self.assertEqual(flat, [ch1, ch2, ch3])

    def test_guide_detail_shows_section_headings(self):
        guide = GuideFactory(slug="view-sec")
        ChapterFactory(guide=guide, title="Intro Ch", slug="intro", order=0)
        section = GuideSectionFactory(
            guide=guide, title="Basics Section", slug="basics", order=1
        )
        ChapterFactory(
            guide=guide, title="Ch In Basics", slug="ch-basics", order=0, section=section
        )
        response = self.client.get("/guides/view-sec/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Intro Ch")
        self.assertContains(response, "Basics Section")
        self.assertContains(response, "Ch In Basics")
        # Section title should be bold/strong, not a link
        self.assertContains(response, "<strong>Basics Section</strong>")

    def test_guide_detail_hides_empty_section(self):
        guide = GuideFactory(slug="view-empty-sec")
        ChapterFactory(guide=guide, title="Solo Ch", slug="solo", order=0)
        GuideSectionFactory(guide=guide, title="Ghost Section", slug="ghost", order=1)
        response = self.client.get("/guides/view-empty-sec/")
        self.assertContains(response, "Solo Ch")
        self.assertNotContains(response, "Ghost Section")

    def test_chapter_sidebar_shows_section_headings(self):
        guide = GuideFactory(slug="sidebar-sec")
        section = GuideSectionFactory(
            guide=guide, title="My Section", slug="my-sec", order=1
        )
        ch1 = ChapterFactory(
            guide=guide, title="Standalone Ch", slug="standalone", order=0
        )
        ch2 = ChapterFactory(
            guide=guide, title="Sec Ch", slug="sec-ch", order=0, section=section
        )
        response = self.client.get("/guides/sidebar-sec/standalone/")
        self.assertEqual(response.status_code, 200)
        # Sidebar should show the section heading
        self.assertContains(response, "<strong>My Section</strong>")
        self.assertContains(response, "Standalone Ch")
        self.assertContains(response, "Sec Ch")

    def test_chapter_prev_next_ignores_sections(self):
        guide = GuideFactory(slug="nav-sec")
        section = GuideSectionFactory(guide=guide, slug="sec", order=1)
        ch1 = ChapterFactory(
            guide=guide, title="First", slug="first", order=0
        )
        ch2 = ChapterFactory(
            guide=guide, title="Second", slug="second", order=0, section=section
        )
        ch3 = ChapterFactory(
            guide=guide, title="Third", slug="third", order=1, section=section
        )
        # First chapter: next should be Second (in section), flat walk
        response = self.client.get("/guides/nav-sec/first/")
        self.assertContains(response, "Second")
        # Second chapter: prev=First, next=Third
        response = self.client.get("/guides/nav-sec/second/")
        self.assertContains(response, "First")
        self.assertContains(response, "Third")
        # Third chapter: prev=Second, no next
        response = self.client.get("/guides/nav-sec/third/")
        self.assertContains(response, "Second")


class BulkTagChapterApiTests(TransactionTestCase):
    """Tests for the api_add_tag endpoint with chapters."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="staff", password="password", is_staff=True
        )
        self.client.login(username="staff", password="password")

    def test_api_add_tag_to_chapter(self):
        """The api/add-tag/ endpoint should support tagging chapters."""
        guide = GuideFactory()
        chapter = ChapterFactory(guide=guide, title="Test Chapter")
        response = self.client.post(
            "/api/add-tag/",
            {"content_type": "chapter", "object_id": chapter.pk, "tag": "testtag"},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["tag"], "testtag")
        # Verify the tag was actually added
        chapter.refresh_from_db()
        self.assertEqual(list(chapter.tags.values_list("tag", flat=True)), ["testtag"])

    def test_api_add_tag_to_chapter_creates_new_tag(self):
        """Tagging a chapter with a new tag should create that tag."""
        guide = GuideFactory()
        chapter = ChapterFactory(guide=guide)
        self.assertFalse(Tag.objects.filter(tag="brandnewtag").exists())
        response = self.client.post(
            "/api/add-tag/",
            {"content_type": "chapter", "object_id": chapter.pk, "tag": "brandnewtag"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Tag.objects.filter(tag="brandnewtag").exists())
