from unittest.mock import patch
from xml.etree import ElementTree

from django.contrib.auth.models import User, Permission
from django.test import TestCase
from django.urls import reverse

from .factories import NoteFactory, BlogmarkFactory, EntryFactory
from .models import Entry, Tag


class ReplacementAdminTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "replacement-admin", "a@example.com", "pw"
        )
        self.client.force_login(self.user)

    def convert_url(self, source):
        return f"/admin/blog/{source._meta.model_name}/{source.pk}/convert-to-entry/"

    def live_url(self, entry):
        return f"/admin/blog/entry/{entry.pk}/go-live-with-replacement/"

    def convert(self, source):
        response = self.client.post(self.convert_url(source))
        self.assertEqual(response.status_code, 302)
        entry = Entry.objects.get()
        self.assertEqual(
            response.url, reverse("admin:blog_entry_change", args=[entry.pk])
        )
        return entry

    def test_note_conversion_and_go_live_preserve_url_and_data(self):
        source = NoteFactory(
            title="My note",
            body='Hello **world**\n\n<img src="x?a=1&b=2"><br>&nbsp;',
            metadata={"foo": "bar"},
            card_image="image.jpg",
        )
        tag = Tag.objects.create(tag="replacement-test")
        source.tags.add(tag)
        original_url = source.get_absolute_url()
        entry = self.convert(source)
        self.assertTrue(entry.is_draft)
        self.assertEqual(entry.slug, source.slug + "-replacement-entry")
        self.assertEqual(entry.created, source.created)
        self.assertEqual(entry.title, source.title)
        self.assertEqual(entry.metadata, source.metadata)
        self.assertEqual(entry.card_image, source.card_image)
        self.assertEqual(list(entry.tags.all()), [tag])
        ElementTree.fromstring("<entry>" + entry.body + "</entry>")
        self.assertIn("<strong>world</strong>", entry.body)
        source.refresh_from_db()
        self.assertFalse(source.is_draft)
        self.assertContains(
            self.client.get(reverse("admin:blog_entry_change", args=[entry.pk])),
            "Go live with replacement",
        )
        response = self.client.post(self.live_url(entry))
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        source.refresh_from_db()
        self.assertFalse(entry.is_draft)
        self.assertTrue(source.is_draft)
        self.assertEqual(entry.get_absolute_url(), original_url)
        self.assertEqual(source.slug, entry.slug + "-replaced")
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 400)

    def test_blogmark_conversion_preserves_link_and_via(self):
        source = BlogmarkFactory(
            title="",
            link_title="A & B",
            link_url="https://example.com/?a=1&b=2",
            commentary="**Bold**",
            use_markdown=True,
            via_url="https://via.example/",
            via_title="Via site",
        )
        entry = self.convert(source)
        self.assertEqual(entry.title, source.link_title)
        root = ElementTree.fromstring("<entry>" + entry.body + "</entry>")
        self.assertEqual(root.find(".//a").attrib["href"], source.link_url)
        self.assertIn("<strong>Bold</strong>", entry.body)
        self.assertIn("Via site", entry.body)
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 302)
        source.refresh_from_db()
        self.assertTrue(source.is_draft)

    def test_plain_text_blogmark_is_not_interpreted_as_markdown_or_html(self):
        entry = self.convert(
            BlogmarkFactory(commentary="**plain** <thing> & text", use_markdown=False)
        )
        self.assertIn("**plain** &lt;thing&gt; &amp; text", entry.body)

    def test_conversion_is_idempotent_and_controls_are_visible(self):
        source = NoteFactory(body="A note")
        self.assertContains(
            self.client.get(reverse("admin:blog_note_change", args=[source.pk])),
            "Convert to blog entry",
        )
        entry = self.convert(source)
        self.assertEqual(
            self.client.post(self.convert_url(source)).url,
            reverse("admin:blog_entry_change", args=[entry.pk]),
        )
        self.assertEqual(Entry.objects.count(), 1)
        self.assertTrue(entry.title)

    def test_get_cannot_mutate(self):
        source = NoteFactory(body="Note")
        self.assertEqual(self.client.get(self.convert_url(source)).status_code, 405)
        self.assertFalse(Entry.objects.exists())
        entry = self.convert(source)
        self.assertEqual(self.client.get(self.live_url(entry)).status_code, 405)

    def test_permissions_and_csrf(self):
        source = NoteFactory(body="Note")
        self.user.is_superuser = False
        self.user.save()
        self.assertEqual(self.client.post(self.convert_url(source)).status_code, 403)
        self.user.user_permissions.add(Permission.objects.get(codename="change_note"))
        self.assertEqual(self.client.post(self.convert_url(source)).status_code, 403)
        self.user.is_superuser = True
        self.user.save()
        entry = self.convert(source)
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(codename="change_entry"))
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 403)
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(client.post(self.live_url(entry)).status_code, 403)

    def test_conflicts_and_changed_source_are_rejected(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        conflict = EntryFactory(slug=source.slug, created=source.created)
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 400)
        conflict.delete()
        source.slug = "changed-slug"
        source.save()
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 400)
        entry.refresh_from_db()
        self.assertTrue(entry.is_draft)

    def test_transaction_rolls_back_source_when_entry_save_fails(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        old_slug = source.slug
        with patch.object(Entry, "save", side_effect=RuntimeError("save failed")):
            with self.assertRaises(RuntimeError):
                self.client.post(self.live_url(entry))
        source.refresh_from_db()
        self.assertFalse(source.is_draft)
        self.assertEqual(source.slug, old_slug)

    def test_64_character_slug_can_be_converted(self):
        source = NoteFactory(body="Note", slug="a" * 64)
        entry = self.convert(source)
        self.assertEqual(len(entry.slug), 82)
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 302)

    def test_unrelated_entry_cannot_go_live_as_replacement(self):
        entry = EntryFactory(is_draft=True)
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 400)

    def test_conversion_conflict_does_not_create_an_entry(self):
        source = NoteFactory(body="Note")
        NoteFactory(slug=source.slug + "-replacement-entry", created=source.created)
        self.assertEqual(self.client.post(self.convert_url(source)).status_code, 400)
        self.assertFalse(Entry.objects.exists())

    def test_retired_slug_conflict_leaves_both_items_unchanged(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        NoteFactory(slug=source.slug + "-replaced", created=source.created)
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 400)
        entry.refresh_from_db()
        source.refresh_from_db()
        self.assertTrue(entry.is_draft)
        self.assertFalse(source.is_draft)

    def test_invalid_saved_xhtml_cannot_be_published(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        Entry.objects.filter(pk=entry.pk).update(body="<p>unclosed")
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 400)
        source.refresh_from_db()
        self.assertFalse(source.is_draft)

    def test_original_url_serves_entry_after_publication(self):
        source = BlogmarkFactory(commentary="Original content")
        original_url = source.get_absolute_url()
        self.assertTemplateUsed(self.client.get(original_url), "blogmark.html")
        entry = self.convert(source)
        entry.body = "<p>Edited replacement content</p>"
        entry.save()
        self.client.post(self.live_url(entry))
        response = self.client.get(original_url)
        self.assertTemplateUsed(response, "entry.html")
        self.assertContains(response, "Edited replacement content")

    def assert_can_delete_replaced_source(self, source):
        original_url = source.get_absolute_url()
        entry = self.convert(source)
        self.assertEqual(self.client.post(self.live_url(entry)).status_code, 302)
        model_name = source._meta.model_name
        delete_url = reverse(f"admin:blog_{model_name}_delete", args=[source.pk])
        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["protected"], [])

        response = self.client.post(delete_url, {"post": "yes"})
        self.assertRedirects(response, reverse(f"admin:blog_{model_name}_changelist"))
        self.assertFalse(type(source).objects.filter(pk=source.pk).exists())
        entry.refresh_from_db()
        self.assertIsNone(getattr(entry, f"replacement_{model_name}_id"))
        self.assertFalse(entry.is_draft)
        self.assertEqual(entry.get_absolute_url(), original_url)
        response = self.client.get(original_url)
        self.assertTemplateUsed(response, "entry.html")
        self.assertContains(response, "Original content")

    def test_delete_replaced_note_preserves_entry(self):
        self.assert_can_delete_replaced_source(NoteFactory(body="Original content"))

    def test_delete_replaced_blogmark_preserves_entry(self):
        self.assert_can_delete_replaced_source(
            BlogmarkFactory(commentary="Original content")
        )
