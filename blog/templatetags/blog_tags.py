from django import template
from django.utils.safestring import mark_safe
from markdown import markdown

register = template.Library()


@register.inclusion_tag("includes/blog_mixed_list.html", takes_context=True)
def blog_mixed_list(context, items):
    context.update({"items": items, "showdate": False})
    return context


@register.inclusion_tag("includes/blog_mixed_list.html", takes_context=True)
def blog_mixed_list_with_dates(
    context, items, year_headers=False, day_headers=False, day_links=False
):
    context.update(
        {
            "items": items,
            "showdate": not day_headers,
            "year_headers": year_headers,
            "day_headers": day_headers,
            "day_links": day_links,
        }
    )
    return context


@register.inclusion_tag("includes/comments_list.html", takes_context=True)
def comments_list(context, comments):
    context.update(
        {
            "comments": comments,
            "show_headers": False,
        }
    )
    return context


@register.inclusion_tag("includes/comments_list.html", takes_context=True)
def comments_list_with_headers(context, comments):
    context.update(
        {
            "comments": comments,
            "show_headers": True,
        }
    )
    return context


@register.simple_tag(takes_context=True)
def page_href(context, page):
    query_dict = context["request"].GET.copy()
    if page == 1 and "page" in query_dict:
        del query_dict["page"]
    query_dict["page"] = str(page)
    if context.get("fixed_type") and "type" in query_dict:
        del query_dict["type"]
    return "?" + query_dict.urlencode()


def _search_prefix(context, query_dict):
    if context.get("fixed_type"):
        return "/search/?" + query_dict.urlencode()
    return "?" + query_dict.urlencode()


@register.simple_tag(takes_context=True)
def add_qsarg(context, name, value):
    query_dict = context["request"].GET.copy()
    if value not in query_dict.getlist(name):
        query_dict.appendlist(name, value)
    # And always remove ?page= - see
    # https://github.com/simonw/simonwillisonblog/issues/239
    if "page" in query_dict:
        query_dict.pop("page")
    return _search_prefix(context, query_dict)


@register.simple_tag(takes_context=True)
def remove_qsarg(context, name, value):
    query_dict = context["request"].GET.copy()
    query_dict.setlist(name, [v for v in query_dict.getlist(name) if v != value])
    return _search_prefix(context, query_dict)


@register.simple_tag(takes_context=True)
def replace_qsarg(context, name, value):
    query_dict = context["request"].GET.copy()
    query_dict[name] = value
    return _search_prefix(context, query_dict)


@register.simple_tag(takes_context=True)
def remove_id_filters(context):
    query_dict = context["request"].GET.copy()
    for param in ("entries", "blogmarks", "quotations", "notes"):
        query_dict.pop(param, None)
    return _search_prefix(context, query_dict)


@register.filter
def markdownify(text):
    """
    Convert Markdown text to HTML.
    """
    return mark_safe(markdown(text))


@register.filter
def strip_trailing_period(text):
    if text and text.endswith("."):
        return text[:-1]
    return text


@register.filter
def trailing_period(text):
    if text and text.endswith("."):
        return "."
    return ""
