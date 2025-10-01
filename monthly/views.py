from django.http import Http404
from django.shortcuts import render

from .models import Newsletter


def monthly_index(request):
    newsletters = Newsletter.objects.all()
    context = {
        "newsletters": newsletters,
    }
    return render(request, "monthly.html", context)


def newsletter_detail(request, year, month):
    year = int(year)
    month = int(month)
    newsletters = (
        Newsletter.objects.filter(sent_at__year=year, sent_at__month=month)
        .order_by("-sent_at")
    )
    newsletter = newsletters.first()
    if newsletter is None:
        raise Http404("Newsletter not found")

    return render(
        request,
        "monthly_detail.html",
        {
            "newsletter": newsletter,
        },
    )
