# coding=utf8
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.db import models
from django.db.models import CharField, Value
from django.conf import settings
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.http import Http404, HttpResponsePermanentRedirect as Redirect, HttpResponse
from django.test import Client
from django.utils import timezone
from .models import (
    Beat,
    Blogmark,
    Chapter,
    Entry,
    Guide,
    Quotation,
    Note,
    Photo,
    Photoset,
    Series,
    Tag,
    PreviousTagName,
    TagMerge,
)
import hashlib
import hmac
from urllib.parse import urlencode
import requests
from bs4 import BeautifulSoup as Soup
import datetime
import random
from collections import Counter
import cloudflare
import os
import pytz

MONTHS_3_REV = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTHS_3_REV_REV = {value: key for key, value in list(MONTHS_3_REV.items())}
BLACKLISTED_TAGS = ("quora", "flash", "resolved", "recovered")


def set_no_cache(response):
    response["Cache-Control"] = "private, no-cache, no-store, must-revalidate"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    return response


def archive_item(request, year, month, day, slug):
    if day.startswith("0"):
        day = day.lstrip("0")
        return Redirect("/%s/%s/%s/%s/" % (year, month, day, slug))

    # This could be a quote OR link OR entry
    for content_type, model in (
        ("blogmark", Blogmark),
        ("entry", Entry),
        ("quotation", Quotation),
        ("note", Note),
        ("beat", Beat),
    ):
        try:
            obj = get_object_or_404(
                model,
                created__year=int(year),
                created__month=MONTHS_3_REV[month.lower()],
                created__day=int(day),
                slug=slug,
            )
        except Http404:
            continue

        # If item is entry posted before Dec 1 2006, add "previously hosted"
        if content_type == "entry" and obj.created < datetime.datetime(
            2006, 12, 1, 1, 1, 1, tzinfo=datetime.timezone.utc
        ):
            previously_hosted = (
                "http://simon.incutio.com/archive/"
                + obj.created.strftime("%Y/%m/%d/")
                + obj.slug
            )
        else:
            previously_hosted = None

        template = getattr(obj, "custom_template", None) or "{}.html".format(
            content_type
        )

        updates = []
        if isinstance(obj, Entry):
            updates = list(obj.updates.order_by("created"))
            for update in updates:
                update.created_str = (
                    str(
                        update.created.astimezone(
                            pytz.timezone("America/Los_Angeles")
                        ).time()
                    )
                    .split(".")[0]
                    .rsplit(":", 1)[0]
                )

        response = render(
            request,
            template,
            {
                content_type: obj,
                "content_type": content_type,
                "object_id": obj.id,
                "previously_hosted": previously_hosted,
                "item": obj,
                "recent_articles": Entry.objects.filter(is_draft=False)
                .prefetch_related("tags")
                .order_by("-created")[0:3],
                "is_draft": obj.is_draft,
                "updates": updates,
            },
        )
        if obj.is_draft:
            set_no_cache(response)
        else:
            six_months = datetime.timedelta(days=180)
            if obj.created < timezone.now() - six_months:
                response["Cache-Control"] = "s-maxage={}".format(24 * 60 * 60)
        response["x-enable-card"] = "1"
        return response

    # If we get here, non of the views matched
    raise Http404


def index(request):
    # Get back 30 most recent across all item types
    recent = list(
        Entry.objects.filter(is_draft=False)
        .annotate(content_type=Value("entry", output_field=CharField()))
        .values("content_type", "id", "created")
        .order_by()
        .union(
            Blogmark.objects.filter(is_draft=False)
            .annotate(content_type=Value("blogmark", output_field=CharField()))
            .values("content_type", "id", "created")
            .order_by()
        )
        .union(
            Quotation.objects.filter(is_draft=False)
            .annotate(content_type=Value("quotation", output_field=CharField()))
            .values("content_type", "id", "created")
            .order_by()
        )
        .union(
            Note.objects.filter(is_draft=False)
            .annotate(content_type=Value("note", output_field=CharField()))
            .values("content_type", "id", "created")
            .order_by()
        )
        .union(
            Beat.objects.filter(is_draft=False)
            .annotate(content_type=Value("beat", output_field=CharField()))
            .values("content_type", "id", "created")
            .order_by()
        )
        .order_by("-created")[:30]
    )

    # Now load the entries, blogmarks, quotations
    items = []
    to_load = {}
    for item in recent:
        to_load.setdefault(item["content_type"], []).append(item["id"])
    for content_type, model in (
        ("entry", Entry),
        ("blogmark", Blogmark),
        ("quotation", Quotation),
        ("note", Note),
        ("beat", Beat),
    ):
        if content_type not in to_load:
            continue
        objects = model.objects.prefetch_related("tags").in_bulk(to_load[content_type])
        items.extend([{"type": content_type, "obj": obj} for obj in objects.values()])

    items.sort(key=lambda x: x["obj"].created, reverse=True)

    response = render(
        request,
        "homepage.html",
        {
            "items": items,
            "entries": Entry.objects.filter(is_draft=False)
            .only("id", "slug", "created", "title", "extra_head_html")
            .prefetch_related("tags")[0:40],
            "current_tags": find_current_tags(5),
            "has_guides": Guide.objects.filter(is_draft=False).exists(),
        },
    )
    response["Cache-Control"] = "s-maxage=200"
    return response


