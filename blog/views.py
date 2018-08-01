# coding=utf8
from django.shortcuts import render, get_object_or_404
from django.utils.timezone import utc
from django.http import HttpResponse, JsonResponse
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.views.decorators.cache import never_cache
from django.db import models
from django.db.models.functions import TruncYear, TruncMonth
from django.conf import settings
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.http import (
    Http404,
    HttpResponsePermanentRedirect as Redirect
)
from .models import (
    Blogmark,
    Entry,
    Quotation,
    Photo,
    Photoset,
    Tag,
    load_mixed_objects,
)
import requests
from bs4 import BeautifulSoup as Soup
import time
import json
import datetime
import random
from collections import Counter
import CloudFlare
import os

MONTHS_3_REV = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
    'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
}
MONTHS_3_REV_REV = {value: key for key, value in list(MONTHS_3_REV.items())}
BLACKLISTED_TAGS = ('quora', 'flash', 'resolved', 'recovered')


def archive_item(request, year, month, day, slug):
    if day.startswith('0'):
        day = day.lstrip('0')
        return Redirect('/%s/%s/%s/%s/' % (year, month, day, slug))

    # This could be a quote OR link OR entry
    for content_type, model in (
        ('blogmark', Blogmark),
        ('entry', Entry),
        ('quotation', Quotation)
    ):
        try:
            obj = get_object_or_404(model,
                created__year=int(year),
                created__month=MONTHS_3_REV[month.lower()],
                created__day=int(day),
                slug=slug
            )
        except Http404:
            continue

        # If item is entry posted before Dec 1 2006, add "previously hosted"
        if content_type == 'entry' and obj.created < datetime.datetime(
            2006, 12, 1, 1, 1, 1, tzinfo=utc
        ):
            previously_hosted = 'http://simon.incutio.com/archive/' + \
                obj.created.strftime("%Y/%m/%d/") + obj.slug
        else:
            previously_hosted = None

        return render(request, '%s.html' % content_type, {
            content_type: obj,
            'content_type': content_type,
            'object_id': obj.id,
            'previously_hosted': previously_hosted,
            'item': obj,
        })

    # If we get here, non of the views matched
    raise Http404


def find_last_x_days(x=10):
    """
    Returns 5 date objects representing most recent days that have either
    photos, blogmarks or quotes available. Looks at most recent 50 of each.
    """
    # photos = list(Photo.objects.values('created')[0:50])
    blogmarks = list(Blogmark.objects.values('created')[0:50])
    quotes = list(Quotation.objects.values('created')[0:50])
    dates = set([o['created'].date() for o in blogmarks + quotes])
    dates = list(dates)
    dates.sort()
    dates.reverse()
    return dates[0:x]


def index(request):
    last_x_days = find_last_x_days()

    if not last_x_days:
        raise Http404("No links to display")
    blogmarks = Blogmark.objects.filter(
        created__gte=last_x_days[-1]
    ).prefetch_related('tags')
    quotations = Quotation.objects.filter(
        created__gte=last_x_days[-1]
    ).prefetch_related('tags')
    days = []
    for day in last_x_days:
        links = [
            {'type': 'link', 'obj': link, 'date': link.created}
            for link in blogmarks
            if link.created.date() == day
        ]
        quotes = [
            {'type': 'quote', 'obj': q, 'date': q.created}
            for q in quotations
            if q.created.date() == day
        ]
        items = links + quotes
        items.sort(key=lambda x: x['date'], reverse=True)
        days.append({
            'date': day,
            'items': items,
            'photos': []
            # Photo.objects.filter(
            #   created__year = day.year,
            #   created__month = day.month,
            #   created__day = day.day
            # )
        })
        # If day is today or yesterday, flag it as special
        if day == datetime.date.today():
            days[-1]['special'] = 'Today'
        elif day == datetime.date.today() - datetime.timedelta(days=1):
            days[-1]['special'] = 'Yesterday'

    response = render(request, 'homepage.html', {
        'days': days,
        'entries': Entry.objects.prefetch_related('tags')[0:4],
        'current_tags': find_current_tags(5),
    })
    response['Cache-Control'] = 's-maxage=200'
    return response


def find_current_tags(num=5):
    """Returns num random tags from top 30 in recent 400 taggings"""
    last_400_tags = list(Tag.quotation_set.through.objects.annotate(
        created=models.F('quotation__created')
    ).values('tag__tag', 'created').union(
        Tag.entry_set.through.objects.annotate(
            created=models.F('entry__created')
        ).values('tag__tag', 'created'),
        Tag.blogmark_set.through.objects.annotate(
            created=models.F('blogmark__created')
        ).values('tag__tag', 'created'),
    ).order_by('-created')[:400])
    counter = Counter(
        t['tag__tag'] for t in last_400_tags
        if t['tag__tag'] not in BLACKLISTED_TAGS
    )
    candidates = [p[0] for p in counter.most_common(30)]
    random.shuffle(candidates)
    return candidates[:num]


