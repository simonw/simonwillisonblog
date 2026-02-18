from blog.models import Beat


def truncate(text, max_length=500):
    if not text or len(text) <= max_length:
        return text or ""
    truncated = text[: max_length - 1]
    last_period = truncated.rfind(". ")
    if last_period > max_length // 2:
        return truncated[: last_period + 1]
    return truncated.rsplit(" ", 1)[0] + "\u2026"


def unique_slug(slug, created, import_ref):
    """
    Return a slug unique for the given date, avoiding collisions with
    other beats (excluding the one identified by import_ref).
    """
    base_slug = slug[:64]
    candidate = base_slug
    suffix = 2
    while Beat.objects.filter(
        slug=candidate,
        created__date=created.date() if hasattr(created, "date") else created,
    ).exclude(import_ref=import_ref).exists():
        candidate = "{}{}".format(base_slug[: 64 - len(str(suffix)) - 1], "-{}".format(suffix))
        suffix += 1
    return candidate