def entry_updates(request, entry_id):
    entry = get_object_or_404(Entry, pk=entry_id)
    updates = list(entry.updates.order_by("created"))
    for update in updates:
        update.created_str = (
            str(update.created.astimezone(pytz.timezone("America/Los_Angeles")).time())
            .split(".")[0]
            .rsplit(":", 1)[0]
        )
    response = render(request, "entry_updates.html", {"updates": updates})
    response["Cache-Control"] = "s-maxage=10"
    return response


def entry_updates_json(request, entry_id):
    entry = get_object_or_404(Entry, pk=entry_id)
    updates = entry.updates.order_by("created")
    since_id = request.GET.get("since")
    if since_id:
        updates = updates.filter(id__gt=since_id)
    response = JsonResponse(
        {
            "updates": [
                {
                    "id": update.id,
                    "created": update.created.isoformat(),
                    "created_str": (
                        str(
                            update.created.astimezone(
                                pytz.timezone("America/Los_Angeles")
                            ).time()
                        )
                        .split(".")[0]
                        .rsplit(":", 1)[0]
                    ),
                    "content": update.content,
                }
                for update in updates
            ]
        }
    )
    response["Cache-Control"] = "s-maxage=10"
    return response


def find_current_tags(num=5):
    """Returns num random tags from top 30 in recent 400 taggings"""
    last_400_tags = list(
        Tag.quotation_set.through.objects.annotate(
            created=models.F("quotation__created")
        )
        .values("tag__tag", "created")
        .union(
            Tag.entry_set.through.objects.annotate(
                created=models.F("entry__created")
            ).values("tag__tag", "created"),
            Tag.blogmark_set.through.objects.annotate(
                created=models.F("blogmark__created")
            ).values("tag__tag", "created"),
            Tag.note_set.through.objects.annotate(
                created=models.F("note__created")
            ).values("tag__tag", "created"),
            Tag.beat_set.through.objects.annotate(
                created=models.F("beat__created")
            ).values("tag__tag", "created"),
        )
        .order_by("-created")[:400]
    )
    counter = Counter(
        t["tag__tag"] for t in last_400_tags if t["tag__tag"] not in BLACKLISTED_TAGS
    )
    candidates = [p[0] for p in counter.most_common(30)]
    random.shuffle(candidates)
    tags = Tag.objects.in_bulk(candidates[:num], field_name="tag")
    return [tags[tag] for tag in candidates[:num]]


def archive_year(request, year):
    year = int(year)
    # Display list of months
    # each with count of blogmarks/photos/entries/quotes
    # We can cache this page heavily, so don't worry too much
    months = []
    max_count = 0
    for month in range(1, 12 + 1):
        date = datetime.date(year=year, month=month, day=1)
        entry_count = Entry.objects.filter(
            created__year=year, created__month=month, is_draft=False
        ).count()
        link_count = Blogmark.objects.filter(
            created__year=year, created__month=month, is_draft=False
        ).count()
        quote_count = Quotation.objects.filter(
            created__year=year, created__month=month, is_draft=False
        ).count()
        photo_count = Photo.objects.filter(
            created__year=year, created__month=month
        ).count()
        note_count = Note.objects.filter(
            created__year=year, created__month=month, is_draft=False
        ).count()
        month_count = entry_count + link_count + quote_count + photo_count + note_count
        if month_count:
            counts = [
                ("entry", entry_count),
                ("link", link_count),
                ("photo", photo_count),
                ("quote", quote_count),
                ("note", note_count),
            ]
            counts_not_0 = [p for p in counts if p[1]]
            months.append(
                {
                    "date": date,
                    "counts": counts,
                    "counts_not_0": counts_not_0,
                    "entries": list(
                        Entry.objects.filter(
                            created__year=year, created__month=month, is_draft=False
                        ).order_by("created")
                    ),
                }
            )
            max_count = max(
                max_count, entry_count, link_count, quote_count, photo_count, note_count
            )
    return render(
        request,
        "archive_year.html",
        {
            "months": months,
            "year": year,
            "max_count": max_count,
        },
    )


