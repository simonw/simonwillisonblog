from blog.models import Entry, Blogmark, Quotation, Note, SponsorMessage
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone


def all(request):
    return {
        "years_with_content": years_with_content(),
        "sponsor_message": current_sponsor_message(),
    }


def current_sponsor_message():
    cache_key = "current-sponsor-message"
    message = cache.get(cache_key)
    if message is None:
        now = timezone.now()
        message = (
            SponsorMessage.objects.filter(
                is_active=True,
                display_from__lte=now,
                display_until__gte=now,
            )
            .order_by("-pk")
            .first()
        ) or False  # False as sentinel since None means cache miss
        cache.set(cache_key, message, 60)
    return message if message is not False else None


def years_with_content():
    cache_key = "years-with-content-3"
    years = cache.get(cache_key)
    if not years:
        years = list(
            set(
                list(Entry.objects.datetimes("created", "year"))
                + list(Blogmark.objects.datetimes("created", "year"))
                + list(Quotation.objects.datetimes("created", "year"))
                + list(Note.objects.datetimes("created", "year"))
            )
        )
        years.sort()
        cache.set(cache_key, years, 60 * 60)
    return years
