from django.db import models
from django.db.models import Sum, Subquery, OuterRef, IntegerField
from django.utils.dates import MONTHS_3
from django.db.models.functions import Coalesce
from django.utils.safestring import mark_safe
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.db.models import JSONField, Count
from django.contrib.postgres.search import SearchVectorField
from django.contrib.postgres.indexes import GinIndex
from django.utils.html import escape, strip_tags
from collections import Counter
import re
import arrow
import datetime
from markdown import markdown
from xml.etree import ElementTree

tag_re = re.compile("^[a-z0-9]+$")


class Tag(models.Model):
    tag = models.SlugField(unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.tag

    def description_rendered(self):
        if self.description:
            return mark_safe(markdown(self.description))
        else:
            return ""

    def get_absolute_url(self):
        return "/tags/%s/" % self.tag

    def get_link(self, reltag=False):
        return mark_safe(
            '<a href="%s"%s>%s</a>'
            % (self.get_absolute_url(), (reltag and ' rel="tag"' or ""), self)
        )

    def get_reltag(self):
        return self.get_link(reltag=True)

    def entry_count(self):
        return self.entry_set.filter(is_draft=False).count()

    def link_count(self):
        return self.blogmark_set.filter(is_draft=False).count()

    def quote_count(self):
        return self.quotation_set.filter(is_draft=False).count()

    def note_count(self):
        return self.note_set.filter(is_draft=False).count()

    def total_count(self):
        entry_count = Subquery(
            Entry.objects.filter(is_draft=False, tags=OuterRef("pk"))
            .values("tags")
            .annotate(count=Count("id"))
            .values("count"),
            output_field=IntegerField(),
        )

        blogmark_count = Subquery(
            Blogmark.objects.filter(is_draft=False, tags=OuterRef("pk"))
            .values("tags")
            .annotate(count=Count("id"))
            .values("count"),
            output_field=IntegerField(),
        )

        quotation_count = Subquery(
            Quotation.objects.filter(is_draft=False, tags=OuterRef("pk"))
            .values("tags")
            .annotate(count=Count("id"))
            .values("count"),
            output_field=IntegerField(),
        )

        note_count = Subquery(
            Note.objects.filter(is_draft=False, tags=OuterRef("pk"))
            .values("tags")
            .annotate(count=Count("id"))
            .values("count"),
            output_field=IntegerField(),
        )

        result = (
            Tag.objects.filter(pk=self.pk)
            .annotate(
                total_count=Sum(
                    Coalesce(entry_count, 0)
                    + Coalesce(blogmark_count, 0)
                    + Coalesce(quotation_count, 0)
                    + Coalesce(note_count, 0)
                )
            )
            .values("total_count")
            .first()
        )

        return result["total_count"] if result else 0

    def all_types_queryset(self):
        entries = (
            self.entry_set.all()
            .annotate(type=models.Value("entry", output_field=models.CharField()))
            .values("pk", "created", "type")
        )
        blogmarks = (
            self.blogmark_set.all()
            .annotate(type=models.Value("blogmark", output_field=models.CharField()))
            .values("pk", "created", "type")
        )
        quotations = (
            self.quotation_set.all()
            .annotate(type=models.Value("quotation", output_field=models.CharField()))
            .values("pk", "created", "type")
        )
        notes = (
            self.note_set.all()
            .annotate(type=models.Value("note", output_field=models.CharField()))
            .values("pk", "created", "type")
        )
        return entries.union(blogmarks, quotations, notes).order_by("-created")

    def get_related_tags(self, limit=10):
        """Get all items tagged with this, look at /their/ tags, order by count"""
        if not hasattr(self, "_related_tags"):
            counts = Counter()
            for klass, collection in (
                (Entry, "entry_set"),
                (Blogmark, "blogmark_set"),
                (Quotation, "quotation_set"),
                (Note, "note_set"),
            ):
                qs = klass.objects.filter(
                    pk__in=getattr(self, collection).all()
                ).values_list("tags__tag", flat=True)
                counts.update(t for t in qs if t != self.tag)
            tag_names = [p[0] for p in counts.most_common(limit)]
            tags_by_name = {t.tag: t for t in Tag.objects.filter(tag__in=tag_names)}
            # Need a list in the correct order
            self._related_tags = [tags_by_name[name] for name in tag_names]
        return self._related_tags

    def rename_tag(self, new_name):
        PreviousTagName.objects.create(tag=self, previous_name=self.tag)
        self.tag = new_name
        self.save()


class PreviousTagName(models.Model):
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)
    previous_name = models.SlugField()

    def __str__(self):
        return self.previous_name