def archive_month(request, year, month):
    year = int(year)
    month = MONTHS_3_REV[month.lower()]

    items = []
    type_counts = []

    for model, type_name, singular, plural in (
        (Entry, "entry", "entry", "entries"),
        (Blogmark, "blogmark", "link", "links"),
        (Quotation, "quotation", "quote", "quotes"),
        (Note, "note", "note", "notes"),
        (Beat, "beat", "beat", "beats"),
    ):
        ids = list(
            model.objects.filter(
                created__year=year, created__month=month, is_draft=False
            ).values_list("id", flat=True)
        )
        if ids:
            items.extend(
                [
                    {"type": type_name, "obj": obj}
                    for obj in list(
                        model.objects.prefetch_related("tags").in_bulk(ids).values()
                    )
                ]
            )
            type_counts.append(
                {
                    "type": type_name,
                    "singular": singular,
                    "plural": plural,
                    "count": len(ids),
                }
            )
    if not items:
        raise Http404
    items.sort(key=lambda x: x["obj"].created)
    # Paginate it
    paginator = Paginator(items, min(1000, int(request.GET.get("size") or "30")))
    page_number = request.GET.get("page") or "1"
    if page_number == "last":
        page_number = paginator.num_pages
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        raise Http404
    except EmptyPage:
        raise Http404

    return render(
        request,
        "archive_month.html",
        {
            "items": page.object_list,
            "total": paginator.count,
            "page": page,
            "date": datetime.date(year, month, 1),
            "type_counts": type_counts,
        },
    )


def _get_adjacent_content_days(current_date):
    """
    Find the nearest previous and next days that have published content.
    Returns (previous_date, next_date) where each is a datetime.date or None.
    """
    previous_date = None
    next_date = None

    for model in (Blogmark, Entry, Quotation, Note, Beat):
        prev_created = (
            model.objects.filter(
                created__date__lt=current_date,
                is_draft=False,
            )
            .order_by("-created")
            .values_list("created", flat=True)
            .first()
        )
        if prev_created:
            prev_day = prev_created.date()
            if previous_date is None or prev_day > previous_date:
                previous_date = prev_day

        next_created = (
            model.objects.filter(
                created__date__gt=current_date,
                is_draft=False,
            )
            .order_by("created")
            .values_list("created", flat=True)
            .first()
        )
        if next_created:
            next_day = next_created.date()
            if next_date is None or next_day < next_date:
                next_date = next_day

    return previous_date, next_date


def _day_archive_url(date):
    """Build the day archive URL for a given datetime.date."""
    return "/%d/%s/%d/" % (
        date.year,
        MONTHS_3_REV_REV[date.month].title(),
        date.day,
    )


def archive_day(request, year, month, day):
    if day.startswith("0"):
        day = day.lstrip("0")
        return Redirect("/%s/%s/%s/" % (year, month, day))
    context = {}
    context["date"] = datetime.date(int(year), MONTHS_3_REV[month.lower()], int(day))
    items = []  # Array of {'type': , 'obj': }
    count = 0
    for name, model in (
        ("blogmark", Blogmark),
        ("entry", Entry),
        ("quotation", Quotation),
        ("note", Note),
        ("beat", Beat),
    ):
        filt = model.objects.filter(
            created__year=int(year),
            created__month=MONTHS_3_REV[month.lower()],
            created__day=int(day),
            is_draft=False,
        ).order_by("created")
        context[name] = list(filt)
        count += len(context[name])
        items.extend([{"type": name, "obj": obj} for obj in context[name]])
    # Now do photosets separately because they have no created field
    context["photoset"] = list(
        Photoset.objects.filter(
            primary__created__year=int(year),
            primary__created__month=MONTHS_3_REV[month.lower()],
            primary__created__day=int(day),
        )
    )
    for photoset in context["photoset"]:
        photoset.created = photoset.primary.created
    count += len(context["photoset"])
    items.extend([{"type": "photoset", "obj": ps} for ps in context["photoset"]])
    if count == 0:
        raise Http404("No photosets/photos/entries/quotes/links for that day")
    items.sort(key=lambda x: x["obj"].created)
    context["items"] = items
    photos = Photo.objects.filter(
        created__year=context["date"].year,
        created__month=context["date"].month,
        created__day=context["date"].day,
    )
    context["photos"] = photos[:25]
    # Should we show more_photos ?
    if photos.count() > 25:
        context["more_photos"] = photos.count()
    # Find adjacent days with content for navigation
    previous_day, next_day = _get_adjacent_content_days(context["date"])
    if previous_day:
        context["previous_day"] = previous_day
        context["previous_day_url"] = _day_archive_url(previous_day)
    if next_day:
        context["next_day"] = next_day
        context["next_day_url"] = _day_archive_url(next_day)
    return render(request, "archive_day.html", context)


def tag_index(request):
    return render(request, "tags.html")


