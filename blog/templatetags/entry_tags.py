from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from bs4 import BeautifulSoup, NavigableString, Comment
import re
import datetime

register = template.Library()
@register.filter
def xhtml(xhtml):
    return XhtmlString(xhtml, contains_markup=True)


class XhtmlString(object):
    def __init__(self, value, contains_markup=False):
        if isinstance(value, XhtmlString):
            self.soup = value.soup
        else:
            if value is None:
                value = ""
            if not contains_markup:
                # Handle strings like "this & that"
                value = conditional_escape(value)
            self.soup = BeautifulSoup(f"<entry>{value}</entry>", "html.parser")
        self.et = self.soup.find("entry")

    def __str__(self):
        if not self.et:
            return ""
        return mark_safe("".join(str(content) for content in self.et.contents))


@register.filter
def resize_images_to_fit_width(value, arg):
    max_width = int(arg)
    x = XhtmlString(value)
    if not x.et:
        return x
    for img in x.et.find_all("img"):
        try:
            width = int(img.get("width", 0))
            height = int(img.get("height", 0))
        except (TypeError, ValueError):
            continue
        if width > max_width and height:
            # Scale down
            img["width"] = str(max_width)
            img["height"] = str(int(float(max_width) / width * height))
    return x


xhtml_endtag_fragment = re.compile(r"\s*/>")


@register.filter
def xhtml2html(xhtml):
    # &apos; is valid in XML/XHTML but not in regular HTML
    s = str(xhtml).replace("&apos;", "&#39;")
    return mark_safe(xhtml_endtag_fragment.sub(">", s))


@register.filter
def split_cutoff(xhtml):
    return xhtml.split("<!-- cutoff -->")[0]


@register.filter
def remove_context_paragraph(xhtml):
    x = XhtmlString(xhtml)
    if not x.et:
        return x
    p = x.et.find("p")
    if p is None:
        return x
    xhtml = str(p)
    if xhtml.startswith("<p><em>My answer to") or xhtml.startswith(
        '<p class="context">'
    ):
        p.decompose()
    return x


@register.filter
def first_paragraph(xhtml):
    x = XhtmlString(xhtml)
    if not x.et:
        return mark_safe("<p>%s</p>" % xhtml)
    p = x.et.find("p")
    if p is not None:
        return mark_safe(str(p))
    else:
        return mark_safe("<p>%s</p>" % xhtml)


@register.filter
def openid_to_url(openid):
    openid = openid.strip()
    if openid[0] in ("=", "@"):
        return "http://xri.net/%s" % openid
    else:
        return openid


@register.filter
def ends_with_punctuation(value):
    """Does this end in punctuation? Use to decide if more is needed."""
    last_char = value.strip()[-1]
    return last_char in "?.!"


@register.filter
def strip_p_ids(xhtml):
    x = XhtmlString(xhtml)
    if not x.et:
        return x
    for p in x.et.find_all("p"):
        if "id" in p.attrs:
            del p.attrs["id"]
    return x


@register.filter
def break_up_long_words(xhtml, length):
    """Breaks up words that are longer than the argument."""
    length = int(length)
    x = XhtmlString(xhtml)
    do_break_long_words(x.et, length)
    return x


def do_break_long_words(et, length):
    """Pass a BeautifulSoup Tag instance; breaks up long words in it"""
    if et is None:
        return
    for node in list(_iter_text_nodes(et)):
        new_text = do_break_long_words_string(str(node), length)
        if new_text != str(node):
            node.replace_with(new_text)


whitespace_re = re.compile(r"(\s+)")


def _iter_text_nodes(tag):
    if tag is None:
        return []
    for node in tag.descendants:
        if isinstance(node, NavigableString) and not isinstance(node, Comment):
            yield node