class Series(models.Model):
    created = models.DateTimeField(default=datetime.datetime.utcnow)
    slug = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    summary = models.TextField()

    def summary_rendered(self):
        if self.summary:
            return mark_safe(markdown(self.summary))
        else:
            return ""

    def entries_ordest_first(self):
        return self.entry_set.filter(is_draft=False).order_by("created")

    def get_absolute_url(self):
        return "/series/{}/".format(self.slug)

    def __str__(self):
        return self.title

    class Meta:
        verbose_name_plural = "Series"


class BaseModel(models.Model):
    created = models.DateTimeField(default=datetime.datetime.utcnow)
    tags = models.ManyToManyField(Tag, blank=True)
    slug = models.SlugField(max_length=64)
    metadata = JSONField(blank=True, default=dict)
    search_document = SearchVectorField(null=True)
    import_ref = models.TextField(max_length=64, null=True, unique=True)
    card_image = models.CharField(max_length=128, null=True, blank=True)
    series = models.ForeignKey(Series, blank=True, null=True, on_delete=models.PROTECT)
    is_draft = models.BooleanField(default=False)  # P9163

    def created_unixtimestamp(self):
        return int(arrow.get(self.created).timestamp())

    def tag_summary(self):
        return " ".join(t.tag for t in self.tags.all())

    def get_absolute_url(self):
        return "/%d/%s/%d/%s/" % (
            self.created.year,
            MONTHS_3[self.created.month].title(),
            self.created.day,
            self.slug,
        )

    def edit_url(self):
        return "/admin/blog/%s/%d/" % (self.__class__.__name__.lower(), self.id)

    class Meta:
        abstract = True
        ordering = ("-created",)
        indexes = [GinIndex(fields=["search_document"])]


class Entry(BaseModel):
    title = models.CharField(max_length=255)
    body = models.TextField()
    tweet_html = models.TextField(
        blank=True,
        null=True,
        help_text="""
        Paste in the embed tweet HTML, minus the script tag,
        to display a tweet in the sidebar next to this entry.
    """.strip(),
    )
    extra_head_html = models.TextField(
        blank=True,
        null=True,
        help_text="""
        Extra HTML to be included in the &lt;head&gt; for this entry
    """.strip(),
    )
    custom_template = models.CharField(max_length=100, null=True, blank=True)
    is_entry = True
    live_timezone = models.CharField(max_length=100, null=True, blank=True)

    def next_by_created(self):
        return super().get_next_by_created(is_draft=False)

    def previous_by_created(self):
        return super().get_previous_by_created(is_draft=False)

    def images(self):
        """Extracts images from entry.body"""
        et = ElementTree.fromstring("<entry>%s</entry>" % self.body)
        return [i.attrib for i in et.findall(".//img")]

    def index_components(self):
        return {
            "A": self.title,
            "C": strip_tags(self.body),
            "B": " ".join(self.tags.values_list("tag", flat=True)),
        }

    def series_info(self):
        entries = list(self.series.entries_ordest_first().defer("body"))
        has_next = False
        start = 1
        # If there are more than 7, only show 3 before and 3 after this one
        if len(entries) > 7:
            entry_ids = [e.pk for e in entries]
            try:
                this_index = entry_ids.index(self.pk)
            except ValueError:
                this_index = len(entries)
            if this_index < 4:
                entries = entries[:7]
                start = 1
            else:
                entries = entries[this_index - 3 : this_index + 4]
                start = (this_index - 3) + 1
            has_next = len(entry_ids) > start + len(entries) - 1
        return {
            "start": start,
            "entries": entries,
            "has_next": has_next,
        }

    def multi_paragraph(self):
        return self.body.count("<p") > 1

    def __str__(self):
        return self.title

    class Meta(BaseModel.Meta):
        verbose_name_plural = "Entries"