def top_tags(request):
    """Display recent headlines for the 10 most popular tags."""
    tags = (
        Tag.objects.annotate(
            entry_count=models.Count(
                "entry", filter=models.Q(entry__is_draft=False), distinct=True
            ),
            blogmark_count=models.Count(
                "blogmark", filter=models.Q(blogmark__is_draft=False), distinct=True
            ),
            quotation_count=models.Count(
                "quotation", filter=models.Q(quotation__is_draft=False), distinct=True
            ),
            note_count=models.Count(
                "note", filter=models.Q(note__is_draft=False), distinct=True
            ),
            beat_count=models.Count(
                "beat", filter=models.Q(beat__is_draft=False), distinct=True
            ),
        )
        .annotate(
            total=models.F("entry_count")
            + models.F("blogmark_count")
            + models.F("quotation_count")
            + models.F("note_count")
            + models.F("beat_count")
        )
        .order_by("-total")[:10]
    )
    tags_info = [
        {
            "tag": tag,
            "total": tag.total,
            "recent_entries": tag.entry_set.filter(is_draft=False).order_by("-created")[
                :5
            ],
        }
        for tag in tags
    ]
    return render(request, "top_tags.html", {"tags_info": tags_info})


# This query gets the IDs of things that match all of the tags
INTERSECTION_SQL = """
    SELECT %(content_table)s.id
        FROM %(content_table)s, %(tag_table)s
    WHERE is_draft = false AND %(tag_table)s.tag_id IN (
            SELECT id FROM blog_tag WHERE tag IN (%(joined_tags)s)
        )
        AND %(tag_table)s.%(tag_table_content_key)s = %(content_table)s.id
    GROUP BY %(content_table)s.id
        HAVING COUNT(%(content_table)s.id) = %(tag_count)d
"""


def archive_tag(request, tags, atom=False):
    from .feeds import EverythingTagged

    tags_ = Tag.objects.filter(tag__in=tags.split("+")).values_list("tag", flat=True)[
        :3
    ]
    if not tags_:
        # Try for a previous tag name
        if "+" not in tags:
            try:
                previous = PreviousTagName.objects.get(previous_name=tags)
            except PreviousTagName.DoesNotExist:
                raise Http404
            return Redirect("/tag/%s/" % previous.tag.tag)

        raise Http404
    tags = tags_
    items = []
    from django.db import connection

    cursor = connection.cursor()
    for model, content_type in (
        (Entry, "entry"),
        (Quotation, "quotation"),
        (Blogmark, "blogmark"),
        (Note, "note"),
        (Beat, "beat"),
    ):
        cursor.execute(
            INTERSECTION_SQL
            % {
                "content_table": "blog_%s" % content_type,
                "tag_table": "blog_%s_tags" % content_type,
                "tag_table_content_key": "%s_id" % content_type,
                "joined_tags": ", ".join(["'%s'" % tag for tag in tags]),
                "tag_count": len(tags),
            }
        )
        ids = [r[0] for r in cursor.fetchall()]
        items.extend(
            [
                {"type": content_type, "obj": obj}
                for obj in list(
                    model.objects.prefetch_related("tags").in_bulk(ids).values()
                )
            ]
        )
    if not items:
        raise Http404
    items.sort(key=lambda x: x["obj"].created, reverse=True)
    # Paginate it
    paginator = Paginator(items, min(1000, int(request.GET.get("size") or "30")))
    page_number = request.GET.get("page") or "1"
    if page_number == "last":
        page_number = paginator.num_pages
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        raise Http404
    except EmptyPage:
        raise Http404

    if atom:
        response = EverythingTagged(
            ", ".join(tags), (item["obj"] for item in page.object_list)
        )(request)
        # Pagination in link: header
        if page.has_next():
            query_dict = request.GET.copy()
            query_dict["page"] = str(page.next_page_number())
            next_url = request.path + "?" + query_dict.urlencode()
            response["link"] = '<{}>; rel="next"'.format(next_url)
        return response

    return render(
        request,
        "archive_tag.html",
        {
            "tags": tags,
            "items": page.object_list,
            "total": paginator.count,
            "page": page,
            "only_one_tag": len(tags) == 1,
            "tag": Tag.objects.get(tag=tags[0]),
        },
    )


def archive_tag_atom(request, tags):
    return archive_tag(request, tags, atom=True)


def series_index(request):
    return render(
        request,
        "series_index.html",
        {
            "all_series": Series.objects.all().annotate(
                num_entries=models.Count("entry")
            ),
        },
    )


def archive_series(request, slug):
    series = get_object_or_404(Series, slug=slug)
    return render(
        request,
        "archive_series.html",
        {
            "series": series,
            "items": [
                {"type": "entry", "obj": obj}
                for obj in series.entry_set.order_by("created").prefetch_related("tags")
            ],
        },
    )


def archive_series_atom(request, slug):
    from .feeds import SeriesFeed

    series = get_object_or_404(Series, slug=slug)
    return SeriesFeed(series)(request)


def guide_index(request):
    return render(
        request,
        "guide_index.html",
        {
            "guides": Guide.objects.filter(is_draft=False)
            .annotate(
                num_chapters=models.Count(
                    "chapters", filter=models.Q(chapters__is_draft=False)
                )
            )
            .prefetch_related(
                models.Prefetch(
                    "chapters",
                    queryset=Chapter.objects.filter(is_draft=False).order_by(
                        "order", "created"
                    ),
                    to_attr="visible_chapters",
                )
            ),
        },
    )


