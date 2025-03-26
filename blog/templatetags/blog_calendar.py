from django import template

register = template.Library()

from blog.models import Entry, Photo, Quotation, Blogmark, Photoset, Note
import datetime, copy

# This code used to use the following:
#   import calendar
#   calendar.Calendar().itermonthdates(date.year, date.month)
# But... that functionality of the calendar module is only available in
# 2.5, and relies on the with statement. D'oh!

FIRSTWEEKDAY = 0  # Monday


def itermonthdates(year, month):
    "Modelled after 2.5's calendar...itermonthdates"
    date = datetime.date(year, month, 1)
    # Go back to the beginning of the week
    days = (date.weekday() - FIRSTWEEKDAY) % 7
    date -= datetime.timedelta(days=days)
    oneday = datetime.timedelta(days=1)
    while True:
        yield date
        date += oneday
        if date.month != month and date.weekday() == FIRSTWEEKDAY:
            break


def get_next_month(date):
    "I can't believe this isn't in the standard library!"
    if date.month == 12:
        return datetime.date(date.year + 1, 1, 1)
    else:
        return datetime.date(date.year, date.month + 1, 1)


def get_previous_month(date):
    if date.month == 1:
        return datetime.date(date.year - 1, 12, 1)
    else:
        return datetime.date(date.year, date.month - 1, 1)


@register.inclusion_tag("includes/calendar.html")
def render_calendar(date):
    return calendar_context(date)


@register.inclusion_tag("includes/calendar.html")
def render_calendar_month_only(date):
    ctxt = calendar_context(date)
    ctxt["month_only"] = True
    return ctxt


MODELS_TO_CHECK = (  # Name, model, score
    ("links", Blogmark, 2, "created"),
    ("entries", Entry, 4, "created"),
    ("quotes", Quotation, 2, "created"),
    ("notes", Note, 2, "created"),
    ("photos", Photo, 1, "created"),
    ("photosets", Photoset, 2, "primary__created"),
)


def make_empty_day_dict(date):
    d = dict([(key, []) for key, _1, _2, _3 in MODELS_TO_CHECK])
    d.update({"day": date, "populated": False, "display": True})
    return d


def attribute_lookup(obj, attr_string):
    "Attr string is something like 'primary__created"
    lookups = attr_string.split("__")
    for lookup in lookups:
        obj = getattr(obj, lookup)
    return obj


def calendar_context(date):
    "Renders a summary calendar for the given month"
    day_things = dict(
        [(d, make_empty_day_dict(d)) for d in itermonthdates(date.year, date.month)]
    )
    # Flag all days NOT in year/month as display: False
    for day in list(day_things.keys()):
        if day.month != date.month:
            day_things[day]["display"] = False
    for name, model, score, created_lookup in MODELS_TO_CHECK:
        lookup_args = {
            created_lookup + "__month": date.month,
            created_lookup + "__year": date.year,
        }
        if model in (Blogmark, Entry, Quotation, Note):
            lookup_args["is_draft"] = False
        for item in model.objects.filter(**lookup_args):
            day = day_things[attribute_lookup(item, created_lookup).date()]
            day[name].append(item)
            day["populated"] = True
    # Now that we've gathered the data we can render the calendar
    days = list(day_things.values())
    days.sort(key=lambda x: x["day"])
    # But first, swoop through and add a description to every day
    for day in days:
        day["score"] = score_for_day(day)
        if day["populated"]:
            day["description"] = description_for_day(day)
        if day["day"] == date:
            day["is_this_day"] = True
    # Now swoop through again, applying a colour to every day based on score
    cg = ColourGradient(WHITE, PURPLE)
    max_score = max([d["score"] for d in days] + [0.001])
    for day in days:
        day["colour"] = cg.pick_css(float(day["score"]) / max_score)
    weeks = []
    while days:
        weeks.append(days[0:7])
        del days[0:7]
    # Find next and previous months
    # WARNING: This makes an assumption that I posted at least one thing every
    # month since I started.
    first_month = Entry.objects.all().order_by("created")[0].created.date()
    if get_next_month(first_month) <= date:
        previous_month = get_previous_month(date)
    else:
        previous_month = None
    if date < datetime.date.today().replace(day=1):
        next_month = get_next_month(date)
    else:
        next_month = None
    return {
        "next_month": next_month,
        "previous_month": previous_month,
        "date": date,
        "weeks": weeks,
    }


PURPLE = (163, 143, 183)
WHITE = (255, 255, 255)


class ColourGradient(object):
    def __init__(self, min_col, max_col):
        self.min_col = min_col
        self.max_col = max_col

    def pick(self, f):
        f = float(f)
        assert 0.0 <= f <= 1.0, "argument must be between 0 and 1, inclusive"

        def calc(pair):
            return (pair[0] - pair[1]) * f + pair[1]

        return tuple(map(calc, list(zip(self.max_col, self.min_col))))

    def pick_css(self, f):
        "Returns e.g. rgb(0, 0, 0)"
        return "rgb(%s)" % ", ".join(map(str, list(map(int, self.pick(f)))))


def description_for_day(day):
    bits = []
    for key in day:
        if isinstance(day[key], list) and len(day[key]) > 0:
            count = len(day[key])
            if count == 1:
                name = day[key][0]._meta.verbose_name
            else:
                name = day[key][0]._meta.verbose_name_plural
            bits.append("%d %s" % (count, name))
    return ", ".join(bits)


def score_for_day(day):
    "1 point/photo, 2 points for blogmark/quote/photoset, 4 points for entry"
    score = 0
    for name, model, points, created_lookup in MODELS_TO_CHECK:
        score += points * len(day[name])
    return score
