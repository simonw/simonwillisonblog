from django.core.management.base import BaseCommand
from django.db import transaction
from blog.models import (
    Entry,
    Tag,
)
from BeautifulSoup import BeautifulSoup as Soup
import requests
from django.utils.html import escape
from django.utils.text import slugify
from dateutil import parser
import datetime
import random


class Command(BaseCommand):
    help = "./manage.py import_quora http://URL-to-JSON.json"

    def add_arguments(self, parser):
        parser.add_argument('json_url', type=str)

    @transaction.atomic
    def handle(self, *args, **kwargs):
        data_url = kwargs['json_url']
        posts = requests.get(data_url).json()
        quora = Tag.objects.get_or_create(tag='quora')[0]
        for post in posts:
            question = post['originalQuestion'] or post['question']
            url = 'https://www.quora.com' + (post['originalQuestionUrl'] or post['href'])
            if question.endswith('Remove Banner'):
                question = question.replace('Remove Banner', '')
            answer = clean_answer(post['answer'])
            date = datetime.datetime.combine(
                parser.parse(post['meta'].replace('Added ', '')).date(),
                datetime.time(random.randint(9, 18), random.randint(0, 59))
            )
            truncated_question = question
            if len(truncated_question) > 250:
                truncated_question = truncated_question[:250] + u'...'
            body = u'<p><em>My answer to <a href="%s">%s</a> on Quora</em></p>' % (
                url, escape(question)
            )
            body += u'\n\n' + answer
            slug = slugify(' '.join(truncated_question.split()[:3]))
            entry = Entry.objects.create(
                slug=slug,
                created=date,
                title=truncated_question,
                body=body
            )
            entry.tags.add(quora)
            print entry


def clean_answer(html):
    soup = Soup(html)
    # Ditch class attributes
    for tag in ('p', 'span', 'a', 'code', 'div'):
        for el in soup.findAll(tag):
            del el['class']
    # On links, kill the rel and target and onclick and tooltip
    for el in soup.findAll('a'):
        del el['rel']
        del el['target']
        del el['onclick']
        del el['data-qt-tooltip']

    for el in soup.findAll('canvas'):
        el.extract()

    for img in soup.findAll('img'):
        del img['class']
        del img['data-src']
        src = img['master_src']
        del img['master_src']
        w = img['master_w']
        del img['master_w']
        h = img['master_h']
        del img['master_h']
        img['src'] = src
        img['width'] = w
        img['height'] = h
        img['style'] = 'max-width: 100%'
    return unicode(soup)