def guide_detail(request, slug):
    if request.user.is_staff:
        guide = get_object_or_404(Guide, slug=slug)
    else:
        guide = get_object_or_404(Guide, slug=slug, is_draft=False)
    chapters = guide.chapters.filter(is_draft=False).order_by("order", "created")
    if request.user.is_staff:
        chapters = guide.chapters.order_by("order", "created")
    return render(
        request,
        "guide_detail.html",
        {
            "guide": guide,
            "chapters": chapters,
        },
    )


def chapter_detail(request, guide_slug, chapter_slug):
    if request.user.is_staff:
        guide = get_object_or_404(Guide, slug=guide_slug)
        chapter = get_object_or_404(Chapter, guide=guide, slug=chapter_slug)
    else:
        guide = get_object_or_404(Guide, slug=guide_slug, is_draft=False)
        chapter = get_object_or_404(
            Chapter, guide=guide, slug=chapter_slug, is_draft=False
        )
    all_chapters = list(
        guide.chapters.filter(is_draft=False).order_by("order", "created")
    )
    if request.user.is_staff:
        all_chapters = list(guide.chapters.order_by("order", "created"))
    current_index = None
    for i, ch in enumerate(all_chapters):
        if ch.pk == chapter.pk:
            current_index = i
            break
    previous_chapter = (
        all_chapters[current_index - 1] if current_index and current_index > 0 else None
    )
    next_chapter = (
        all_chapters[current_index + 1]
        if current_index is not None and current_index < len(all_chapters) - 1
        else None
    )
    return render(
        request,
        "chapter_detail.html",
        {
            "guide": guide,
            "chapter": chapter,
            "previous_chapter": previous_chapter,
            "next_chapter": next_chapter,
        },
    )


@never_cache
@staff_member_required
def write(request):
    return render(request, "write.html")


@never_cache
@staff_member_required
def tools(request):
    if request.POST.get("purge_all"):
        cf = cloudflare.CloudFlare(
            email=settings.CLOUDFLARE_EMAIL, token=settings.CLOUDFLARE_TOKEN
        )
        cf.zones.purge_cache.delete(
            settings.CLOUDFLARE_ZONE_ID, data={"purge_everything": True}
        )
        return Redirect(request.path + "?msg=Cache+purged")
    return render(
        request,
        "tools.html",
        {
            "msg": request.GET.get("msg"),
            "deployed_hash": os.environ.get("HEROKU_SLUG_COMMIT"),
        },
    )


@never_cache
@staff_member_required
def tools_extract_title(request):
    url = request.GET.get("url", "")
    if url:
        soup = Soup(requests.get(url).content, "html5lib")
        title = ""
        title_el = soup.find("title")
        if title_el:
            title = title_el.text
        return JsonResponse(
            {
                "title": title,
            }
        )
    return JsonResponse({})


# Redirects for ancient patterns
# /archive/2002/10/24/
def archive_day_redirect(request, yyyy, mm, dd):
    return Redirect("/%s/%s/%d/" % (yyyy, MONTHS_3_REV_REV[int(mm)].title(), int(dd)))


# /archive/2003/09/05/listamatic
def archive_item_redirect(request, yyyy, mm, dd, slug):
    return Redirect(
        "/%s/%s/%d/%s" % (yyyy, MONTHS_3_REV_REV[int(mm)].title(), int(dd), slug)
    )


# For use with datasette-auth-existing-cookies
@never_cache
def user_from_cookies(request):
    if not request.user.is_authenticated:
        return JsonResponse({})
    return JsonResponse(
        {
            "id": request.user.id,
            "username": request.user.username,
            "name": request.user.get_full_name(),
            "is_staff": request.user.is_staff,
            "is_superuser": request.user.is_superuser,
        }
    )


def redirect_entry(request, pk):
    return Redirect(get_object_or_404(Entry, pk=pk).get_absolute_url())


def redirect_blogmark(request, pk):
    return Redirect(get_object_or_404(Blogmark, pk=pk).get_absolute_url())


def redirect_quotation(request, pk):
    return Redirect(get_object_or_404(Quotation, pk=pk).get_absolute_url())


def redirect_note(request, pk):
    return Redirect(get_object_or_404(Note, pk=pk).get_absolute_url())


def redirect_beat(request, pk):
    return Redirect(get_object_or_404(Beat, pk=pk).get_absolute_url())


