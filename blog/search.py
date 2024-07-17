import time
import json
from django.db import models
from django.db.models.functions import TruncYear, TruncMonth
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, Http404
from django.shortcuts import render
from blog.models import Entry, Blogmark, Quotation, Tag, load_mixed_objects
from .views import MONTHS_3_REV_REV


def search(request):
    q = request.GET.get("q", "").strip()
    start = time.time()

    query = None
    rank_annotation = None
    if q:
        query = SearchQuery(q, search_type="websearch")
        rank_annotation = SearchRank(models.F("search_document"), query)

    selected_tags = request.GET.getlist("tag")

    if len(selected_tags) > 2:
        return HttpResponse("Too many tags", status=400)

    excluded_tags = request.GET.getlist("exclude.tag")
    selected_type = request.GET.get("type", "")
    selected_year = request.GET.get("year", "")
    selected_month = request.GET.get("month", "")

    values = ["pk", "type", "created"]
    if q:
        values.append("rank")

    def make_queryset(klass, type_name):
        qs = klass.objects.annotate(
            type=models.Value(type_name, output_field=models.CharField())
        )
        if selected_year and selected_year.isdigit() and 2000 <= int(selected_year):
            qs = qs.filter(created__year=int(selected_year))
        if (
            selected_month
            and selected_month.isdigit()
            and 1 <= int(selected_month) <= 12
        ):
            qs = qs.filter(created__month=int(selected_month))
        if q:
            qs = qs.filter(search_document=query)
            qs = qs.annotate(rank=rank_annotation)
        for tag in selected_tags:
            qs = qs.filter(tags__tag=tag)
        for exclude_tag in excluded_tags:
            qs = qs.exclude(tags__tag=exclude_tag)
        return qs.order_by()

    # Start with a .none() queryset just so we can union stuff onto it
    qs = Entry.objects.annotate(
        type=models.Value("empty", output_field=models.CharField())
    )
    if q:
        qs = qs.annotate(rank=rank_annotation)
    qs = qs.values(*values).none()

    type_counts_raw = {}
    tag_counts_raw = {}
    year_counts_raw = {}
    month_counts_raw = {}

    for klass, type_name in (
        (Entry, "entry"),
        (Blogmark, "blogmark"),
        (Quotation, "quotation"),
    ):
        if selected_type and selected_type != type_name:
            continue
        klass_qs = make_queryset(klass, type_name)
        type_count = klass_qs.count()
        if type_count:
            type_counts_raw[type_name] = type_count
        for tag, count in (
            Tag.objects.filter(**{"%s__in" % type_name: klass_qs})
            .annotate(n=models.Count("tag"))
            .values_list("tag", "n")
        ):
            tag_counts_raw[tag] = tag_counts_raw.get(tag, 0) + count
        for row in (
            klass_qs.order_by()
            .annotate(year=TruncYear("created"))
            .values("year")
            .annotate(n=models.Count("pk"))
        ):
            year_counts_raw[row["year"]] = (
                year_counts_raw.get(row["year"], 0) + row["n"]
            )
        # Only do month counts if a year is selected
        if selected_year:
            for row in (
                klass_qs.order_by()
                .annotate(month=TruncMonth("created"))
                .values("month")
                .annotate(n=models.Count("pk"))
            ):
                month_counts_raw[row["month"]] = (
                    month_counts_raw.get(row["month"], 0) + row["n"]
                )
        qs = qs.union(klass_qs.values(*values))

    sort = request.GET.get("sort")
    if sort not in ("relevance", "date"):
        sort = None

    if sort is None:
        if q:
            sort = "relevance"
        else:
            sort = "date"

    # can't sort by relevance if there's no q
    if sort == "relevance" and not q:
        sort = "date"

    db_sort = {"relevance": "-rank", "date": "-created"}[sort]
    qs = qs.order_by(db_sort)

    type_counts = sorted(
        [
            {"type": type_name, "n": value}
            for type_name, value in list(type_counts_raw.items())
        ],
        key=lambda t: t["n"],
        reverse=True,
    )
    tag_counts = sorted(
        [{"tag": tag, "n": value} for tag, value in list(tag_counts_raw.items())],
        key=lambda t: t["n"],
        reverse=True,
    )[:40]

    year_counts = sorted(
        [{"year": year, "n": value} for year, value in list(year_counts_raw.items())],
        key=lambda t: t["year"],
    )

    month_counts = sorted(
        [
            {"month": month, "n": value}
            for month, value in list(month_counts_raw.items())
        ],
        key=lambda t: t["month"],
    )

    paginator = Paginator(qs, 30)
    page_number = request.GET.get("page") or "1"
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        raise Http404
    except EmptyPage:
        raise Http404

    results = []
    for obj in load_mixed_objects(page.object_list):
        results.append(
            {
                "type": obj.original_dict["type"],
                "rank": obj.original_dict.get("rank"),
                "obj": obj,
            }
        )
    end = time.time()

    selected = {
        "tags": selected_tags,
        "year": selected_year,
        "month": selected_month,
        "type": selected_type,
        "month_name": MONTHS_3_REV_REV.get(
            selected_month and int(selected_month) or "", ""
        ).title(),
    }
    # Remove empty keys
    selected = {key: value for key, value in list(selected.items()) if value}

    # Dynamic title
    noun = {
        "quotation": "Quotations",
        "blogmark": "Blogmarks",
        "entry": "Entries",
    }.get(selected.get("type")) or "Items"
    title = noun

    if q:
        title = "“%s” in %s" % (q, title.lower())

    if selected.get("tags"):
        title += " tagged %s" % (", ".join(selected["tags"]))

    datebits = []
    if selected.get("month_name"):
        datebits.append(selected["month_name"])
    if selected.get("year"):
        datebits.append(selected["year"])
    if datebits:
        title += " in %s" % (", ".join(datebits))

    if not q and not selected:
        title = "Search"

    return render(
        request,
        "search.html",
        {
            "q": q,
            "sort": sort,
            "title": title,
            "results": results,
            "total": paginator.count,
            "page": page,
            "duration": end - start,
            "type_counts": type_counts,
            "tag_counts": tag_counts,
            "year_counts": year_counts,
            "month_counts": month_counts,
            "selected_tags": selected_tags,
            "excluded_tags": excluded_tags,
            "selected": selected,
        },
    )


def tools_search_tags(request):
    q = request.GET.get("q", "").strip()
    results = []
    if q:
        results = list(
            Tag.objects.filter(tag__icontains=q).values_list("tag", flat=True)
        )
        results.sort(key=lambda t: len(t))
    return HttpResponse(json.dumps({"tags": results}), content_type="application/json")
