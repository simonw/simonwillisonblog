from django import template
register = template.Library()


@register.inclusion_tag('includes/blog_mixed_list.html',
    takes_context=True)
def blog_mixed_list(context, items):
    context.update({
        'items': items,
        'showdate': False
    })
    return context


@register.inclusion_tag('includes/blog_mixed_list.html',
    takes_context=True)
def blog_mixed_list_with_dates(context, items):
    context.update({
        'items': items,
        'showdate': True
    })
    return context


@register.inclusion_tag('includes/comments_list.html',
    takes_context=True)
def comments_list(context, comments):
    context.update({
        'comments': comments,
        'show_headers': False,
    })
    return context


@register.inclusion_tag('includes/comments_list.html',
    takes_context=True)
def comments_list_with_headers(context, comments):
    context.update({
        'comments': comments,
        'show_headers': True,
    })
    return context


@register.simple_tag(takes_context=True)
def page_href(context, page):
    query_dict = context['request'].GET.copy()
    if page == 1 and 'page' in query_dict:
        del query_dict['page']
    query_dict['page'] = page
    return '?' + query_dict.urlencode()