def random_tag_redirect(request, tag):
    """
    Redirect to a random item (entry, blogmark, quotation, or note) with the given tag.
    Uses no-cache headers so Cloudflare doesn't cache the redirect.
    """
    from django.db import connection

    tag_obj = get_object_or_404(Tag, tag=tag)

    # Use a CTE to efficiently select one random item from all content types
    # This avoids loading all items into memory for tags with thousands of items
    sql = """
    WITH all_items AS (
        SELECT id AS pk, 'entry' AS type FROM blog_entry
        WHERE is_draft = false AND id IN (
            SELECT entry_id FROM blog_entry_tags WHERE tag_id = %s
        )
        UNION ALL
        SELECT id AS pk, 'blogmark' AS type FROM blog_blogmark
        WHERE is_draft = false AND id IN (
            SELECT blogmark_id FROM blog_blogmark_tags WHERE tag_id = %s
        )
        UNION ALL
        SELECT id AS pk, 'quotation' AS type FROM blog_quotation
        WHERE is_draft = false AND id IN (
            SELECT quotation_id FROM blog_quotation_tags WHERE tag_id = %s
        )
        UNION ALL
        SELECT id AS pk, 'note' AS type FROM blog_note
        WHERE is_draft = false AND id IN (
            SELECT note_id FROM blog_note_tags WHERE tag_id = %s
        )
        UNION ALL
        SELECT id AS pk, 'beat' AS type FROM blog_beat
        WHERE is_draft = false AND id IN (
            SELECT beat_id FROM blog_beat_tags WHERE tag_id = %s
        )
    )
    SELECT pk, type FROM all_items ORDER BY RANDOM() LIMIT 1
    """

    with connection.cursor() as cursor:
        cursor.execute(
            sql, [tag_obj.pk, tag_obj.pk, tag_obj.pk, tag_obj.pk, tag_obj.pk]
        )
        row = cursor.fetchone()

    if not row:
        raise Http404("No items found with this tag")

    item_pk, item_type = row

    # Load the actual object
    model_map = {
        "entry": Entry,
        "blogmark": Blogmark,
        "quotation": Quotation,
        "note": Note,
        "beat": Beat,
    }
    model = model_map[item_type]
    obj = get_object_or_404(model, pk=item_pk)

    # Redirect with no-cache headers
    from django.http import HttpResponseRedirect

    response = HttpResponseRedirect(obj.get_absolute_url())
    set_no_cache(response)
    return response


def about(request):
    return render(request, "about.html")


def custom_404(request, exception):
    return render(
        request,
        "404.html",
        {"q": [b.strip() for b in request.path.split("/") if b.strip()][-1]},
        status=404,
    )


@staff_member_required
@never_cache
def bulk_tag(request):
    """
    Admin-only view for bulk tagging search results.
    Reuses the search functionality but renders a custom template with tagging UI.
    """
    from blog import search as search_views

    context = search_views.search(request, return_context=True, per_page=200)
    return render(request, "bulk_tag.html", context)


@require_POST
@staff_member_required
def api_add_tag(request):
    """
    API endpoint to handle adding a tag to an object.
    Expects content_type, object_id, and tag in the POST data.
    """
    content_type = request.POST.get("content_type")
    object_id = request.POST.get("object_id")
    tag_name = request.POST.get("tag")

    # Validate inputs
    if not content_type or not object_id or not tag_name:
        return JsonResponse({"error": "Missing required parameters"}, status=400)

    # Get the object
    model = {
        "entry": Entry,
        "blogmark": Blogmark,
        "quotation": Quotation,
        "note": Note,
        "beat": Beat,
    }.get(content_type)
    if not model:
        return JsonResponse({"error": "Invalid content type"}, status=400)

    try:
        obj = model.objects.get(pk=object_id)
    except model.DoesNotExist:
        return JsonResponse({"error": "Object not found"}, status=404)

    # Get or create the tag
    tag = Tag.objects.get_or_create(tag=tag_name)[0]

    # Add the tag to the object
    obj.tags.add(tag)

    return JsonResponse({"success": True, "tag": tag_name})


