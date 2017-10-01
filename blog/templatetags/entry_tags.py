from django import template
from django.utils.timezone import utc
from xml.etree import ElementTree
import re
import datetime

register = template.Library()
entry_stripper = re.compile('^<entry>(.*?)</entry>$', re.DOTALL)


def _back_to_xhtml(et):
    m = entry_stripper.match(ElementTree.tostring(et, 'utf-8'))
    if m:
        return m.group(1)
    else:
        return '' # If we end up with <entry />


@register.filter
def resize_images_to_fit_width(value, arg):
    max_width = int(arg)
    et = ElementTree.fromstring('<entry>%s</entry>' % value.encode('utf8'))
    for img in et.findall('.//img'):
        width = int(img.get('width', 0))
        height = int(img.get('height', 0))
        if width > max_width:
            # Scale down
            img.set('width', str(max_width))
            img.set('height', str(int(float(max_width) / width * height)))
    return _back_to_xhtml(et)

xhtml_endtag_fragment = re.compile('\s*/>')


@register.filter
def xhtml2html(xhtml):
    # &apos; is valid in XML/XHTML but not in regular HTML
    s = xhtml.replace('&apos;', '&#39;')
    return xhtml_endtag_fragment.sub('>', s)


@register.filter
def remove_quora_paragraph(xhtml):
    et = ElementTree.fromstring(('<entry>%s</entry>' % xhtml).encode('utf8'))
    p = et.find('p')
    if p is None:
        return _back_to_xhtml(et)
    if ElementTree.tostring(p, 'utf-8').startswith('<p><em>My answer to'):
        et.remove(p)
    return _back_to_xhtml(et)


@register.filter
def first_paragraph(xhtml):
    et = ElementTree.fromstring(('<entry>%s</entry>' % xhtml).encode('utf8'))
    p = et.find('p')
    if p is not None:
        return ElementTree.tostring(p, 'utf-8')
    else:
        return '<p>%s</p>' % xhtml


@register.filter
def openid_to_url(openid):
    openid = openid.strip()
    if openid[0] in ('=', '@'):
        return 'http://xri.net/%s' % openid
    else:
        return openid


@register.filter
def ends_with_punctuation(value):
    """Does this end in punctuation? Use to decide if more is needed."""
    last_char = value.strip()[-1]
    return last_char in '?.!'


@register.filter
def strip_p_ids(xhtml):
    et = ElementTree.fromstring('<entry>%s</entry>' % xhtml)
    for p in et.findall('.//p'):
        if 'id' in p.attrib:
            del p.attrib['id']
    return _back_to_xhtml(et)


@register.filter
def break_up_long_words(xhtml, length):
    """Breaks up words that are longer than the argument."""
    length = int(length)
    et = ElementTree.fromstring('<entry>%s</entry>' % xhtml)
    do_break_long_words(et, length)
    return _back_to_xhtml(et)


def do_break_long_words(et, length):
    """Pass an ElementTree instance; breaks up long words in it"""
    if et.text:
        et.text = do_break_long_words_string(et.text, length)
    for child in et.getchildren():
        do_break_long_words(child, length)
    if et.tail:
        et.tail = do_break_long_words_string(et.tail, length)


whitespace_re = re.compile('(\s+)')


def do_break_long_words_string(s, length):
    bits = whitespace_re.split(s)
    for i, bit in enumerate(bits):
        if whitespace_re.match(bit):
            continue
        if len(bit) > length:
            s = ''
            while bit:
                s += bit[:length] + ' '
                bit = bit[length:]
            bits[i] = s
    return ''.join(bits)


@register.filter
def typography(xhtml):
    return xhtml
    if not xhtml:
        return xhtml
    "Handles curly quotes and em dashes. Must be fed valid XHTML!"
    et = ElementTree.fromstring(u'<entry>%s</entry>' % xhtml.encode('utf8'))
    do_typography(et)
    return _back_to_xhtml(et)


def do_typography(et):
    # Designed to be called recursively on ElementTree objects
    if et.tag not in ('pre', 'code'):
        # Don't do et.text or children for those tags; just do et.tail
        if et.text:
            et.text = do_typography_string(et.text)
        for child in et.getchildren():
            do_typography(child)
    if et.tail:
        et.tail = do_typography_string(et.tail)

LEFT_DOUBLE_QUOTATION_MARK = u'\u201c'
RIGHT_DOUBLE_QUOTATION_MARK = u'\u201d'
RIGHT_SINGLE_QUOTATION_MARK = u'\u2019'
QUOTATION_PAIR = (LEFT_DOUBLE_QUOTATION_MARK, RIGHT_DOUBLE_QUOTATION_MARK)
EM_DASH = u'\u2014'


def quote_alternator():
    i = 0
    while True:
        yield QUOTATION_PAIR[i % 2]
        i += 1

double_re = re.compile('"')


def do_typography_string(s):
    if not isinstance(s, unicode):
        s = s.decode('utf-8')
    # Do single quotes
    s = s.replace(u"'", RIGHT_SINGLE_QUOTATION_MARK)
    # Now do double quotes, but only if an even number of them
    if s.count('"') % 2 == 0:
        alternator = quote_alternator()
        s = double_re.sub(lambda m: alternator.next(), s)
    # Finally, do em dashes
    s = s.replace(' - ', u'\u2014')
    return s


NUMBERS = 'zero one two three four five six seven eight nine'.split()
number_re = re.compile('\d+')


def num_to_string(s):
    try:
        return NUMBERS[int(s)]
    except IndexError:
        return s

chunks = (
    (60 * 60 * 24 * 365, 'year'),
    (60 * 60 * 24 * 30, 'month'),
    (60 * 60 * 24, 'day'),
    (60 * 60, 'hour'),
    (60, 'minute')
)


@register.filter
def text_ago(d):
    """Returns 'One day' or 'Three minutes' etc - similar to time_since"""
    delta = datetime.datetime.utcnow().replace(tzinfo=utc) - d
    since_seconds = (24 * 60 * 60 * delta.days) + delta.seconds
    for i, (seconds, name) in enumerate(chunks):
        count = since_seconds / seconds
        if count != 0:
            break
    text = "%d %s%s" % (count, name, ((count == 1) and [""] or ["s"])[0])
    # Now convert the number at the start to a text equivalent
    text = number_re.sub(lambda m: num_to_string(m.group(0)), text)
    # Special case for zero minutes
    if text == 'zero minutes' or text.startswith('-'):
        text = 'moments'
    return '%s ago' % text


@register.inclusion_tag('includes/entry_footer.html', takes_context=True)
def entry_footer(context, entry):
    context.update({
        'entry': entry,
        'showdate': True
    })
    return context


@register.inclusion_tag('includes/entry_footer.html', takes_context=True)
def entry_footer_no_date(context, entry):
    context.update({
        'entry': entry,
        'showdate': False
    })
    return context
