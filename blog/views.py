from django.shortcuts import render, get_object_or_404
from django.utils.dates import MONTHS_3_REV
from django.utils.timezone import utc
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.cache import never_cache
from django.conf import settings
from django.core.paginator import (
    Paginator,
    EmptyPage,
    PageNotAnInteger,
)
from django.http import (
    Http404,
    HttpResponseRedirect as Redirect
)
from models import (
    Blogmark,
    Entry,
    Quotation,
    Photo,
    Photoset,
    Tag
)
import datetime
import itertools
import CloudFlare


BLACKLISTED_TAGS = ('quora', 'flash')


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
                created__year = int(year),
                created__month = MONTHS_3_REV[month.lower()],
                created__day = int(day),
                slug = slug
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


def find_last_5_days():
    "Returns 5 date objects representing most recent days that have either"
    "photos, blogmarks or quotes available. Looks at most recent 50 of each."
    #photos = list(Photo.objects.values('created')[0:50])
    blogmarks = list(Blogmark.objects.values('created')[0:50])
    quotes = list(Quotation.objects.values('created')[0:50])
    dates = set([o['created'] for o in blogmarks + quotes])
    dates = list(dates)
    dates.sort()
    dates.reverse()
    return dates[0:5]


def index(request):
    last_5_days = find_last_5_days()
    
    if not last_5_days:
        raise Http404, "No links to display"
    blogmarks = Blogmark.objects.filter(created__gte = last_5_days[-1])
    quotations = Quotation.objects.filter(created__gte = last_5_days[-1])
    days = []
    for daystamp in last_5_days:
        day = daystamp.date()
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
        items.sort(lambda x, y: cmp(y['date'], x['date']))
        days.append({
            'date': day,
            'items': items,
            'photos': []#Photo.objects.filter(
                #created__year = day.year,
                #created__month = day.month,
                #created__day = day.day
            #)
        })
        # If day is today or yesterday, flag it as special
        if day == datetime.date.today():
            days[-1]['special'] = 'Today'
        elif day == datetime.date.today() - datetime.timedelta(days=1):
            days[-1]['special'] = 'Yesterday'

    response = render(request, 'homepage.html', {
        'days': days,
        'entries': Entry.objects.all()[0:3],
        'current_tags': find_current_tags(5),
        'years_with_content': years_with_content(),
    })
    response['Cache-Control'] = 's-maxage=200'
    return response


def find_current_tags(num=5):
    "Returns 5 most popular tags from the last 40 of each item"
    links = Blogmark.objects.all()[:40]
    entries = Entry.objects.all()[:40]
    quotes = Quotation.objects.all()[:40]
    tag_counts = {}
    for obj in itertools.chain(links, entries, quotes):
        for tag in obj.tags.all():
            tag = tag.tag
            if tag in tag_counts:
                tag_counts[tag] += 1
            else:
                tag_counts[tag] = 1
    # Order and return
    pairs = tag_counts.items()
    pairs.sort(lambda x, y: cmp(y[1], x[1]))
    # Filter out blacklisted
    pairs = [pair for pair in pairs if pair[0] not in BLACKLISTED_TAGS]
    return [pair[0] for pair in pairs[:num]]


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
            created__year = year,
            created__month = month
        ).count()
        link_count = Blogmark.objects.filter(
            created__year = year,
            created__month = month
        ).count()
        quote_count = Quotation.objects.filter(
            created__year = year,
            created__month = month
        ).count()
        photo_count = Photo.objects.filter(
            created__year = year,
            created__month = month
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
        'years': years_with_content(),
    })


def years_with_content():
    years = list(set(
        list(Entry.objects.datetimes('created', 'year')) + 
        list(Blogmark.objects.datetimes('created', 'year')) + 
        list(Quotation.objects.datetimes('created', 'year'))
    ))
    years.sort()
    return years

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
    photos = list(Photo.objects.filter(
        created__year=year, created__month=month
    ))
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
            created__year = int(year),
            created__month = MONTHS_3_REV[month.lower()],
            created__day = int(day)
        ).order_by('created')
        if (name == 'photo'):
            filt = filt[:25]
        context[name] = list(filt)
        count += len(context[name])
        items.extend([{'type': name, 'obj': obj} for obj in context[name]])
    # Now do photosets separately because they have no created field
    context['photoset'] = list(Photoset.objects.filter(
        primary__created__year = int(year),
        primary__created__month = MONTHS_3_REV[month.lower()],
        primary__created__day = int(day)
    ))
    for photoset in context['photoset']:
        photoset.created = photoset.primary.created
    count += len(context['photoset'])
    items.extend([{'type': 'photoset', 'obj': ps}
        for ps in context['photoset']])
    if count == 0:
        raise Http404, "No photosets/photos/entries/quotes/links for that day"
    items.sort(lambda x, y: cmp(x['obj'].created, y['obj'].created))
    context['items'] = items
    photos = Photo.objects.filter(
        created__year = context['date'].year,
        created__month = context['date'].month,
        created__day = context['date'].day
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
        tag__in = tags.split('+')
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
            for obj in model.objects.in_bulk(ids).values()
        ])
    if not items:
        raise Http404
    items.sort(lambda x, y: cmp(y['obj'].created, x['obj'].created))
    # Paginate it
    paginator = Paginator(items, 40)
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
        'msg': request.GET.get('msg')
    })
