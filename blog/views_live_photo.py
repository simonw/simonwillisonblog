import json

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Max
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.utils.html import escape, format_html
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from markdown import markdown

from .models import Entry, LiveUpdate

RECENT_ENTRY_COUNT = 10


def live_photo_entries(requested_id=None):
    """
    Returns (entries, selected_entry) for the live photo entry picker.

    Entries that have live updates come first, most recently updated first,
    followed by the most recently created entries. The default selection is
    the entry with the most recent live update, unless requested_id is given.
    """
    annotated = Entry.objects.annotate(latest_update=Max("updates__created")).only(
        "id", "title", "created", "is_draft"
    )
    entries = list(
        annotated.filter(latest_update__isnull=False).order_by("-latest_update")[
            :RECENT_ENTRY_COUNT
        ]
    )
    seen = {entry.pk for entry in entries}
    for entry in annotated.order_by("-created")[:RECENT_ENTRY_COUNT]:
        if entry.pk not in seen:
            entries.append(entry)
            seen.add(entry.pk)

    selected = None
    if requested_id:
        selected = next((e for e in entries if str(e.pk) == str(requested_id)), None)
        if selected is None and str(requested_id).isdigit():
            selected = annotated.filter(pk=requested_id).first()
            if selected is not None:
                entries.insert(0, selected)
    if selected is None and entries:
        selected = entries[0]
    return entries, selected


def live_photo_html(image_url, alt, width, height, caption=""):
    image = format_html(
        '<img src="{}" alt="{}" width="{}" height="{}" '
        'style="max-width: 100%; height: auto;">',
        image_url,
        alt,
        width,
        height,
    )
    caption = caption.strip()
    if not caption:
        return "<br>{}".format(image)
    rendered = markdown(caption)
    # Remove leading/trailing <p> tag, the update is already in a <p>
    if rendered.startswith("<p>") and rendered.endswith("</p>"):
        rendered = rendered[3:-4]
    return "{}<br>{}".format(rendered, image)


@staff_member_required
@never_cache
def live_photo(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Only superusers can upload to S3")
    entries, selected = live_photo_entries(request.GET.get("entry"))
    return render(
        request,
        "live_photo.html",
        {
            "entries": entries,
            "selected_entry": selected,
            "public_url_base": settings.S3_WEB_MANAGER_PUBLIC_URL_BASE,
        },
    )


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


@require_POST
@staff_member_required
def live_photo_create(request):
    if not request.user.is_superuser:
        return _error("Only superusers can post live photos", status=403)
    try:
        data = json.loads(request.body)
    except ValueError:
        return _error("Request body must be JSON")
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object")

    entry_id = str(data.get("entry_id", ""))
    entry = Entry.objects.filter(pk=entry_id).first() if entry_id.isdigit() else None
    if entry is None:
        return _error("Entry not found", status=404)

    public_url_base = settings.S3_WEB_MANAGER_PUBLIC_URL_BASE
    image_url = str(data.get("image_url", ""))
    if not image_url.startswith(public_url_base):
        return _error("image_url must start with {}".format(public_url_base))

    alt = str(data.get("alt", "")).strip()
    if not alt:
        return _error("Alt text is required")

    try:
        width = int(data.get("width"))
        height = int(data.get("height"))
    except (TypeError, ValueError):
        return _error("width and height must be integers")
    if not (0 < width <= 10000 and 0 < height <= 10000):
        return _error("width and height are out of range")

    # Each upload gets a unique URL, so a retry after a lost response
    # returns the existing update instead of posting a duplicate
    update = entry.updates.filter(
        content__contains='src="{}"'.format(escape(image_url))
    ).first()
    if update is None:
        update = LiveUpdate.objects.create(
            entry=entry,
            content=live_photo_html(
                image_url,
                alt,
                width,
                height,
                caption=str(data.get("caption", "")),
            ),
        )
    return JsonResponse(
        {
            "id": update.pk,
            "content": update.content,
            "url": "{}#live-update-{}".format(entry.get_absolute_url(), update.pk),
        }
    )
