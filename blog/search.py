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
from blog.models import Beat, Entry, Blogmark, Quotation, Note, Tag, load_mixed_objects
from guides.models import Chapter
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


def search(request, q=None, return_context=False, per_page=30):
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
    selected_beat = request.GET.get("beat", "")

    # Support type=beat:release etc. - parse into selected_beat_subtype
    selected_beat_subtype = ""
    if selected_type.startswith("beat:"):
        selected_beat_subtype = selected_type[5:]  # e.g. "release"

    # Parse ID filters: entries=1,2,3&notes=4,5&quotations=6&blogmarks=7,8
    id_filter_param_map = {
        "entries": "entry",
        "blogmarks": "blogmark",
        "quotations": "quotation",
        "notes": "note",
        "beats": "beat",
        "chapters": "chapter",
    }
    id_filters = {}  # type_name -> set of int IDs
    for param, type_name in id_filter_param_map.items():
        raw = request.GET.get(param, "").strip()
        if raw:
            ids = set()
            for part in raw.split(","):
                part = part.strip()
                if part.isdigit():
                    ids.add(int(part))
            if ids:
                id_filters[type_name] = ids
    has_id_filters = bool(id_filters)

    values = ["pk", "type", "created"]
    if search_q:
        values.append("rank")

    def make_queryset(klass, type_name):
        qs = klass.objects.filter(is_draft=False).annotate(
            type=models.Value(type_name, output_field=models.CharField())
        )
        if klass == Chapter:
            qs = qs.filter(guide__is_draft=False)
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
        if selected_beat and type_name == "beat":
            qs = qs.filter(beat_type=selected_beat)
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
    beat_type_counts_raw = {}

    for klass, type_name, tag_filter_name in (
        (Entry, "entry", "entry"),
        (Blogmark, "blogmark", "blogmark"),
        (Quotation, "quotation", "quotation"),
        (Note, "note", "note"),
        (Beat, "beat", "beat"),
        (Chapter, "chapter", "guides_chapter_set"),
    ):
        # Determine if this type should be included based on selected_type
        if selected_type:
            if selected_beat_subtype:
                # type=beat:something -> only include Beat
                if type_name != "beat":
                    continue
            elif selected_type != type_name:
                continue
        # If ID filters are active, skip types not mentioned
        if has_id_filters and type_name not in id_filters:
            continue
        klass_qs = make_queryset(klass, type_name)
        # Apply beat subtype filter when type=beat:something
        if selected_beat_subtype and type_name == "beat":
            klass_qs = klass_qs.filter(beat_type=selected_beat_subtype)
        # Apply ID filter for this type
        if type_name in id_filters:
            klass_qs = klass_qs.filter(pk__in=id_filters[type_name])
        # For beats, break down into per-beat_type counts in type_counts
        if type_name == "beat":
            for row in (
                klass_qs.order_by()
                .values("beat_type")
                .annotate(n=models.Count("pk"))
            ):
                bt_key = f"beat:{row['beat_type']}"
                type_counts_raw[bt_key] = (
                    type_counts_raw.get(bt_key, 0) + row["n"]
                )
        else:
            type_count = klass_qs.count()
            if type_count:
                type_counts_raw[type_name] = type_count
        for tag, count in (
            Tag.objects.filter(**{"%s__in" % tag_filter_name: klass_qs})
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
        # Only do beat_type counts if type=beat is selected
        if selected_type == "beat" and type_name == "beat":
            for row in (
                klass_qs.order_by().values("beat_type").annotate(n=models.Count("pk"))
            ):
                beat_type_counts_raw[row["beat_type"]] = (
                    beat_type_counts_raw.get(row["beat_type"], 0) + row["n"]
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

    type_labels = {
        "entry": "Entry",
        "blogmark": "Blogmark",
        "quotation": "Quotation",
        "note": "Note",
        "chapter": "Chapter",
    }
    # Add beat subtype labels: beat:release -> Release, etc.
    for bt_value, bt_label in Beat.BeatType.choices:
        type_labels[f"beat:{bt_value}"] = bt_label

    type_counts = sorted(
        [
            {"type": type_name, "label": type_labels.get(type_name, type_name), "n": value}
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

    beat_type_labels = dict(Beat.BeatType.choices)
    beat_type_counts = sorted(
        [
            {"beat_type": bt, "label": beat_type_labels.get(bt, bt), "n": value}
            for bt, value in list(beat_type_counts_raw.items())
        ],
        key=lambda t: t["n"],
        reverse=True,
    )

    paginator = Paginator(qs, per_page)
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
        "type_label": type_labels.get(selected_type, selected_type) if selected_type else "",
        "beat": selected_beat,
        "beat_label": (
            beat_type_labels.get(selected_beat, selected_beat) if selected_beat else ""
        ),
        "month_name": (
            calendar.month_name[int(selected_month)] if selected_month.isdigit() else ""
        ),
        "from_date": from_date,
        "to_date": to_date,
    }
    # Remove empty keys
    selected = {key: value for key, value in list(selected.items()) if value}

    # Dynamic title
    beat_subtype_nouns = {
        "release": "Releases",
        "til": "TILs",
        "til_update": "TIL updates",
        "research": "Research",
        "tool": "Tools",
        "museum": "Museums",
    }
    base_type_nouns = {
        "quotation": "Quotations",
        "blogmark": "Blogmarks",
        "entry": "Entries",
        "note": "Notes",
        "beat": "Elsewhere",
        "chapter": "Chapters",
    }
    sel_type = selected.get("type", "")
    if sel_type.startswith("beat:"):
        noun = beat_subtype_nouns.get(sel_type[5:], "Elsewhere")
    else:
        noun = base_type_nouns.get(sel_type) or "Posts"
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

    # Build id_filter_params for template (preserving raw values)
    id_filter_params = {}
    for param in id_filter_param_map:
        raw = request.GET.get(param, "").strip()
        if raw:
            id_filter_params[param] = raw

    # Build human-readable list of filtered types
    id_filter_type_names = []
    type_display_names = {
        "entry": "entries",
        "blogmark": "blogmarks",
        "quotation": "quotations",
        "note": "notes",
        "beat": "beats",
        "chapter": "chapters",
    }
    for type_name in ("entry", "blogmark", "quotation", "note", "beat", "chapter"):
        if type_name in id_filters:
            id_filter_type_names.append(type_display_names[type_name])

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
        "beat_type_counts": beat_type_counts,
        "selected_tags": selected_tags,
        "excluded_tags": excluded_tags,
        "selected": selected,
        "suggestion": suggestion,
        "num_corrected_results": num_corrected_results,
        "id_filters": id_filters,
        "id_filter_params": id_filter_params,
        "id_filter_type_names": id_filter_type_names,
    }

    if return_context:
        return context
    else:
        return render(request, "search.html", context)


FEED_URLS = {
    "entry": "/atom/entries/",
    "blogmark": "/atom/links/",
    "quotation": "/atom/quotations/",
    "note": "/atom/notes/",
    "beat": "/atom/beats/",
}


def type_listing(request, type_name):
    request.GET = request.GET.copy()
    request.GET["type"] = type_name
    context = search(request, return_context=True)
    context["fixed_type"] = True
    context["feed_url"] = FEED_URLS.get(type_name)
    if type_name == "beat":
        active_types = set(
            Beat.objects.filter(is_draft=False)
            .values_list("beat_type", flat=True)
            .distinct()
        )
        context["beat_type_links"] = [
            {"slug": value, "label": label, "css_class": value.replace("_", "-")}
            for value, label in Beat.BeatType.choices
            if value in active_types
        ]
    return render(request, "search.html", context)


def beat_type_listing(request, beat_type):
    valid_types = {value for value, _ in Beat.BeatType.choices}
    if beat_type not in valid_types:
        raise Http404
    request.GET = request.GET.copy()
    request.GET["type"] = f"beat:{beat_type}"
    context = search(request, return_context=True)
    context["fixed_type"] = True
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
