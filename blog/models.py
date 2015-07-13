from django.db import models
from django.utils.dates import MONTHS_3
from django.utils.safestring import mark_safe
import re
from xml.etree import ElementTree as ET

tag_re = re.compile('^[a-z0-9]+$')

class Tag(models.Model):
    tag = models.SlugField(
        unique = True
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
    
    def get_related_tags(self, limit=5):
        "Get all items tagged with this, look at /their/ tags, order by count"
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


class Entry(models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64)
    body = models.TextField()
    created = models.DateTimeField()
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        ordering = ('-created',)

    def get_absolute_url(self):
        return '/%d/%s/%d/%s/' % (
            self.created.year, MONTHS_3[self.created.month].title(),
            self.created.day, self.slug
        )

    def edit_url(self):
        return "/admin/blog/entry/%d/" % self.id
    
    def images(self):
        "Extracts images from entry.body"
        et = ET.fromstring('<entry>%s</entry>' % self.body)
        return [i.attrib for i in et.findall('.//img')]

    def __unicode__(self):
        return self.title
    

class Quotation(models.Model):
    slug = models.SlugField(max_length=64)
    quotation = models.TextField()
    source = models.CharField(max_length=255)
    source_url = models.URLField(blank=True, null=True, )
    created = models.DateTimeField()
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        ordering = ('-created',)

    def title(self):
        "Mainly a convenence for the comments RSS feed"
        return u"A quote from %s" % escape(self.source)
    
    
    def get_absolute_url(self):
        return '/%d/%s/%d/%s/' % (
            self.created.year, MONTHS_3[self.created.month].title(),
            self.created.day, self.slug
        )

    def edit_url(self):
        return "/admin/blog/quotation/%d/" % self.id

    def __unicode__(self):
        return self.quotation


class Blogmark(models.Model):
    slug = models.SlugField(max_length=64)
    link_url = models.URLField()
    link_title = models.CharField(max_length=255)
    via_url = models.URLField(blank=True, null=True, )
    via_title = models.CharField(max_length=255, blank=True, null=True)
    commentary = models.TextField()
    created = models.DateTimeField()
    tags = models.ManyToManyField(Tag, blank=True)

    class Meta:
        ordering = ('-created',)

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

    def get_absolute_url(self):
        return u'/%d/%s/%d/%s/' % (
            self.created.year, MONTHS_3[self.created.month].title(),
            self.created.day, self.slug
        )

    def edit_url(self):
        return "/admin/blog/blogmark/%d/" % self.id


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
