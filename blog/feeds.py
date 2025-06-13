from django.contrib.syndication.views import Feed
from django.utils.dateformat import format as date_format
from django.utils.feedgenerator import Atom1Feed
from django.http import HttpResponse
from blog.models import Entry, Blogmark, Quotation, Note


class Base(Feed):
    feed_type = Atom1Feed
    link = "/"
    author_name = "Simon Willison"

    def __call__(self, request, *args, **kwargs):
        response = super(Base, self).__call__(request, *args, **kwargs)
        # Open CORS headers
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Max-Age"] = "1000"
        # Tell CloudFlare to cache my feeds for 2 minutes
        response["Cache-Control"] = "s-maxage=%d" % (2 * 60)
        return response

    def item_link(self, item):
        return (
            "https://simonwillison.net"
            + item.get_absolute_url()
            + "#atom-%s" % self.ga_source
        )

    def item_categories(self, item):
        return [t.tag for t in item.tags.all()]

    def item_pubdate(self, item):
        return item.created

    def item_updateddate(self, item):
        return item.created

    def get_feed(self, obj, request):
        feedgen = super().get_feed(obj, request)
        feedgen.content_type = "application/xml; charset=utf-8"
        return feedgen


class Entries(Base):
    title = "Simon Willison's Weblog: Entries"
    ga_source = "entries"

    def items(self):
        return (
            Entry.objects.filter(is_draft=False)
            .prefetch_related("tags")
            .order_by("-created")[:15]
        )

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        note = (
            '<p><em>You are only seeing the long-form articles from my blog. '
            'Subscribe to <a href="https://simonwillison.net/atom/everything/">/atom/everything/</a> '
            'to get all of my posts, or take a look at my <a href="https://simonwillison.net/about/#subscribe">other subscription options</a>.</em></p>'
        )
        return item.body + note


class Blogmarks(Base):
    title = "Simon Willison's Weblog: Blogmarks"
    description_template = "feeds/blogmark.html"
    ga_source = "blogmarks"

    def items(self):
        return (
            Blogmark.objects.filter(is_draft=False)
            .prefetch_related("tags")
            .order_by("-created")[:15]
        )

    def item_title(self, item):
        return item.link_title


class Everything(Base):
    title = "Simon Willison's Weblog"
    description_template = "feeds/everything.html"
    ga_source = "everything"

    def items(self):
        # Pretty dumb implementation: pull top 30 of entries/blogmarks/quotations
        # then sort them together and return most recent 30 combined
        last_30_entries = list(
            Entry.objects.filter(is_draft=False)
            .prefetch_related("tags")
            .order_by("-created")[:30]
        )
        last_30_blogmarks = list(
            Blogmark.objects.filter(is_draft=False)
            .prefetch_related("tags")
            .order_by("-created")[:30]
        )
        last_30_quotations = list(
            Quotation.objects.filter(is_draft=False)
            .prefetch_related("tags")
            .order_by("-created")[:30]
        )
        last_30_notes = list(
            Note.objects.filter(is_draft=False)
            .prefetch_related("tags")
            .order_by("-created")[:30]
        )
        combined = (
            last_30_blogmarks + last_30_entries + last_30_quotations + last_30_notes
        )
        combined.sort(key=lambda e: e.created, reverse=True)
        return combined[:30]

    def item_title(self, item):
        if isinstance(item, Entry):
            return item.title
        elif isinstance(item, Blogmark):
            return item.link_title
        elif isinstance(item, Quotation):
            return "Quoting %s" % item.source
        elif isinstance(item, Note):
            if item.title:
                return item.title
            else:
                return "Note on {}".format(date_format(item.created, "jS F Y"))
        else:
            return "Unknown item type"


class SeriesFeed(Everything):
    ga_source = "series"

    def __init__(self, series):
        self.title = "Simon Willison's Weblog: {}".format(series.title)
        self.series = series

    def items(self):
        return list(self.series.entry_set.all().order_by("-created"))


class EverythingTagged(Everything):
    ga_source = "tag"

    def __init__(self, title, items):
        self.title = "Simon Willison's Weblog: {}".format(title)
        self._items = items

    def items(self):
        return self._items


def sitemap(request):
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for klass in (Entry, Blogmark, Quotation, Note):
        for obj in klass.objects.exclude(is_draft=True).only("slug", "created"):
            xml.append(
                "<url><loc>https://simonwillison.net%s</loc></url>"
                % obj.get_absolute_url()
            )
    xml.append("</urlset>")
    return HttpResponse("\n".join(xml), content_type="application/xml")
