import re
from html import escape

from django.db import models
from django.utils import timezone
from django.utils.safestring import mark_safe
from markdown import markdown

from blog.models import BaseModel, Tag, Series


def _markdown_copy_formatter(source, language, css_class, options, md, **kwargs):
    return f"<div><markdown-copy><textarea>{escape(source)}</textarea></markdown-copy></div>"


def _markdown_copy_feed_formatter(source, language, css_class, options, md, **kwargs):
    return f"<pre>{escape(source)}</pre>"


_CUSTOM_FENCES = [
    {
        "name": "markdown-copy",
        "class": "",
        "format": _markdown_copy_formatter,
    }
]

_CUSTOM_FENCES_FEED = [
    {
        "name": "markdown-copy",
        "class": "",
        "format": _markdown_copy_feed_formatter,
    }
]


class Guide(models.Model):
    created = models.DateTimeField(default=timezone.now)
    updated = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    is_draft = models.BooleanField(default=False)

    def get_absolute_url(self):
        return "/guides/{}/".format(self.slug)

    def edit_url(self):
        return "/admin/guides/guide/%d/" % self.id

    def __str__(self):
        return self.title

    class Meta:
        ordering = ("title",)


class GuideSection(models.Model):
    guide = models.ForeignKey(Guide, related_name="sections", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ("order",)
        unique_together = (("guide", "slug"),)

    def __str__(self):
        return self.title


class Chapter(BaseModel):
    guide = models.ForeignKey(Guide, related_name="chapters", on_delete=models.CASCADE)
    section = models.ForeignKey(
        GuideSection,
        related_name="chapters",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="guides_chapter_set")
    series = models.ForeignKey(
        Series,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name="guides_chapter_set",
    )
    updated = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=255)
    body = models.TextField()
    order = models.IntegerField(default=0)
    is_unlisted = models.BooleanField(default=False)
    is_chapter = True

    def save(self, **kwargs):
        old = Chapter.objects.filter(pk=self.pk).first() if self.pk else None
        super().save(**kwargs)
        # Snapshot persisted fields, including the guide's current visibility.
        # The instance may have unsaved fields or a stale cached guide.
        saved = Chapter.objects.select_related("guide").get(pk=self.pk)
        should_record = old is None or any(
            getattr(old, field) != getattr(saved, field)
            for field in ("title", "body", "is_draft", "guide_id")
        )
        if should_record:
            ChapterChange.objects.create(
                chapter=saved,
                created=saved.created if old is None else timezone.now(),
                title=saved.title,
                body=saved.body,
                is_draft=saved.is_draft,
                guide_is_draft=saved.guide.is_draft,
            )

    def _render_body(self, custom_fences):
        return mark_safe(
            markdown(
                self.body,
                extensions=["pymdownx.superfences", "pymdownx.highlight", "toc"],
                extension_configs={
                    "pymdownx.superfences": {
                        "custom_fences": custom_fences,
                    },
                    "pymdownx.highlight": {
                        "guess_lang": False,
                        "css_class": "codehilite",
                        "use_pygments": True,
                    },
                },
            )
        )

    def body_rendered(self):
        return self._render_body(_CUSTOM_FENCES)

    def body_rendered_for_feed(self):
        return self._render_body(_CUSTOM_FENCES_FEED)

    def h2_headings(self):
        html = str(self.body_rendered())
        return [
            {"id": m.group(1), "title": re.sub(r"<[^>]+>", "", m.group(2))}
            for m in re.finditer(r'<h2\s+id="([^"]+)">(.*?)</h2>', html)
        ]

    def multi_paragraph(self):
        return str(self.body_rendered()).count("<p") > 3

    def get_absolute_url(self):
        return "/guides/{}/{}/".format(self.guide.slug, self.slug)

    def edit_url(self):
        return "/admin/guides/chapter/%d/" % self.id

    def index_components(self):
        return {
            "A": self.title,
            "C": self.body,
            "B": " ".join(self.tags.values_list("tag", flat=True)),
        }

    def __str__(self):
        return self.title

    class Meta(BaseModel.Meta):
        ordering = ("order", "created")
        unique_together = (("guide", "slug"),)


class ChapterChange(models.Model):
    chapter = models.ForeignKey(
        Chapter, related_name="changes", on_delete=models.CASCADE
    )
    created = models.DateTimeField()
    title = models.CharField(max_length=255)
    body = models.TextField()
    is_draft = models.BooleanField()
    # NULL means historical guide visibility is unknown: keep these private.
    guide_is_draft = models.BooleanField(null=True)
    is_notable = models.BooleanField(default=False)
    change_note = models.TextField(default="", blank=True)

    def __str__(self):
        return f"Change to {self.chapter.title} at {self.created.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ("created",)
