from blog.models import Entry, Blogmark, Quotation
from django.conf import settings


def all(request):
    return {
        'GOOGLE_ANALYTICS_ID': settings.GOOGLE_ANALYTICS_ID,
        'years_with_content': years_with_content(),
    }


def years_with_content():
    years = list(set(
        list(Entry.objects.datetimes('created', 'year')) +
        list(Blogmark.objects.datetimes('created', 'year')) +
        list(Quotation.objects.datetimes('created', 'year'))
    ))
    years.sort()
    return years
