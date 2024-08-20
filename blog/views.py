# coding=utf8
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.cache import never_cache
from django.db import models
from django.db.models import CharField, Value
from django.conf import settings
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.http import Http404, HttpResponsePermanentRedirect as Redirect
from .models import (
    Blogmark,
    Entry,
    Quotation,
    Photo,
    Photoset,
    Series,
    Tag,
    PreviousTagName,
)
import requests
from bs4 import BeautifulSoup as Soup
import datetime
import random
from collections import Counter
import cloudflare
import os

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


def archive_item(request, year, month, day, slug):
    if day.startswith("0"):
        day = day.lstrip("0")
        return Redirect("/%s/%s/%s/%s/" % (year, month, day, slug))

    # This could be a quote OR link OR entry
    for content_type, model in (
        ("blogmark", Blogmark),
        ("entry", Entry),
        ("quotation", Quotation),
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

        return render(
            request,
            template,
            {
                content_type: obj,
                "content_type": content_type,
                "object_id": obj.id,
                "previously_hosted": previously_hosted,
                "item": obj,
                "recent_articles": Entry.objects.prefetch_related("tags").order_by(
                    "-created"
                )[0:3],
            },
        )

    # If we get here, non of the views matched
    raise Http404


def index(request):
    # Get back 30 most recent across all item types
    recent = list(
        Entry.objects.annotate(content_type=Value("entry", output_field=CharField()))
        .values("content_type", "id", "created")
        .order_by()
        .union(
            Blogmark.objects.annotate(
                content_type=Value("blogmark", output_field=CharField())
            )
            .values("content_type", "id", "created")
            .order_by()
        )
        .union(
            Quotation.objects.annotate(
                content_type=Value("quotation", output_field=CharField())
            )
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
    ):
        if content_type not in to_load:
            continue
        items.extend(
            [
                {"type": content_type, "obj": obj}
                for obj in model.objects.in_bulk(to_load[content_type]).values()
            ]
        )

    items.sort(key=lambda x: x["obj"].created, reverse=True)

    response = render(
        request,
        "homepage.html",
        {
            "items": items,
            "entries": Entry.objects.only(
                "id", "slug", "created", "title", "extra_head_html"
            ).prefetch_related("tags")[0:40],
            "current_tags": find_current_tags(5),
        },
    )
    response["Cache-Control"] = "s-maxage=200"
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
            created__year=year, created__month=month
        ).count()
        link_count = Blogmark.objects.filter(
            created__year=year, created__month=month
        ).count()
        quote_count = Quotation.objects.filter(
            created__year=year, created__month=month
        ).count()
        photo_count = Photo.objects.filter(
            created__year=year, created__month=month
        ).count()
        month_count = entry_count + link_count + quote_count + photo_count
        if month_count:
            counts = [
                ("entry", entry_count),
                ("link", link_count),
                ("photo", photo_count),
                ("quote", quote_count),
            ]
            counts_not_0 = [p for p in counts if p[1]]
            months.append(
                {
                    "date": date,
                    "counts": counts,
                    "counts_not_0": counts_not_0,
                    "entries": list(
                        Entry.objects.filter(
                            created__year=year, created__month=month
                        ).order_by("created")
                    ),
                }
            )
            max_count = max(
                max_count, entry_count, link_count, quote_count, photo_count
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
    from django.db import connection

    cursor = connection.cursor()
    for model, content_type in (
        (Entry, "entry"),
        (Quotation, "quotation"),
        (Blogmark, "blogmark"),
    ):
        ids = model.objects.filter(
            created__year=year, created__month=month
        ).values_list("id", flat=True)
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
        },
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
        ("photo", Photo),
    ):
        filt = model.objects.filter(
            created__year=int(year),
            created__month=MONTHS_3_REV[month.lower()],
            created__day=int(day),
        ).order_by("created")
        if name == "photo":
            filt = filt[:25]
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
    return render(request, "archive_day.html", context)


def tag_index(request):
    return render(request, "tags.html")


# This query gets the IDs of things that match all of the tags
INTERSECTION_SQL = """
    SELECT %(content_table)s.id
        FROM %(content_table)s, %(tag_table)s
    WHERE %(tag_table)s.tag_id IN (
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


def about(request):
    return render(request, "about.html")


def custom_404(request, exception):
    return render(
        request,
        "404.html",
        {"q": [b.strip() for b in request.path.split("/") if b.strip()][-1]},
        status=404,
    )