@staff_member_required
@never_cache
def merge_tags(request):
    """
    Admin-only view for merging two tags.
    Shows a confirmation screen with counts before merging.
    """
    source_tag = None
    destination_tag = None
    error = None
    success = None

    source_tag_name = request.GET.get("source") or request.POST.get("source")
    destination_tag_name = request.GET.get("destination") or request.POST.get(
        "destination"
    )

    # Look up the tags if specified
    if source_tag_name:
        try:
            source_tag = Tag.objects.get(tag=source_tag_name)
        except Tag.DoesNotExist:
            error = f"Source tag '{source_tag_name}' not found"

    if destination_tag_name:
        try:
            destination_tag = Tag.objects.get(tag=destination_tag_name)
        except Tag.DoesNotExist:
            error = f"Destination tag '{destination_tag_name}' not found"

    # Validate that they're different
    if source_tag and destination_tag and source_tag.pk == destination_tag.pk:
        error = "Source and destination tags must be different"
        source_tag = None
        destination_tag = None

    # Handle POST request (perform the merge)
    if request.method == "POST" and source_tag and destination_tag and not error:
        if request.POST.get("confirm") == "yes":
            # Track items where tag was added vs just removed
            details = {
                "entries": {"added": [], "already_tagged": []},
                "blogmarks": {"added": [], "already_tagged": []},
                "quotations": {"added": [], "already_tagged": []},
                "notes": {"added": [], "already_tagged": []},
            }

            # Re-tag all content from source to destination
            for entry in Entry.objects.filter(tags=source_tag):
                already_has_dest = destination_tag in entry.tags.all()
                entry.tags.remove(source_tag)
                if already_has_dest:
                    details["entries"]["already_tagged"].append(entry.pk)
                else:
                    entry.tags.add(destination_tag)
                    details["entries"]["added"].append(entry.pk)

            for blogmark in Blogmark.objects.filter(tags=source_tag):
                already_has_dest = destination_tag in blogmark.tags.all()
                blogmark.tags.remove(source_tag)
                if already_has_dest:
                    details["blogmarks"]["already_tagged"].append(blogmark.pk)
                else:
                    blogmark.tags.add(destination_tag)
                    details["blogmarks"]["added"].append(blogmark.pk)

            for quotation in Quotation.objects.filter(tags=source_tag):
                already_has_dest = destination_tag in quotation.tags.all()
                quotation.tags.remove(source_tag)
                if already_has_dest:
                    details["quotations"]["already_tagged"].append(quotation.pk)
                else:
                    quotation.tags.add(destination_tag)
                    details["quotations"]["added"].append(quotation.pk)

            for note in Note.objects.filter(tags=source_tag):
                already_has_dest = destination_tag in note.tags.all()
                note.tags.remove(source_tag)
                if already_has_dest:
                    details["notes"]["already_tagged"].append(note.pk)
                else:
                    note.tags.add(destination_tag)
                    details["notes"]["added"].append(note.pk)

            # Create PreviousTagName for redirect
            PreviousTagName.objects.create(
                tag=destination_tag, previous_name=source_tag.tag
            )

            # Record the merge
            TagMerge.objects.create(
                source_tag_name=source_tag.tag,
                destination_tag=destination_tag,
                destination_tag_name=destination_tag.tag,
                details=details,
            )

            # Calculate totals for success message
            total_removed = sum(
                len(details[k]["added"]) + len(details[k]["already_tagged"])
                for k in details
            )
            total_added = sum(len(details[k]["added"]) for k in details)
            total_already = sum(len(details[k]["already_tagged"]) for k in details)

            # Delete the source tag
            source_tag_name_for_message = source_tag.tag
            source_tag.delete()

            success_parts = [
                f"Successfully merged '{source_tag_name_for_message}' into "
                f"'{destination_tag.tag}'. "
            ]
            if total_added:
                success_parts.append(
                    f"Added '{destination_tag.tag}' tag to {total_added} item(s). "
                )
            if total_already:
                success_parts.append(
                    f"Removed '{source_tag_name_for_message}' from {total_already} item(s) "
                    f"that already had '{destination_tag.tag}'."
                )
            if not total_added and not total_already:
                success_parts.append("No items were affected.")

            success = "".join(success_parts)
            source_tag = None
            destination_tag = None

    # Calculate counts for confirmation screen
    counts = None
    if source_tag and destination_tag:
        # Count items with source tag that DON'T have destination tag (will be added)
        # Count items with source tag that DO have destination tag (already tagged)
        counts = {
            "entries": {
                "total": source_tag.entry_set.count(),
                "will_add": source_tag.entry_set.exclude(tags=destination_tag).count(),
            },
            "blogmarks": {
                "total": source_tag.blogmark_set.count(),
                "will_add": source_tag.blogmark_set.exclude(
                    tags=destination_tag
                ).count(),
            },
            "quotations": {
                "total": source_tag.quotation_set.count(),
                "will_add": source_tag.quotation_set.exclude(
                    tags=destination_tag
                ).count(),
            },
            "notes": {
                "total": source_tag.note_set.count(),
                "will_add": source_tag.note_set.exclude(tags=destination_tag).count(),
            },
        }
        for k in counts:
            counts[k]["already_tagged"] = counts[k]["total"] - counts[k]["will_add"]
        counts["total"] = sum(
            c["total"] for c in counts.values() if isinstance(c, dict)
        )
        counts["total_will_add"] = sum(
            c["will_add"] for c in counts.values() if isinstance(c, dict)
        )
        counts["total_already_tagged"] = sum(
            c["already_tagged"] for c in counts.values() if isinstance(c, dict)
        )

    return render(
        request,
        "merge_tags.html",
        {
            "source_tag": source_tag,
            "destination_tag": destination_tag,
            "source_tag_name": source_tag_name or "",
            "destination_tag_name": destination_tag_name or "",
            "counts": counts,
            "error": error,
            "success": success,
        },
    )


