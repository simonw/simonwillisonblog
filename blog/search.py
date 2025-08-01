import time
import json
import re
import calendar
from django.db import models
from django.db.models.functions import TruncYear, TruncMonth
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, Http404
from django.shortcuts import render
from blog.models import Entry, Blogmark, Quotation, Note, Tag, load_mixed_objects
from spellchecker import SpellChecker
import datetime


_spell = None


def get_spellchecker():
    global _spell
    if _spell is None:
        _spell = SpellChecker()
        # Load all tags into the spellchecker
        tag_words = set()
        for tag in Tag.objects.values_list("tag", flat=True):
            tag_words.update(tag.split("-"))
        _spell.word_frequency.load_words(tag_words)
    return _spell


def get_suggestion(phrase):
    words = phrase.split()
    spell = get_spellchecker()
    unknown = spell.unknown(words)
    if not unknown:
        return phrase
    new_words = []
    for word in words:
        if word in unknown:
            suggestion = spell.correction(word)
            if suggestion:
                new_words.append(suggestion)
            else:
                new_words.append(word)
        else:
            new_words.append(word)
    return " ".join(new_words)


def parse_date_clauses(query):
    from_date = None
    to_date = None
    from_match = re.search(r"from:(\d{4}-\d{2}-\d{2})", query)
    to_match = re.search(r"to:(\d{4}-\d{2}-\d{2})", query)
    if from_match:
        from_date = datetime.datetime.strptime(from_match.group(1), "%Y-%m-%d").date()
    if to_match:
        to_date = datetime.datetime.strptime(to_match.group(1), "%Y-%m-%d").date()
    query = re.sub(r"from:\d{4}-\d{2}-\d{2}", "", query)
    query = re.sub(r"to:\d{4}-\d{2}-\d{2}", "", query)
    return query.strip(), from_date, to_date


def search(request, q=None, return_context=False):
    q = (q or request.GET.get("q", "")).strip()
    search_q, from_date, to_date = parse_date_clauses(q)
    search_q = search_q.strip()
    start = time.time()

    query = None
    rank_annotation = None
    if search_q:
        query = SearchQuery(search_q, search_type="websearch")
        rank_annotation = SearchRank(models.F("search_document"), query)

    selected_tags = request.GET.getlist("tag")

    if len(selected_tags) > 2:
        return HttpResponse("Too many tags", status=400)

    excluded_tags = request.GET.getlist("exclude.tag")
    selected_type = request.GET.get("type", "")
    selected_year = request.GET.get("year", "")
    selected_month = request.GET.get("month", "")

    values = ["pk", "type", "created"]
    if search_q:
        values.append("rank")

    def make_queryset(klass, type_name):
        qs = klass.objects.filter(is_draft=False).annotate(
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
        if from_date:
            qs = qs.filter(created__gte=from_date)
        if to_date:
            qs = qs.filter(created__lt=to_date)
        if search_q:
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
    if search_q:
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
        (Note, "note"),
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
        if search_q:
            sort = "relevance"
        else:
            sort = "date"

    # can't sort by relevance if there's no search_q
    if sort == "relevance" and not search_q:
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
        "month_name": (
            calendar.month_name[int(selected_month)] if selected_month.isdigit() else ""
        ),
        "from_date": from_date,
        "to_date": to_date,
    }
    # Remove empty keys
    selected = {key: value for key, value in list(selected.items()) if value}

    # Dynamic title
    noun = {
        "quotation": "Quotations",
        "blogmark": "Blogmarks",
        "entry": "Entries",
        "note": "Notes",
    }.get(selected.get("type")) or "Posts"
    title = noun

    if search_q:
        title = "“%s” in %s" % (search_q, title.lower())

    if selected.get("tags"):
        title += " tagged %s" % (", ".join(selected["tags"]))

    datebits = []
    if selected.get("month_name"):
        datebits.append(selected["month_name"])
    if selected.get("year"):
        datebits.append(selected["year"])
    if datebits:
        title += " in %s" % (", ".join(datebits))

    if from_date or to_date:
        date_range = []
        if from_date:
            date_range.append(f"from {from_date}")
        if to_date:
            date_range.append(f"to {to_date}")
        title += " " + " ".join(date_range)

    if not search_q and not selected:
        title = "Search"

    # if no results, count how many a spell-corrected search would get
    suggestion = None
    num_corrected_results = 0
    if not results and search_q and not return_context:
        suggestion = get_suggestion(search_q)
        corrected_context = search(request, suggestion, return_context=True)
        num_corrected_results = corrected_context["total"]

    context = {
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
        "suggestion": suggestion,
        "num_corrected_results": num_corrected_results,
    }

    if return_context:
        return context
    else:
        return render(request, "search.html", context)


def tools_search_tags(request):
    q = request.GET.get("q", "").strip()
    results = []
    if q:
        results = list(
            Tag.objects.filter(tag__icontains=q).values_list("tag", flat=True)
        )
        results.sort(key=lambda t: len(t))
    return HttpResponse(json.dumps({"tags": results}), content_type="application/json")