def archive_year(request, year):
    year = int(year)
    # Display list of months
    # each with count of blogmarks/photos/entries/quotes
    # We can cache this page heavily, so don't worry too much
    months = []
    max_count = 0
    for month in range(1, 12 + 1):
        date = datetime.date(year=year, month=month, day=1)
        entry_count = Entry.objects.filter(
            created__year=year,
            created__month=month
        ).count()
        link_count = Blogmark.objects.filter(
            created__year=year,
            created__month=month
        ).count()
        quote_count = Quotation.objects.filter(
            created__year=year,
            created__month=month
        ).count()
        photo_count = Photo.objects.filter(
            created__year=year,
            created__month=month
        ).count()
        month_count = entry_count + link_count + quote_count + photo_count
        if month_count:
            counts = [
                ('entry', entry_count),
                ('link', link_count),
                ('photo', photo_count),
                ('quote', quote_count),
            ]
            counts_not_0 = [p for p in counts if p[1]]
            months.append({
                'date': date,
                'counts': counts,
                'counts_not_0': counts_not_0
            })
            max_count = max(
                max_count, entry_count, link_count, quote_count, photo_count
            )
    return render(request, 'archive_year.html', {
        'months': months,
        'year': year,
        'max_count': max_count,
    })


def archive_month(request, year, month):
    year = int(year)
    month = MONTHS_3_REV[month.lower()]

    def by_date(objs):
        lookup = {}
        for obj in objs:
            lookup.setdefault(obj.created.date(), []).append(obj)
        return lookup
    entries = list(Entry.objects.filter(
        created__year=year, created__month=month
    ).order_by('created'))
    blogmarks = list(Blogmark.objects.filter(
        created__year=year, created__month=month
    ))
    quotations = list(Quotation.objects.filter(
        created__year=year, created__month=month
    ))
    # photos = list(Photo.objects.filter(
    #     created__year=year, created__month=month
    # ))
    # Extract non-de-duped list of ALL tags, for tag cloud
    tags = []
    for obj in entries + blogmarks + quotations:
        tags.extend([t.tag for t in obj.tags.all()])
    return render(request, 'archive_month.html', {
        'date': datetime.date(year, month, 1),
        'entries': entries,
        'tags': tags
    })


def archive_day(request, year, month, day):
    if day.startswith('0'):
        day = day.lstrip('0')
        return Redirect('/%s/%s/%s/' % (year, month, day))
    context = {}
    context['date'] = datetime.date(
        int(year), MONTHS_3_REV[month.lower()], int(day)
    )
    items = [] # Array of {'type': , 'obj': }
    count = 0
    for name, model in (
        ('blogmark', Blogmark), ('entry', Entry),
        ('quotation', Quotation), ('photo', Photo)
    ):
        filt = model.objects.filter(
            created__year=int(year),
            created__month=MONTHS_3_REV[month.lower()],
            created__day=int(day)
        ).order_by('created')
        if (name == 'photo'):
            filt = filt[:25]
        context[name] = list(filt)
        count += len(context[name])
        items.extend([{'type': name, 'obj': obj} for obj in context[name]])
    # Now do photosets separately because they have no created field
    context['photoset'] = list(Photoset.objects.filter(
        primary__created__year=int(year),
        primary__created__month=MONTHS_3_REV[month.lower()],
        primary__created__day=int(day)
    ))
    for photoset in context['photoset']:
        photoset.created = photoset.primary.created
    count += len(context['photoset'])
    items.extend([{'type': 'photoset', 'obj': ps}
        for ps in context['photoset']])
    if count == 0:
        raise Http404("No photosets/photos/entries/quotes/links for that day")
    items.sort(key=lambda x: x['obj'].created, reverse=True)
    context['items'] = items
    photos = Photo.objects.filter(
        created__year=context['date'].year,
        created__month=context['date'].month,
        created__day=context['date'].day
    )
    context['photos'] = photos[:25]
    # Should we show more_photos ?
    if photos.count() > 25:
        context['more_photos'] = photos.count()
    return render(request, 'archive_day.html', context)


def tag_index(request):
    return render(request, 'tags.html')

