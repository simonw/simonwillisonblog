from .models import Tag, PreviousTagName
from django.db.models import (
    Case,
    When,
    Value,
    IntegerField,
    F,
    Q,
    Subquery,
    OuterRef,
    Count,
)
from django.db.models.functions import Length
from django.http import JsonResponse, HttpResponse
from django.utils.html import format_html
import json


def tags_autocomplete(request):
    query = request.GET.get("q", "")
    # Remove whitespace
    query = "".join(query.split())
    if query:
        entry_count = (
            Tag.objects.filter(id=OuterRef("pk"))
            .annotate(
                count=Count("entry", filter=Q(entry__is_draft=False), distinct=True)
            )
            .values("count")
        )

        # Subquery for counting blogmarks
        blogmark_count = (
            Tag.objects.filter(id=OuterRef("pk"))
            .annotate(
                count=Count(
                    "blogmark", filter=Q(blogmark__is_draft=False), distinct=True
                )
            )
            .values("count")
        )

        # Subquery for counting quotations
        quotation_count = (
            Tag.objects.filter(id=OuterRef("pk"))
            .annotate(
                count=Count(
                    "quotation", filter=Q(quotation__is_draft=False), distinct=True
                )
            )
            .values("count")
        )
        note_count = (
            Tag.objects.filter(id=OuterRef("pk"))
            .annotate(
                count=Count("note", filter=Q(note__is_draft=False), distinct=True)
            )
            .values("count")
        )
        beat_count = (
            Tag.objects.filter(id=OuterRef("pk"))
            .annotate(
                count=Count("beat", filter=Q(beat__is_draft=False), distinct=True)
            )
            .values("count")
        )

        tags = (
            Tag.objects.search(query)
            .annotate(
                total_entry=Subquery(entry_count),
                total_blogmark=Subquery(blogmark_count),
                total_quotation=Subquery(quotation_count),
                total_note=Subquery(note_count),
                total_beat=Subquery(beat_count),
                is_exact_match=Case(
                    When(
                        Q(tag__iexact=query)
                        | Q(
                            pk__in=PreviousTagName.objects.filter(
                                previous_name__iexact=query
                            ).values("tag_id")
                        ),
                        then=Value(1),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
            )
            .annotate(
                count=F("total_entry")
                + F("total_blogmark")
                + F("total_quotation")
                + F("total_note")
                + F("total_beat")
            )
            .order_by("-is_exact_match", "-count", Length("tag"))[:5]
        )
    else:
        tags = Tag.objects.none()

    if request.GET.get("debug"):
        return HttpResponse(
            format_html(
                "<html><body><pre>{}</pre><hr><code>{}</code></body></html>",
                json.dumps(list(tags.values()), indent=4),
                str(tags.query),
            )
        )

    return JsonResponse({"tags": list(tags.values())})
