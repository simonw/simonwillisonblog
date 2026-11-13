from unittest.mock import patch
from xml.etree import ElementTree

import pytest
from django.contrib.auth.models import Permission, User
from django.urls import reverse
from pytest_django.asserts import assertContains, assertRedirects, assertTemplateUsed

from .factories import BlogmarkFactory, EntryFactory, NoteFactory
from .models import Entry, Tag


@pytest.mark.django_db
class TestReplacementAdmin:
    @pytest.fixture(autouse=True)
    def setup(self, client, db):
        self.client = client
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
        assert response.status_code == 302
        entry = Entry.objects.get()
        assert response.url == reverse("admin:blog_entry_change", args=[entry.pk])
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
        assert entry.is_draft
        assert entry.slug == source.slug + "-replacement-entry"
        assert entry.created == source.created
        assert entry.title == source.title
        assert entry.metadata == source.metadata
        assert entry.card_image == source.card_image
        assert list(entry.tags.all()) == [tag]
        ElementTree.fromstring("<entry>" + entry.body + "</entry>")
        assert "<strong>world</strong>" in entry.body
        source.refresh_from_db()
        assert not source.is_draft
        assertContains(
            self.client.get(reverse("admin:blog_entry_change", args=[entry.pk])),
            "Go live with replacement",
        )
        response = self.client.post(self.live_url(entry))
        assert response.status_code == 302
        entry.refresh_from_db()
        source.refresh_from_db()
        assert not entry.is_draft
        assert source.is_draft
        assert entry.get_absolute_url() == original_url
        assert source.slug == entry.slug + "-replaced"
        assert self.client.post(self.live_url(entry)).status_code == 400

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
        assert entry.title == source.link_title
        root = ElementTree.fromstring("<entry>" + entry.body + "</entry>")
        assert root.find(".//a").attrib["href"] == source.link_url
        assert "<strong>Bold</strong>" in entry.body
        assert "Via site" in entry.body
        assert self.client.post(self.live_url(entry)).status_code == 302
        source.refresh_from_db()
        assert source.is_draft

    def test_plain_text_blogmark_is_not_interpreted_as_markdown_or_html(self):
        entry = self.convert(
            BlogmarkFactory(commentary="**plain** <thing> & text", use_markdown=False)
        )
        assert "**plain** &lt;thing&gt; &amp; text" in entry.body

    def test_conversion_is_idempotent_and_controls_are_visible(self):
        source = NoteFactory(body="A note")
        assertContains(
            self.client.get(reverse("admin:blog_note_change", args=[source.pk])),
            "Convert to blog entry",
        )
        entry = self.convert(source)
        assert self.client.post(self.convert_url(source)).url == reverse(
            "admin:blog_entry_change", args=[entry.pk]
        )
        assert Entry.objects.count() == 1
        assert entry.title

    def test_get_cannot_mutate(self):
        source = NoteFactory(body="Note")
        assert self.client.get(self.convert_url(source)).status_code == 405
        assert not Entry.objects.exists()
        entry = self.convert(source)
        assert self.client.get(self.live_url(entry)).status_code == 405

    def test_permissions_and_csrf(self):
        source = NoteFactory(body="Note")
        self.user.is_superuser = False
        self.user.save()
        assert self.client.post(self.convert_url(source)).status_code == 403
        self.user.user_permissions.add(Permission.objects.get(codename="change_note"))
        assert self.client.post(self.convert_url(source)).status_code == 403
        self.user.is_superuser = True
        self.user.save()
        entry = self.convert(source)
        self.user.is_superuser = False
        self.user.save()
        self.user.user_permissions.clear()
        self.user.user_permissions.add(Permission.objects.get(codename="change_entry"))
        assert self.client.post(self.live_url(entry)).status_code == 403
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        assert client.post(self.live_url(entry)).status_code == 403

    def test_conflicts_and_changed_source_are_rejected(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        conflict = EntryFactory(slug=source.slug, created=source.created)
        assert self.client.post(self.live_url(entry)).status_code == 400
        conflict.delete()
        source.slug = "changed-slug"
        source.save()
        assert self.client.post(self.live_url(entry)).status_code == 400
        entry.refresh_from_db()
        assert entry.is_draft

    def test_transaction_rolls_back_source_when_entry_save_fails(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        old_slug = source.slug
        with patch.object(Entry, "save", side_effect=RuntimeError("save failed")):
            with pytest.raises(RuntimeError):
                self.client.post(self.live_url(entry))
        source.refresh_from_db()
        assert not source.is_draft
        assert source.slug == old_slug

    def test_64_character_slug_can_be_converted(self):
        source = NoteFactory(body="Note", slug="a" * 64)
        entry = self.convert(source)
        assert len(entry.slug) == 82
        assert self.client.post(self.live_url(entry)).status_code == 302

    def test_unrelated_entry_cannot_go_live_as_replacement(self):
        entry = EntryFactory(is_draft=True)
        assert self.client.post(self.live_url(entry)).status_code == 400

    def test_conversion_conflict_does_not_create_an_entry(self):
        source = NoteFactory(body="Note")
        NoteFactory(slug=source.slug + "-replacement-entry", created=source.created)
        assert self.client.post(self.convert_url(source)).status_code == 400
        assert not Entry.objects.exists()

    def test_retired_slug_conflict_leaves_both_items_unchanged(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        NoteFactory(slug=source.slug + "-replaced", created=source.created)
        assert self.client.post(self.live_url(entry)).status_code == 400
        entry.refresh_from_db()
        source.refresh_from_db()
        assert entry.is_draft
        assert not source.is_draft

    def test_invalid_saved_xhtml_cannot_be_published(self):
        source = NoteFactory(body="Note")
        entry = self.convert(source)
        Entry.objects.filter(pk=entry.pk).update(body="<p>unclosed")
        assert self.client.post(self.live_url(entry)).status_code == 400
        source.refresh_from_db()
        assert not source.is_draft

    def test_original_url_serves_entry_after_publication(self):
        source = BlogmarkFactory(commentary="Original content")
        original_url = source.get_absolute_url()
        assertTemplateUsed(self.client.get(original_url), "blogmark.html")
        entry = self.convert(source)
        entry.body = "<p>Edited replacement content</p>"
        entry.save()
        self.client.post(self.live_url(entry))
        response = self.client.get(original_url)
        assertTemplateUsed(response, "entry.html")
        assertContains(response, "Edited replacement content")

    def assert_can_delete_replaced_source(self, source):
        original_url = source.get_absolute_url()
        entry = self.convert(source)
        assert self.client.post(self.live_url(entry)).status_code == 302
        model_name = source._meta.model_name
        delete_url = reverse(f"admin:blog_{model_name}_delete", args=[source.pk])
        response = self.client.get(delete_url)
        assert response.status_code == 200
        assert response.context["protected"] == []

        response = self.client.post(delete_url, {"post": "yes"})
        assertRedirects(response, reverse(f"admin:blog_{model_name}_changelist"))
        assert not type(source).objects.filter(pk=source.pk).exists()
        entry.refresh_from_db()
        assert getattr(entry, f"replacement_{model_name}_id") is None
        assert not entry.is_draft
        assert entry.get_absolute_url() == original_url
        response = self.client.get(original_url)
        assertTemplateUsed(response, "entry.html")
        assertContains(response, "Original content")

    def test_delete_replaced_note_preserves_entry(self):
        self.assert_can_delete_replaced_source(NoteFactory(body="Original content"))

    def test_delete_replaced_blogmark_preserves_entry(self):
        self.assert_can_delete_replaced_source(
            BlogmarkFactory(commentary="Original content")
        )