# This query gets the IDs of things that match all of the tags
INTERSECTION_SQL = """
    SELECT %(content_table)s.id
        FROM %(content_table)s, %(tag_table)s
    WHERE %(tag_table)s.tag_id IN (
            SELECT id FROM blog_tag WHERE tag IN (%(joined_tags)s)
        )
        AND %(tag_table)s.%(tag_table_content_key)s = %(content_table)s.id
    GROUP BY %(content_table)s.id
        HAVING COUNT(%(content_table)s.id) = %(tag_count)d
"""


def archive_tag(request, tags):
    tags = Tag.objects.filter(
        tag__in=tags.split('+')
    ).values_list('tag', flat=True)[:3]
    if not tags:
        raise Http404
    items = []
    from django.db import connection
    cursor = connection.cursor()
    for model, content_type in (
            (Entry, 'entry'), (Quotation, 'quotation'), (Blogmark, 'blogmark')):
        cursor.execute(INTERSECTION_SQL % {
            'content_table': 'blog_%s' % content_type,
            'tag_table': 'blog_%s_tags' % content_type,
            'tag_table_content_key': '%s_id' % content_type,
            'joined_tags': ', '.join(["'%s'" % tag for tag in tags]),
            'tag_count': len(tags),
        })
        ids = [r[0] for r in cursor.fetchall()]
        items.extend([
            {'type': content_type, 'obj': obj}
            for obj in list(model.objects.prefetch_related('tags').in_bulk(ids).values())
        ])
    if not items:
        raise Http404
    items.sort(key=lambda x: x['obj'].created, reverse=True)
    # Paginate it
    paginator = Paginator(items, 30)
    page_number = request.GET.get('page') or '1'
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        raise Http404
    except EmptyPage:
        raise Http404

    return render(request, 'archive_tag.html', {
        'tags': tags,
        'items': page.object_list,
        'total': paginator.count,
        'page': page,
        'only_one_tag': len(tags) == 1,
        'tag': Tag.objects.get(tag=tags[0]),
    })


@never_cache
@staff_member_required
def write(request):
    return render(request, 'write.html')


@never_cache
@staff_member_required
def tools(request):
    if request.POST.get('purge_all'):
        cf = CloudFlare.CloudFlare(
            email=settings.CLOUDFLARE_EMAIL,
            token=settings.CLOUDFLARE_TOKEN
        )
        cf.zones.purge_cache.delete(settings.CLOUDFLARE_ZONE_ID, data={
            'purge_everything': True
        })
        return Redirect(request.path + '?msg=Cache+purged')
    return render(request, 'tools.html', {
        'msg': request.GET.get('msg'),
        'deployed_hash': os.environ.get('HEROKU_SLUG_COMMIT'),
    })


@never_cache
@staff_member_required
def tools_extract_title(request):
    url = request.GET.get('url', '')
    if url:
        soup = Soup(requests.get(url).content, 'html5lib')
        title = ''
        title_el = soup.find('title')
        if title_el:
            title = title_el.text
        return JsonResponse({
            'title': title,
        })
    return JsonResponse({})


