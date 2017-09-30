from django.db import models
from django.utils.dates import MONTHS_3
from django.utils.safestring import mark_safe
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.postgres.fields import JSONField
from django.contrib.postgres.search import SearchVectorField
from django.utils.html import escape, strip_tags
import re
from xml.etree import ElementTree

tag_re = re.compile('^[a-z0-9]+$')


class Tag(models.Model):
    tag = models.SlugField(
        unique=True
    )

    def __unicode__(self):
        return self.tag

    def get_absolute_url(self):
        return "/tags/%s/" % self.tag

    def get_link(self, reltag=False):
        return mark_safe('<a href="%s"%s>%s</a>' % (
            self.get_absolute_url(), (reltag and ' rel="tag"' or ''), self
        ))

    def get_reltag(self):
        return self.get_link(reltag=True)

    def entry_count(self):
        return self.entry_set.count()

    def link_count(self):
        return self.blogmark_set.count()

    def quote_count(self):
        return self.quotation_set.count()

    def total_count(self):
        return self.entry_count() + self.link_count() + self.quote_count()

    def all_types_queryset(self):
        entries = self.entry_set.all().annotate(
            type=models.Value('entry', output_field=models.CharField())
        ).values('pk', 'created', 'type')
        blogmarks = self.blogmark_set.all().annotate(
            type=models.Value('blogmark', output_field=models.CharField())
        ).values('pk', 'created', 'type')
        quotations = self.quotation_set.all().annotate(
            type=models.Value('quotation', output_field=models.CharField())
        ).values('pk', 'created', 'type')
        return entries.union(blogmarks, quotations).order_by('-created')

    def get_related_tags(self, limit=5):
        """Get all items tagged with this, look at /their/ tags, order by count"""
        if not hasattr(self, '_related_tags'):
            other_tags = {} # tag: count
            for collection in ('entry_set', 'blogmark_set', 'quotation_set'):
                for item in getattr(self, collection).all():
                    for tag in item.tags.all():
                        if tag.tag == self.tag:
                            continue
                        try:
                            other_tags[tag.tag] += 1
                        except KeyError:
                            other_tags[tag.tag] = 1
            pairs = other_tags.items()
            pairs.sort(lambda x, y: cmp(y[1], x[1]))
            self._related_tags = [pair[0] for pair in pairs[:limit]]
        return self._related_tags


class BaseModel(models.Model):
    created = models.DateTimeField()
    tags = models.ManyToManyField(Tag, blank=True)
    slug = models.SlugField(max_length=64)
    metadata = JSONField()
    search_document = SearchVectorField(null=True)

    def tag_summary(self):
        return u' '.join(t.tag for t in self.tags.all())

    def get_absolute_url(self):
        return '/%d/%s/%d/%s/' % (
            self.created.year, MONTHS_3[self.created.month].title(),
            self.created.day, self.slug
        )

    def edit_url(self):
        return "/admin/blog/%s/%d/" % (
            self.__class__.__name__.lower(), self.id
        )

    class Meta:
        abstract = True
        ordering = ('-created',)


class Entry(BaseModel):
    title = models.CharField(max_length=255)
    body = models.TextField()

    def images(self):
        """Extracts images from entry.body"""
        et = ElementTree.fromstring('<entry>%s</entry>' % self.body)
        return [i.attrib for i in et.findall('.//img')]

    def index_components(self):
        return {
            'A': self.title,
            'C': strip_tags(self.body),
            'B': ' '.join(self.tags.values_list('tag', flat=True)),
        }

    def __unicode__(self):
        return self.title


class Quotation(BaseModel):
    quotation = models.TextField()
    source = models.CharField(max_length=255)
    source_url = models.URLField(blank=True, null=True, )

    def title(self):
        """Mainly a convenence for the comments RSS feed"""
        return u"A quote from %s" % escape(self.source)

    def index_components(self):
        return {
            'A': self.quotation,
            'B': ' '.join(self.tags.values_list('tag', flat=True)),
            'C': self.source,
        }

    def __unicode__(self):
        return self.quotation


class Blogmark(BaseModel):
    link_url = models.URLField()
    link_title = models.CharField(max_length=255)
    via_url = models.URLField(blank=True, null=True)
    via_title = models.CharField(max_length=255, blank=True, null=True)
    commentary = models.TextField()

    def index_components(self):
        return {
            'A': self.link_title,
            'B': ' '.join(self.tags.values_list('tag', flat=True)),
            'C': self.commentary + ' ' + self.link_domain + ' ' + (self.via_title or ''),
        }

    def __unicode__(self):
        return self.link_title

    def link_domain(self):
        return self.link_url.split('/')[2]

    def word_count(self):
        count = len(self.commentary.split())
        if count == 1:
            return '1 word'
        else:
            return '%d words' % count