IMPORTERS = {
    "releases": {
        "name": "Releases",
        "description": "Import latest releases from releases_cache.json",
        "url": "https://raw.githubusercontent.com/simonw/simonw/refs/heads/main/releases_cache.json",
    },
    "research": {
        "name": "Research",
        "description": "Import research projects from README.md",
        "url": "https://raw.githubusercontent.com/simonw/research/refs/heads/main/README.md",
    },
    "tils": {
        "name": "TILs",
        "description": "Import TILs from til.simonwillison.net",
        "url": (
            "https://til.simonwillison.net/tils.json?sql=select+path%2C+topic%2C+title"
            "%2C+url%2C+body%2C+html%2C+created%2C+created_utc%2C+updated%2C+updated_utc"
            "%2C+shot_hash%2C+slug%2C+summary+from+til+order+by+updated_utc&_size=1000&_shape=array"
        ),
    },
    "tools": {
        "name": "Tools",
        "description": "Import tools from tools.simonwillison.net",
        "url": "https://tools.simonwillison.net/tools.json",
    },
    "museums": {
        "name": "Museums",
        "description": "Import museums from niche-museums.com",
        "url": "https://www.niche-museums.com/museums.json",
    },
}


@staff_member_required
@never_cache
def importers(request):
    return render(request, "importers.html", {"importers": IMPORTERS})


@require_POST
@staff_member_required
def api_run_importer(request):
    import json as json_module
    from django.template.loader import render_to_string
    from blog.importers import (
        import_museums,
        import_releases,
        import_research,
        import_tils,
        import_tools,
    )

    try:
        body = json_module.loads(request.body)
    except (json_module.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    importer_name = body.get("importer")
    if importer_name not in IMPORTERS:
        return JsonResponse({"error": "Unknown importer"}, status=400)

    importer_funcs = {
        "releases": import_releases,
        "research": import_research,
        "tils": import_tils,
        "tools": import_tools,
        "museums": import_museums,
    }

    try:
        result = importer_funcs[importer_name](IMPORTERS[importer_name]["url"])
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

    items = result["items"]
    total = len(items)
    display_items = items[:10]

    items_html = render_to_string(
        "includes/importer_results.html", {"items": display_items}
    )

    return JsonResponse(
        {
            "created": result.get("created", 0),
            "updated": result.get("updated", 0),
            "skipped": result.get("skipped", 0),
            "total": total,
            "items_html": items_html,
        }
    )


# Hide vertical scrollbar, add fade at bottom of viewport
SCREENSHOT_EXTRA_CSS = """
::-webkit-scrollbar {
  display: none;
}
body::after {
  content: "";
  position: fixed;
  left: 0;
  bottom: 0;
  width: 100%;
  height: 20px;
  pointer-events: none;
  background: linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0),
    rgba(255, 255, 255, 1)
  );
}
html {
  margin: 0 10px;
}
#smallhead {
  margin-right: -10px;
  margin-left: -10px;
}
html div#smallhead #smallhead-inner {
  padding-left: 25px;
  padding-right: 10px;
}
"""


def screenshot_card(request, path):
    raise Http404("Card not enabled")
    # Fetch HTML for this path, to use as the version
    response = Client().get("/" + path)
    # response must have x-enable-card header
    if not response.headers.get("x-enable-card"):
        raise Http404("Card not enabled")
    if response.status_code != 200:
        raise Http404("Page not found")
    html_bytes = response.content
    if not getattr(settings, "SCREENSHOT_SECRET", None):
        raise Http404("SCREENSHOT_SECRET is not set")
    screenshot_url = generate_screenshot_url(
        "https://screenshot-worker.simonw.workers.dev/",
        "https://simonwillison.net/" + path,
        hashlib.sha256(html_bytes).hexdigest(),
        secret=settings.SCREENSHOT_SECRET,
        width="700",
        height="350",
        css=SCREENSHOT_EXTRA_CSS,
    )
    # Proxy fetch that URL, so Cloudflare can cache it
    screenshot_bytes = requests.get(screenshot_url).content
    # Return with cache header
    response = HttpResponse(
        screenshot_bytes,
        content_type="image/png",
    )
    response["Cache-Control"] = "s-maxage={}".format(365 * 60 * 60)
    return response


def generate_screenshot_url(
    worker_url: str,
    target_url: str,
    version: str,
    secret: str,
    *,
    width: str = "1200",
    height: str = "800",
    js: str = "",
    css: str = "",
) -> str:
    """
    Build a **signed** screenshot URL (now supports inline JS/CSS injection).

    Parameters
    ----------
    js, css : str
        JavaScript and CSS strings to inject with `addScriptTag` / `addStyleTag`.
        Empty strings (default) mean “none”.
    """
    width, height = str(width), str(height)
    # ---- (dimension validation unchanged) ---- #

    message = _make_message(target_url, version, width, height, js, css)
    signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    params = {
        "url": target_url,
        "version": version,
        "w": width,
        "h": height,
        "js": js,
        "css": css,
        "sig": signature,
    }
    return f"{worker_url.rstrip('/')}/?{urlencode(params, safe='')}"


def _make_message(
    target_url: str, version: str, width: str, height: str, js: str, css: str
) -> str:
    """Message string that must exactly match the Worker implementation."""
    return f"{target_url}|{version}|{width}|{height}|{js}|{css}"
