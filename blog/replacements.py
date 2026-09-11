"""Conversion helpers. Call with the source/entry locked inside a transaction."""

from xml.etree import ElementTree

import html5lib
from markdown import markdown
from django.core.exceptions import ValidationError
from django.utils.html import format_html, strip_tags
from django.template.defaultfilters import linebreaks

from .models import Entry, Blogmark, Note, Quotation, Beat

SUFFIX = "-replacement-entry"


def as_xhtml(html):
    # Markdown's XHTML mode does not normalize embedded raw HTML or HTML entities.
    # Preserve already valid XML (including custom elements), otherwise use the
    # HTML5 parser and XML serializer to close void elements and escape entities.
    try:
        ElementTree.fromstring("<entry>" + html + "</entry>")
    except ElementTree.ParseError:
        fragment = html5lib.parseFragment(
            html, treebuilder="etree", namespaceHTMLElements=False
        )
        serialized = ElementTree.tostring(fragment, encoding="unicode", method="xml")
        html = serialized.removeprefix("<DOCUMENT_FRAGMENT>").removesuffix(
            "</DOCUMENT_FRAGMENT>"
        )
        ElementTree.fromstring("<entry>" + html + "</entry>")
    return html


def check_slug(slug, created, exclude=()):
    if len(slug) > 128:
        raise ValidationError(
            "The replacement suffix would make the slug longer than 128 characters."
        )
    for model in (Entry, Blogmark, Note, Quotation, Beat):
        matches = model.objects.filter(
            slug=slug,
            created__year=created.year,
            created__month=created.month,
            created__day=created.day,
        )
        for obj in exclude:
            if isinstance(obj, model):
                matches = matches.exclude(pk=obj.pk)
        if matches.exists():
            raise ValidationError("Another item already uses the proposed URL: " + slug)


def create_replacement(source):
    existing = Entry.objects.filter(
        **{"replacement_" + source._meta.model_name: source}
    ).first()
    if existing:
        return existing, False
    slug = source.slug + SUFFIX
    check_slug(slug, source.created)
    check_slug(source.slug + "-replaced", source.created, exclude=(source,))
    if isinstance(source, Blogmark):
        title = source.title or source.link_title
        body = str(
            format_html(
                '<p><a href="{}">{}</a></p>', source.link_url, source.link_title
            )
        )
        body += "\n" + (
            markdown(source.commentary, output_format="xhtml")
            if source.use_markdown
            else linebreaks(source.commentary, autoescape=True)
        )
        if source.via_url:
            body += "\n" + str(
                format_html(
                    '<p>Via <a href="{}">{}</a>.</p>',
                    source.via_url,
                    source.via_title or source.via_url,
                )
            )
    else:
        body = markdown(source.body, output_format="xhtml")
        title = source.title or strip_tags(body).strip()[:255] or source.slug
    entry = Entry.objects.create(
        title=title,
        body=as_xhtml(body),
        slug=slug,
        created=source.created,
        is_draft=True,
        metadata=source.metadata,
        series=source.series,
        card_image=source.card_image,
        **{"replacement_" + source._meta.model_name: source},
    )
    entry.tags.set(source.tags.all())
    return entry, True


def publish_replacement(entry, source):
    if (
        not entry.is_draft
        or entry.slug != source.slug + SUFFIX
        or entry.created != source.created
    ):
        raise ValidationError(
            "The replacement must be a draft with the original date and replacement slug. Save those values before going live."
        )
    try:
        ElementTree.fromstring("<entry>" + entry.body + "</entry>")
    except ElementTree.ParseError as ex:
        raise ValidationError("The entry body must be valid XHTML: " + str(ex))
    check_slug(source.slug, source.created, exclude=(source, entry))
    check_slug(source.slug + "-replaced", source.created, exclude=(source,))
    entry.slug = source.slug
    source.slug += "-replaced"
    source.is_draft = True
    source.save()
    entry.is_draft = False
    entry.save()