def do_break_long_words_string(s, length):
    bits = whitespace_re.split(s)
    for i, bit in enumerate(bits):
        if whitespace_re.match(bit):
            continue
        if len(bit) > length:
            s = ""
            while bit:
                s += bit[:length] + " "
                bit = bit[length:]
            bits[i] = s
    return "".join(bits)


@register.filter
def typography(xhtml):
    if not xhtml:
        return xhtml
    "Handles curly quotes and em dashes. Must be fed valid XHTML!"
    x = XhtmlString(xhtml)
    do_typography(x.et)
    return x


@register.filter
def strip_wrapping_p(xhtml):
    xhtml = xhtml.strip()
    if xhtml.startswith("<p>"):
        xhtml = xhtml[3:]
    if xhtml.endswith("</p>"):
        xhtml = xhtml[:-4]
    return mark_safe(xhtml)


def do_typography(et):
    if et is None:
        return
    for node in list(_iter_text_nodes(et)):
        parent = node.parent
        if parent and parent.name in ("pre", "code"):
            continue
        new_text = do_typography_string(str(node))
        if new_text != str(node):
            node.replace_with(new_text)


LEFT_DOUBLE_QUOTATION_MARK = "\u201c"
RIGHT_DOUBLE_QUOTATION_MARK = "\u201d"
RIGHT_SINGLE_QUOTATION_MARK = "\u2019"
QUOTATION_PAIR = (LEFT_DOUBLE_QUOTATION_MARK, RIGHT_DOUBLE_QUOTATION_MARK)
EM_DASH = "\u2014"


def quote_alternator():
    i = 0
    while True:
        yield QUOTATION_PAIR[i % 2]
        i += 1


double_re = re.compile('"')
tag_contents_re = re.compile("(<.*?>)", re.DOTALL)


def do_typography_string(s):
    # Only do this on text that isn't between < and >
    if "<" in s and ">" in s:
        bits = tag_contents_re.split(s)
        # Avoid recursion error
        if len(bits) == 1:
            return s
        for i, bit in enumerate(bits):
            if i % 2 == 0:
                bits[i] = do_typography_string(bit)
        return "".join(bits)

    # Do single quotes
    s = s.replace("'", RIGHT_SINGLE_QUOTATION_MARK)
    # Now do double quotes, but only if an even number of them
    if s.count('"') % 2 == 0:
        alternator = quote_alternator()
        s = double_re.sub(lambda m: next(alternator), s)
    # Finally, do em dashes
    s = s.replace(" - ", "\u2014")
    return s


NUMBERS = "zero one two three four five six seven eight nine".split()
number_re = re.compile(r"\d+")


def num_to_string(s):
    try:
        return NUMBERS[int(s)]
    except IndexError:
        return s


chunks = (
    (60 * 60 * 24 * 365, "year"),
    (60 * 60 * 24 * 30, "month"),
    (60 * 60 * 24, "day"),
    (60 * 60, "hour"),
    (60, "minute"),
)


@register.filter
def text_ago(d):
    """Returns 'One day' or 'Three minutes' etc - similar to time_since"""
    delta = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) - d
    since_seconds = (24 * 60 * 60 * delta.days) + delta.seconds
    for i, (seconds, name) in enumerate(chunks):
        count = since_seconds // seconds
        if count != 0:
            break
    text = "%d %s%s" % (count, name, ((count == 1) and [""] or ["s"])[0])
    # Now convert the number at the start to a text equivalent
    text = number_re.sub(lambda m: num_to_string(m.group(0)), text)
    # Special case for zero minutes
    if text == "zero minutes" or text.startswith("-"):
        text = "moments"
    return "%s ago" % text


@register.inclusion_tag("includes/entry_footer.html", takes_context=True)
def entry_footer(context, entry):
    context.update({"entry": entry, "showdate": True})
    return context


@register.inclusion_tag("includes/entry_footer.html", takes_context=True)
def entry_footer_no_date(context, entry):
    context.update({"entry": entry, "showdate": False})
    return context
