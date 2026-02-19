from blog.models import Beat, Blogmark, Entry, Note, Quotation


def truncate(text, max_length=500):
    if not text or len(text) <= max_length:
        return text or ""
    truncated = text[: max_length - 1]
    last_period = truncated.rfind(". ")
    if last_period > max_length // 2:
        return truncated[: last_period + 1]
    return truncated.rsplit(" ", 1)[0] + "\u2026"


def _slug_exists_for_date(slug, created):
    """Check if any content type already uses this slug on the given date."""
    date = created.date() if hasattr(created, "date") else created
    for model in (Entry, Blogmark, Quotation, Note):
        if model.objects.filter(slug=slug, created__date=date).exists():
            return True
    return False


def unique_slug(slug, created, import_ref):
    """
    Return a slug unique for the given date, avoiding collisions with
    all content types (entries, blogmarks, quotations, notes, and other beats).
    """
    base_slug = slug[:64]
    candidate = base_slug
    suffix = 2
    while Beat.objects.filter(
        slug=candidate,
        created__date=created.date() if hasattr(created, "date") else created,
    ).exclude(import_ref=import_ref).exists() or _slug_exists_for_date(
        candidate, created
    ):
        candidate = "{}{}".format(
            base_slug[: 64 - len(str(suffix)) - 1], "-{}".format(suffix)
        )
        suffix += 1
    return candidate
