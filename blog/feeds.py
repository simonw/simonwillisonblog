from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed
from blog.models import Entry, Blogmark


class Base(Feed):
    feed_type = Atom1Feed
    link = "/"

    def __call__(self, request, *args, **kwargs):
        response = super(Base, self).__call__(request, *args, **kwargs)
        # Tell CloudFlare to cache my feeds for 15 minutes
        response['Cache-Control'] = 's-maxage=%d' % (15 * 60)
        return response

    def item_link(self, item):
        return item.get_absolute_url() + '#atom-%s' % self.ga_source

    def item_categories(self, item):
        return [t.tag for t in item.tags.all()]

    def item_pubdate(self, item):
        return item.created


class Entries(Base):
    title = "Simon Willison's Weblog: Entries"
    ga_source = 'entries'

    def items(self):
        return Entry.objects.prefetch_related(
            'tags'
        ).order_by('-created')[:15]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.body


class Blogmarks(Base):
    title = "Simon Willison's Weblog: Blogmarks"
    description_template = "feeds/blogmark.html"
    ga_source = 'blogmarks'

    def items(self):
        return Blogmark.objects.prefetch_related(
            'tags'
        ).order_by('-created')[:15]

    def item_title(self, item):
        return item.link_title


class Everything(Base):
    title = "Simon Willison's Weblog"
    description_template = "feeds/everything.html"
    ga_source = 'everything'

    def items(self):
        # Pretty dumb implementation: pull top 30 of entries and blogmarks
        # then sort them together and return most recent 30 combined
        # Ignores existence of quotations for the moment.
        last_30_entries = list(Entry.objects.prefetch_related(
            'tags'
        ).order_by('-created')[:30])
        last_30_blogmarks = list(Blogmark.objects.prefetch_related(
            'tags'
        ).order_by('-created')[:30])
        combined = last_30_blogmarks + last_30_entries
        combined.sort(key=lambda e: e.created, reverse=True)
        return combined[:30]

    def item_title(self, item):
        if isinstance(item, Entry):
            return item.title
        else:
            return item.link_title