class Photo(models.Model):
    flickr_id = models.CharField(max_length=32)
    server = models.CharField(max_length=8)
    secret = models.CharField(max_length=32)
    title = models.CharField(max_length=255, blank=True, null=True)
    longitude = models.CharField(max_length=32, blank=True, null=True)
    latitude = models.CharField(max_length=32, blank=True, null=True)
    created = models.DateTimeField()

    def __unicode__(self):
        return self.title

    def photopage(self):
        return "http://www.flickr.com/photo.gne?id=%s" % self.flickr_id

    def url_s(self):
        return "http://static.flickr.com/%s/%s_%s_s.jpg" % (
            self.server, self.flickr_id, self.secret
        )

    def view_thumb(self):
        return '<a href="%s"><img src="%s" width="75" height="75" /></a>' % (
            self.photopage(), self.url_s()
        )


class Photoset(models.Model):
    flickr_id = models.CharField(max_length=32)
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField()
    photos = models.ManyToManyField(
        Photo, related_name="in_photoset",
    )
    primary = models.ForeignKey(Photo)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return "http://www.flickr.com/photos/simon/sets/%s/" % self.flickr_id

    def view_thumb(self):
        return '<a href="%s"><img src="%s" width="75" height="75" /></a>' % (
            self.primary.photopage(), self.primary.url_s()
        )

    def has_map(self):
        return self.photos.filter(longitude__isnull=False).count() > 0


BAD_WORDS = (
    'viagra', 'cialis', 'poker', 'levitra', 'casino', 'ifrance.com',
    'phentermine', 'plasmatics.com', 'xenical', 'sohbet', 'oyuna', 'oyunlar',
)

SPAM_STATUS_OPTIONS = (
    ('normal', 'Not suspected'),
    ('approved', 'Approved'),
    ('suspected', 'Suspected'),
    ('spam', 'SPAM')
)

COMMENTS_ALLOWED_ON = ('entry', 'blogmark', 'quotation')


class Comment(models.Model):
    content_type = models.ForeignKey(ContentType)
    object_id = models.PositiveIntegerField(db_index=True)
    item = GenericForeignKey()
    # The comment
    body = models.TextField()
    created = models.DateTimeField()
    # Author information
    name = models.CharField(max_length=50)
    url = models.URLField(max_length=255,
        blank=True, null=True)
    email = models.CharField(max_length=50, blank=True, null=True)
    openid = models.CharField(max_length=255, blank=True, null=True)
    ip = models.GenericIPAddressField()
    # Spam filtering
    spam_status = models.CharField(max_length=16, choices=SPAM_STATUS_OPTIONS)
    visible_on_site = models.BooleanField(default=True, db_index=True)
    spam_reason = models.TextField()

    def get_absolute_url(self):
        return '/%d/%s/%d/%s/#c%d' % (
            self.item.created.year,
            MONTHS_3[self.item.created.month].title(),
            self.item.created.day, self.item.slug, self.id
        )

    def edit_url(self):
        return "/admin/blog/comment/%d/" % self.id

    def __unicode__(self):
        return '%s on "%s"' % (self.name, self.item)

    def admin_summary(self):
        return '<b>%s</b><br><span style="color: black;">%s</span>' % (
            escape(str(self)), escape(self.body[:200]))
    admin_summary.allow_tags = True
    admin_summary.short_description = 'Comment'

    def on_link(self):
        return '<a href="%s">%s</a>(<a href="%s">#</a>)' % (
            self.item.get_absolute_url(), self.content_type.name.title(),
            self.get_absolute_url())
    on_link.allow_tags = True
    on_link.short_description = "On"

    def ip_link(self):
        return '<a href="/admin/blog/comment/?ip__exact=%s">%s</a>' % (
            self.ip, self.ip)
    ip_link.allow_tags = True
    ip_link.short_description = 'IP'

    def spam_status_options(self):
        bits = []
        bits.append(self.get_spam_status_display())
        bits.append('<br>')
        bits.append('<form class="flagspam" action="/admin/flagspam/" ' +
            ' method="post">')
        bits.append('<input type="hidden" name="id" value="%s">' % self.id)
        bits.append('<input type="submit" class="submit" ' +
            'name="flag_as_spam" value="SPAM"> ')
        bits.append('<input type="submit" class="submit" ' +
            'name="flag_as_approved" value="OK">')
        bits.append('</form>')
        return ''.join(bits)
    spam_status_options.allow_tags = True
    spam_status_options.short_description = 'Spam status'

    class Meta:
        ordering = ('-created',)
        get_latest_by = 'created'


def load_mixed_objects(dicts):
    """
    Takes a list of dictionaries, each of which must at least have a 'type'
    and a 'pk' key. Returns a list of ORM objects of those various types.

    Each returned ORM object has a .original_dict attribute populated.
    """
    to_fetch = {}
    for d in dicts:
        to_fetch.setdefault(d['type'], set()).add(d['pk'])
    fetched = {}
    for key, model in (
        ('blogmark', Blogmark),
        ('entry', Entry),
        ('quotation', Quotation),
    ):
        ids = to_fetch.get(key) or []
        objects = model.objects.filter(pk__in=ids)
        for obj in objects:
            fetched[(key, obj.pk)] = obj
    # Build list in same order as dicts argument
    to_return = []
    for d in dicts:
        item = fetched.get((d['type'], d['pk'])) or None
        if item:
            item.original_dict = d
        to_return.append(item)
    return to_return
