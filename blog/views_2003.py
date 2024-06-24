from django.shortcuts import render
from django.db.models import CharField, Value
import datetime
from .models import (
    Blogmark,
    Entry,
    Quotation,
)


def index(request):
    # Get back items across all item types - I went back to UK on 30 September 2004
    cutoff_kwargs = {}
    if request.GET.get("backdate"):
        cutoff_kwargs["created__lte"] = datetime.datetime(2004, 9, 29, 0, 0, 0)
    recent = list(
        Entry.objects.filter(**cutoff_kwargs)
        .annotate(content_type=Value("entry", output_field=CharField()))
        .values("content_type", "id", "created")
        .order_by()
        .union(
            Blogmark.objects.filter(**cutoff_kwargs)
            .annotate(content_type=Value("blogmark", output_field=CharField()))
            .values("content_type", "id", "created")
            .order_by()
        )
        .union(
            Quotation.objects.filter(**cutoff_kwargs)
            .annotate(content_type=Value("quotation", output_field=CharField()))
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
        "homepage_2003.html",
        {
            "items": items,
        },
    )
    response["Cache-Control"] = "s-maxage=200"
    return response