def search(request):
    q = request.GET.get('q', '').strip()
    start = time.time()

    query = None
    rank_annotation = None
    if q:
        query = SearchQuery(q)
        rank_annotation = SearchRank(models.F('search_document'), query)

    selected_tags = request.GET.getlist('tag')
    excluded_tags = request.GET.getlist('exclude.tag')
    selected_type = request.GET.get('type', '')
    selected_year = request.GET.get('year', '')
    selected_month = request.GET.get('month', '')

    values = ['pk', 'type', 'created']
    if q:
        values.append('rank')

    def make_queryset(klass, type_name):
        qs = klass.objects.annotate(
            type=models.Value(type_name, output_field=models.CharField())
        )
        if selected_year:
            qs = qs.filter(created__year=int(selected_year))
        if selected_month:
            qs = qs.filter(created__month=int(selected_month))
        if q:
            qs = qs.filter(search_document=query)
            qs = qs.annotate(rank=rank_annotation)
        for tag in selected_tags:
            qs = qs.filter(tags__tag=tag)
        for exclude_tag in excluded_tags:
            qs = qs.exclude(tags__tag=exclude_tag)
        return qs.order_by()

    # Start with a .none() queryset just so we can union stuff onto it
    qs = Entry.objects.annotate(
        type=models.Value('empty', output_field=models.CharField())
    )
    if q:
        qs = qs.annotate(rank=rank_annotation)
    qs = qs.values(*values).none()

    type_counts_raw = {}
    tag_counts_raw = {}
    year_counts_raw = {}
    month_counts_raw = {}

    for klass, type_name in (
        (Entry, 'entry'),
        (Blogmark, 'blogmark'),
        (Quotation, 'quotation'),
    ):
        if selected_type and selected_type != type_name:
            continue
        klass_qs = make_queryset(klass, type_name)
        type_count = klass_qs.count()
        if type_count:
            type_counts_raw[type_name] = type_count
        for tag, count in Tag.objects.filter(**{
            '%s__in' % type_name: klass_qs
        }).annotate(
            n=models.Count('tag')
        ).values_list('tag', 'n'):
            tag_counts_raw[tag] = tag_counts_raw.get(tag, 0) + count
        for row in klass_qs.order_by().annotate(
            year=TruncYear('created')
        ).values('year').annotate(n=models.Count('pk')):
            year_counts_raw[row['year']] = year_counts_raw.get(
                row['year'], 0
            ) + row['n']
        # Only do month counts if a year is selected
        if selected_year:
            for row in klass_qs.order_by().annotate(
                month=TruncMonth('created')
            ).values('month').annotate(n=models.Count('pk')):
                month_counts_raw[row['month']] = month_counts_raw.get(
                    row['month'], 0
                ) + row['n']
        qs = qs.union(klass_qs.values(*values))

    if q:
        qs = qs.order_by('-rank')
    else:
        qs = qs.order_by('-created')

    type_counts = sorted(
        [
            {'type': type_name, 'n': value}
            for type_name, value in list(type_counts_raw.items())
        ],
        key=lambda t: t['n'], reverse=True
    )
    tag_counts = sorted(
        [
            {'tag': tag, 'n': value}
            for tag, value in list(tag_counts_raw.items())
        ],
        key=lambda t: t['n'], reverse=True
    )[:40]

    year_counts = sorted(
        [
            {'year': year, 'n': value}
            for year, value in list(year_counts_raw.items())
        ],
        key=lambda t: t['year']
    )

    month_counts = sorted(
        [
            {'month': month, 'n': value}
            for month, value in list(month_counts_raw.items())
        ],
        key=lambda t: t['month']
    )

    paginator = Paginator(qs, 30)
    page_number = request.GET.get('page') or '1'
    try:
        page = paginator.page(page_number)
    except PageNotAnInteger:
        raise Http404
    except EmptyPage:
        raise Http404

    results = []
    for obj in load_mixed_objects(page.object_list):
        results.append({
            'type': obj.original_dict['type'],
            'rank': obj.original_dict.get('rank'),
            'obj': obj,
        })
    end = time.time()

    selected = {
        'tags': selected_tags,
        'year': selected_year,
        'month': selected_month,
        'type': selected_type,
        'month_name': MONTHS_3_REV_REV.get(selected_month and int(selected_month) or '', '').title(),
    }
    # Remove empty keys
    selected = {
        key: value
        for key, value in list(selected.items())
        if value
    }

    # Dynamic title
    noun = {
        'quotation': 'Quotations',
        'blogmark': 'Blogmarks',
        'entry': 'Entries',
    }.get(selected.get('type')) or 'Items'
    title = noun

    if q:
        title = '“%s” in %s' % (q, title.lower())

    if selected.get('tags'):
        title += ' tagged %s' % (', '.join(selected['tags']))

    datebits = []
    if selected.get('month_name'):
        datebits.append(selected['month_name'])
    if selected.get('year'):
        datebits.append(selected['year'])
    if datebits:
        title += ' in %s' % (', '.join(datebits))

    if not q and not selected:
        title = 'Search'

    return render(request, 'search.html', {
        'q': q,
        'title': title,
        'results': results,
        'total': paginator.count,
        'page': page,
        'duration': end - start,
        'type_counts': type_counts,
        'tag_counts': tag_counts,
        'year_counts': year_counts,
        'month_counts': month_counts,
        'selected_tags': selected_tags,
        'excluded_tags': excluded_tags,
        'selected': selected,
    })


def tools_search_tags(request):
    q = request.GET.get('q', '').strip()
    results = []
    if q:
        results = list(
            Tag.objects.filter(tag__icontains=q).values_list('tag', flat=True)
        )
        results.sort(key=lambda t: len(t))
    return HttpResponse(json.dumps({
        'tags': results
    }), content_type='application/json')


# Redirects for ancient patterns
# /archive/2002/10/24/
def archive_day_redirect(request, yyyy, mm, dd):
    return Redirect('/%s/%s/%d/' % (
        yyyy, MONTHS_3_REV_REV[int(mm)].title(), int(dd)
    ))


# /archive/2003/09/05/listamatic
def archive_item_redirect(request, yyyy, mm, dd, slug):
    return Redirect('/%s/%s/%d/%s' % (
        yyyy, MONTHS_3_REV_REV[int(mm)].title(), int(dd), slug
    ))
