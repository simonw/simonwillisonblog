from html import escape

from django.db import models
from django.utils import timezone
from django.utils.safestring import mark_safe
from markdown import markdown

from blog.models import BaseModel, Tag, Series


def _markdown_copy_formatter(source, language, css_class, options, md, **kwargs):
    return f"<div><markdown-copy><textarea>{escape(source)}</textarea></markdown-copy></div>"


_CUSTOM_FENCES = [
    {
        "name": "markdown-copy",
        "class": "",
        "format": _markdown_copy_formatter,
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
        is_new = self.pk is None
        if not is_new:
            try:
                old = Chapter.objects.get(pk=self.pk)
            except Chapter.DoesNotExist:
                old = None
            should_record = old and (
                old.title != self.title
                or old.body != self.body
                or old.is_draft != self.is_draft
            )
        else:
            should_record = True
        super().save(**kwargs)
        if should_record:
            ChapterChange.objects.create(
                chapter=self,
                created=self.created if is_new else timezone.now(),
                title=self.title,
                body=self.body,
                is_draft=self.is_draft,
            )

    def body_rendered(self):
        return mark_safe(
            markdown(
                self.body,
                extensions=["pymdownx.superfences", "pymdownx.highlight", "toc"],
                extension_configs={
                    "pymdownx.superfences": {
                        "custom_fences": _CUSTOM_FENCES,
                    },
                    "pymdownx.highlight": {
                        "guess_lang": False,
                        "css_class": "codehilite",
                        "use_pygments": True,
                    },
                },
            )
        )

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
    is_notable = models.BooleanField(default=False)
    change_note = models.TextField(default="", blank=True)

    def __str__(self):
        return f"Change to {self.chapter.title} at {self.created.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        ordering = ("created",)
