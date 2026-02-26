from blog.feeds import Base
from .models import Chapter, ChapterChange


class GuideFeedItem:
    """Wrapper to give a unified interface for new chapters and notable changes."""

    def __init__(self, chapter, created, change_note=""):
        self.chapter = chapter
        self.created = created
        self.change_note = change_note
        self.tags = chapter.tags

    def get_absolute_url(self):
        return self.chapter.get_absolute_url()

    def body_rendered(self):
        return self.chapter.body_rendered()


class GuideFeed(Base):
    ga_source = "guide"
    description_template = "feeds/guide.html"

    def __init__(self, guide):
        self.guide = guide
        self.title = "Simon Willison's Weblog: {}".format(guide.title)

    def items(self):
        chapters = list(
            self.guide.chapters.filter(is_draft=False)
            .select_related("guide")
            .prefetch_related("tags")
        )
        items = []
        for ch in chapters:
            items.append(GuideFeedItem(ch, ch.created))

        notable_changes = list(
            ChapterChange.objects.filter(
                chapter__guide=self.guide,
                chapter__is_draft=False,
                is_notable=True,
            ).select_related("chapter", "chapter__guide")
            .prefetch_related("chapter__tags")
        )
        for change in notable_changes:
            items.append(
                GuideFeedItem(
                    change.chapter,
                    change.created,
                    change_note=change.change_note,
                )
            )

        items.sort(key=lambda x: x.created, reverse=True)
        return items[:15]

    def item_title(self, item):
        if item.change_note:
            return "{} - {}".format(item.chapter.title, item.change_note)
        return item.chapter.title
