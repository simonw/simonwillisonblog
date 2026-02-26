from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed
from markdown import markdown

from .models import ChapterChange


class GuideFeed(Feed):
    feed_type = Atom1Feed
    author_name = "Simon Willison"

    def __init__(self, guide):
        self.guide = guide

    def title(self):
        return "Simon Willison's Weblog: {}".format(self.guide.title)

    def link(self):
        return self.guide.get_absolute_url()

    def __call__(self, request, *args, **kwargs):
        response = super().__call__(request, *args, **kwargs)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Max-Age"] = "1000"
        cache_minutes = 10
        response["Cache-Control"] = "s-maxage=%d" % (cache_minutes * 60)
        return response

    def items(self):
        # Get the first change for each non-draft chapter (= new chapter)
        # and all notable changes (= significant updates)
        first_change_ids = (
            ChapterChange.objects.filter(
                chapter__guide=self.guide,
                chapter__is_draft=False,
                is_draft=False,
            )
            .order_by("chapter_id", "created")
            .distinct("chapter_id")
            .values_list("id", flat=True)
        )
        notable_change_ids = (
            ChapterChange.objects.filter(
                chapter__guide=self.guide,
                chapter__is_draft=False,
                is_notable=True,
                is_draft=False,
            )
            .values_list("id", flat=True)
        )
        combined_ids = set(first_change_ids) | set(notable_change_ids)
        return (
            ChapterChange.objects.filter(id__in=combined_ids)
            .select_related("chapter", "chapter__guide")
            .order_by("-created")[:15]
        )

    def item_title(self, item):
        first_change = (
            ChapterChange.objects.filter(chapter=item.chapter)
            .order_by("created")
            .first()
        )
        if first_change and first_change.pk == item.pk:
            return item.chapter.title
        if item.change_note:
            return "{}: {}".format(item.chapter.title, item.change_note)
        return "{} (updated)".format(item.chapter.title)

    def item_description(self, item):
        first_change = (
            ChapterChange.objects.filter(chapter=item.chapter)
            .order_by("created")
            .first()
        )
        if first_change and first_change.pk == item.pk:
            return markdown(item.body)
        # For notable updates, show the change note + link to the chapter
        parts = []
        if item.change_note:
            parts.append("<p><em>{}</em></p>".format(item.change_note))
        parts.append(markdown(item.body))
        return "\n".join(parts)

    def item_link(self, item):
        return (
            "https://simonwillison.net"
            + item.chapter.get_absolute_url()
            + "#atom-guide"
        )

    def item_pubdate(self, item):
        return item.created

    def item_updateddate(self, item):
        return item.created

    def get_feed(self, obj, request):
        feedgen = super().get_feed(obj, request)
        feedgen.content_type = "application/xml; charset=utf-8"
        return feedgen
