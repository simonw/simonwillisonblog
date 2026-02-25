from django.shortcuts import render, get_object_or_404
from django.db import models
from django.db.models import Count, Max, Min

from blog.views import set_no_cache
from .models import Guide, Chapter


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


def build_guide_toc(guide, include_drafts=False):
    qs = guide.chapters.all()
    if not include_drafts:
        qs = qs.filter(is_draft=False)

    standalone = list(qs.filter(section__isnull=True).order_by("order", "created"))
    sections = guide.sections.order_by("order")

    toc = []
    for ch in standalone:
        toc.append({"type": "chapter", "order": ch.order, "chapter": ch})

    for sec in sections:
        sec_chapters = list(qs.filter(section=sec).order_by("order", "created"))
        if sec_chapters:
            toc.append({
                "type": "section",
                "order": sec.order,
                "section": sec,
                "chapters": sec_chapters,
            })

    toc.sort(key=lambda item: item["order"])
    return toc


def flatten_toc(toc):
    flat = []
    for item in toc:
        if item["type"] == "chapter":
            flat.append(item["chapter"])
        else:
            flat.extend(item["chapters"])
    return flat


def guide_detail(request, slug):
    if request.user.is_staff:
        guide = get_object_or_404(Guide, slug=slug)
    else:
        guide = get_object_or_404(Guide, slug=slug, is_draft=False)
    include_drafts = request.user.is_staff and guide.is_draft
    toc = build_guide_toc(guide, include_drafts=include_drafts)
    response = render(
        request,
        "guide_detail.html",
        {
            "guide": guide,
            "toc": toc,
        },
    )
    if guide.is_draft:
        set_no_cache(response)
    return response


def chapter_detail(request, guide_slug, chapter_slug):
    if request.user.is_staff:
        guide = get_object_or_404(Guide, slug=guide_slug)
        chapter = get_object_or_404(Chapter, guide=guide, slug=chapter_slug)
    else:
        guide = get_object_or_404(Guide, slug=guide_slug, is_draft=False)
        chapter = get_object_or_404(
            Chapter, guide=guide, slug=chapter_slug, is_draft=False
        )
    include_drafts = request.user.is_staff and chapter.is_draft
    toc = build_guide_toc(guide, include_drafts=include_drafts)
    all_chapters = flatten_toc(toc)
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
    change_stats = chapter.changes.aggregate(
        first_created=Min("created"),
        last_modified=Max("created"),
        num_changes=Count("id"),
    )
    response = render(
        request,
        "chapter_detail.html",
        {
            "guide": guide,
            "chapter": chapter,
            "toc": toc,
            "all_chapters": all_chapters,
            "previous_chapter": previous_chapter,
            "next_chapter": next_chapter,
            "chapter_created": change_stats["first_created"],
            "chapter_last_modified": change_stats["last_modified"],
            "chapter_num_changes": change_stats["num_changes"],
        },
    )
    if guide.is_draft or chapter.is_draft:
        set_no_cache(response)
    return response


def chapter_changes(request, guide_slug, chapter_slug):
    if request.user.is_staff:
        guide = get_object_or_404(Guide, slug=guide_slug)
        chapter = get_object_or_404(Chapter, guide=guide, slug=chapter_slug)
    else:
        guide = get_object_or_404(Guide, slug=guide_slug, is_draft=False)
        chapter = get_object_or_404(
            Chapter, guide=guide, slug=chapter_slug, is_draft=False
        )
    changes = list(chapter.changes.order_by("created"))
    import difflib

    diffs = []
    for i, change in enumerate(changes):
        if i == 0:
            diffs.append(
                {
                    "change": change,
                    "title_diff": None,
                    "body_diff": None,
                    "is_draft_changed": False,
                    "is_first": True,
                }
            )
        else:
            prev = changes[i - 1]
            title_diff = None
            if change.title != prev.title:
                title_diff = difflib.unified_diff(
                    prev.title.splitlines(keepends=True),
                    change.title.splitlines(keepends=True),
                    lineterm="",
                )
                title_diff = list(title_diff)
            body_diff = None
            if change.body != prev.body:
                body_diff = difflib.unified_diff(
                    prev.body.splitlines(keepends=True),
                    change.body.splitlines(keepends=True),
                    lineterm="",
                )
                body_diff = list(body_diff)
            diffs.append(
                {
                    "change": change,
                    "title_diff": title_diff,
                    "body_diff": body_diff,
                    "is_draft_changed": change.is_draft != prev.is_draft,
                    "prev_is_draft": prev.is_draft,
                    "is_first": False,
                }
            )
    response = render(
        request,
        "chapter_changes.html",
        {
            "guide": guide,
            "chapter": chapter,
            "diffs": reversed(diffs),
        },
    )
    if guide.is_draft or chapter.is_draft:
        set_no_cache(response)
    return response
