from blog.models import Entry, Blogmark, Quotation, Note
from django.conf import settings
from django.core.cache import cache


def all(request):
    return {
        "years_with_content": years_with_content(),
    }


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