class LiveUpdate(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    content = models.TextField()
    entry = models.ForeignKey(Entry, related_name="updates", on_delete=models.CASCADE)

    def __str__(self):
        return "{}: {}".format(self.created, self.content)


class Quotation(BaseModel):
    quotation = models.TextField()
    source = models.CharField(max_length=255)
    source_url = models.URLField(
        blank=True,
        null=True,
    )
    context = models.CharField(max_length=255, blank=True, null=True)

    is_quotation = True

    def body(self):
        return mark_safe(markdown(self.quotation))

    def body_strip_tags(self):
        return strip_tags(markdown(self.quotation))

    def context_rendered(self):
        if self.context:
            rendered = markdown(self.context)
            # Remove leading/trailing <p> tag
            if rendered.startswith("<p>") and rendered.endswith("</p>"):
                return mark_safe(rendered[3:-4])
            return mark_safe(rendered)
        else:
            return ""

    def title(self):
        """Mainly a convenience for the comments RSS feed"""
        return "A quote from %s" % escape(self.source)

    def index_components(self):
        return {
            "A": self.quotation,
            "B": " ".join(self.tags.values_list("tag", flat=True)),
            "C": self.source,
        }

    def __str__(self):
        return self.body_strip_tags()


class Blogmark(BaseModel):
    link_url = models.URLField(max_length=512)
    link_title = models.CharField(max_length=255)
    title = models.CharField(
        max_length=255, blank=True, default="", help_text="Optional page title"
    )
    via_url = models.URLField(blank=True, null=True, max_length=512)
    via_title = models.CharField(max_length=255, blank=True, null=True)
    commentary = models.TextField()
    use_markdown = models.BooleanField(
        default=False,
        help_text='Images can use the img element - set width="..." for a specific width and use class="blogmark-image" to center and add a drop shadow.',
    )

    is_blogmark = True

    def index_components(self):
        return {
            "A": self.link_title,
            "B": " ".join(self.tags.values_list("tag", flat=True)),
            "C": self.commentary
            + " "
            + self.link_domain()
            + " "
            + (self.via_title or ""),
        }

    def __str__(self):
        return self.link_title

    def link_domain(self):
        return self.link_url.split("/")[2]

    def body(self):
        if self.use_markdown:
            return mark_safe(markdown(self.commentary))
        return self.commentary

    def word_count(self):
        count = len(self.commentary.split())
        if count == 1:
            return "1 word"
        else:
            return "%d words" % count


class Note(BaseModel):
    body = models.TextField()
    title = models.CharField(
        max_length=255, blank=True, default="", help_text="Optional page title"
    )
    is_note = True

    def body_rendered(self):
        return mark_safe(markdown(self.body))

    def index_components(self):
        # Note: 'A' is typically title/headline, 'C' is main body, 'B' is tags
        return {
            "C": self.body,
            "B": " ".join(self.tags.values_list("tag", flat=True)),
        }

    def __str__(self):
        # Return first 50 chars as string representation
        if len(self.body) > 50:
            return self.body[:50] + "..."
        return self.body

    class Meta(BaseModel.Meta):
        verbose_name_plural = "Notes"


class Photo(models.Model):
    flickr_id = models.CharField(max_length=32)
    server = models.CharField(max_length=8)
    secret = models.CharField(max_length=32)
    title = models.CharField(max_length=255, blank=True, null=True)
    longitude = models.CharField(max_length=32, blank=True, null=True)
    latitude = models.CharField(max_length=32, blank=True, null=True)
    created = models.DateTimeField()

    def __str__(self):
        return self.title

    def photopage(self):
        return "http://www.flickr.com/photo.gne?id=%s" % self.flickr_id

    def url_s(self):
        return "http://static.flickr.com/%s/%s_%s_s.jpg" % (
            self.server,
            self.flickr_id,
            self.secret,
        )

    def view_thumb(self):
        return '<a href="%s"><img src="%s" width="75" height="75" /></a>' % (
            self.photopage(),
            self.url_s(),
        )


class Photoset(models.Model):
    flickr_id = models.CharField(max_length=32)
    title = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField()
    photos = models.ManyToManyField(
        Photo,
        related_name="in_photoset",
    )
    primary = models.ForeignKey(Photo, on_delete=models.CASCADE)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return "http://www.flickr.com/photos/simon/sets/%s/" % self.flickr_id

    def view_thumb(self):
        return '<a href="%s"><img src="%s" width="75" height="75" /></a>' % (
            self.primary.photopage(),
            self.primary.url_s(),
        )

    def has_map(self):
        return self.photos.filter(longitude__isnull=False).count() > 0


BAD_WORDS = (
    "viagra",
    "cialis",
    "poker",
    "levitra",
    "casino",
    "ifrance.com",
    "phentermine",
    "plasmatics.com",
    "xenical",
    "sohbet",
    "oyuna",
    "oyunlar",
)

SPAM_STATUS_OPTIONS = (
    ("normal", "Not suspected"),
    ("approved", "Approved"),
    ("suspected", "Suspected"),
    ("spam", "SPAM"),
)

COMMENTS_ALLOWED_ON = ("entry", "blogmark", "quotation", "note")


class Comment(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(db_index=True)
    item = GenericForeignKey()
    # The comment
    body = models.TextField()
    created = models.DateTimeField()
    # Author information
    name = models.CharField(max_length=50)
    url = models.URLField(max_length=255, blank=True, null=True)
    email = models.CharField(max_length=50, blank=True, null=True)
    openid = models.CharField(max_length=255, blank=True, null=True)
    ip = models.GenericIPAddressField()
    # Spam filtering
    spam_status = models.CharField(max_length=16, choices=SPAM_STATUS_OPTIONS)
    visible_on_site = models.BooleanField(default=True, db_index=True)
    spam_reason = models.TextField()

    def get_absolute_url(self):
        return "/%d/%s/%d/%s/#c%d" % (
            self.item.created.year,
            MONTHS_3[self.item.created.month].title(),
            self.item.created.day,
            self.item.slug,
            self.id,
        )

    def edit_url(self):
        return "/admin/blog/comment/%d/" % self.id

    def __str__(self):
        return '%s on "%s"' % (self.name, self.item)

    def admin_summary(self):
        return '<b>%s</b><br><span style="color: black;">%s</span>' % (
            escape(str(self)),
            escape(self.body[:200]),
        )

    admin_summary.allow_tags = True
    admin_summary.short_description = "Comment"

    def on_link(self):
        return '<a href="%s">%s</a>(<a href="%s">#</a>)' % (
            self.item.get_absolute_url(),
            self.content_type.name.title(),
            self.get_absolute_url(),
        )

    on_link.allow_tags = True
    on_link.short_description = "On"

    def ip_link(self):
        return '<a href="/admin/blog/comment/?ip__exact=%s">%s</a>' % (self.ip, self.ip)

    ip_link.allow_tags = True
    ip_link.short_description = "IP"

    def spam_status_options(self):
        bits = []
        bits.append(self.get_spam_status_display())
        bits.append("<br>")
        bits.append(
            '<form class="flagspam" action="/admin/flagspam/" ' + ' method="post">'
        )
        bits.append('<input type="hidden" name="id" value="%s">' % self.id)
        bits.append(
            '<input type="submit" class="submit" '
            + 'name="flag_as_spam" value="SPAM"> '
        )
        bits.append(
            '<input type="submit" class="submit" '
            + 'name="flag_as_approved" value="OK">'
        )
        bits.append("</form>")
        return "".join(bits)

    spam_status_options.allow_tags = True
    spam_status_options.short_description = "Spam status"

    class Meta:
        ordering = ("-created",)
        get_latest_by = "created"


def load_mixed_objects(dicts):
    """
    Takes a list of dictionaries, each of which must at least have a 'type'
    and a 'pk' key. Returns a list of ORM objects of those various types.

    Each returned ORM object has a .original_dict attribute populated.
    """
    to_fetch = {}
    for d in dicts:
        to_fetch.setdefault(d["type"], set()).add(d["pk"])
    fetched = {}
    for key, model in (
        ("blogmark", Blogmark),
        ("entry", Entry),
        ("quotation", Quotation),
        ("note", Note),
    ):
        ids = to_fetch.get(key) or []
        objects = model.objects.prefetch_related("tags").filter(pk__in=ids)
        for obj in objects:
            fetched[(key, obj.pk)] = obj
    # Build list in same order as dicts argument
    to_return = []
    for d in dicts:
        item = fetched.get((d["type"], d["pk"])) or None
        if item:
            item.original_dict = d
        to_return.append(item)
    return to_return
