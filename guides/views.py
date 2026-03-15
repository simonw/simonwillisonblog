from django.shortcuts import render, get_object_or_404
from django.db import models
from django.db.models import Count, Max, Min

from blog.views import set_no_cache
from .models import Guide, Chapter


def guide_index(request):
    guides = (
        Guide.objects.filter(is_draft=False)
        .annotate(
            num_chapters=models.Count(
                "chapters", filter=models.Q(chapters__is_draft=False)
            )
        )
        .prefetch_related("sections", "chapters")
    )
    for guide in guides:
        toc = build_guide_toc(guide)
        guide.visible_chapters = flatten_toc(toc)
    return render(
        request,
        "guide_index.html",
        {
            "guides": guides,
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
            toc.append(
                {
                    "type": "section",
                    "order": sec.order,
                    "section": sec,
                    "chapters": sec_chapters,
                }
            )

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


def _char_diff_html(old_text, new_text, is_remove):
    """Generate HTML for a single line with character-level diff highlights."""
    import difflib

    from django.utils.html import escape

    sm = difflib.SequenceMatcher(None, old_text, new_text)
    parts = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if is_remove:
            chunk = old_text[i1:i2]
        else:
            chunk = new_text[j1:j2]
        if op == "equal":
            parts.append(escape(chunk))
        elif op == "replace":
            parts.append(f'<span class="char-highlight">{escape(chunk)}</span>')
        elif op == "insert" and not is_remove:
            parts.append(f'<span class="char-highlight">{escape(chunk)}</span>')
        elif op == "delete" and is_remove:
            parts.append(f'<span class="char-highlight">{escape(chunk)}</span>')
    return "".join(parts)


def _build_diff_html(diff_lines):
    """Process unified diff lines into HTML with character-level highlighting."""
    from django.utils.html import escape

    if not diff_lines:
        return None
    lines = [l.rstrip("\n") for l in diff_lines]
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("---") or line.startswith("+++"):
            result.append(f'<span class="diff-header">{escape(line)}</span>')
            i += 1
        elif line.startswith("@@"):
            result.append(f'<span class="diff-header">{escape(line)}</span>')
            i += 1
        elif line.startswith("-"):
            removes = []
            while (
                i < len(lines)
                and lines[i].startswith("-")
                and not lines[i].startswith("---")
            ):
                removes.append(lines[i])
                i += 1
            adds = []
            while (
                i < len(lines)
                and lines[i].startswith("+")
                and not lines[i].startswith("+++")
            ):
                adds.append(lines[i])
                i += 1
            pairs = min(len(removes), len(adds))
            for j in range(pairs):
                rem_content = removes[j][1:]
                add_content = adds[j][1:]
                rem_html = _char_diff_html(rem_content, add_content, is_remove=True)
                add_html = _char_diff_html(rem_content, add_content, is_remove=False)
                result.append(f'<span class="diff-remove">-{rem_html}</span>')
                result.append(f'<span class="diff-add">+{add_html}</span>')
            for j in range(pairs, len(removes)):
                result.append(f'<span class="diff-remove">{escape(removes[j])}</span>')
            for j in range(pairs, len(adds)):
                result.append(f'<span class="diff-add">{escape(adds[j])}</span>')
        elif line.startswith("+"):
            result.append(f'<span class="diff-add">{escape(line)}</span>')
            i += 1
        else:
            result.append(escape(line))
            i += 1
    return "\n".join(result)


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
                title_diff = list(
                    difflib.unified_diff(
                        prev.title.splitlines(keepends=True),
                        change.title.splitlines(keepends=True),
                        lineterm="",
                    )
                )
                title_diff = _build_diff_html(title_diff)
            body_diff = None
            if change.body != prev.body:
                body_diff = list(
                    difflib.unified_diff(
                        prev.body.splitlines(keepends=True),
                        change.body.splitlines(keepends=True),
                        lineterm="",
                    )
                )
                body_diff = _build_diff_html(body_diff)
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
