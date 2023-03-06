from django.core.management.base import BaseCommand
from datetime import timezone
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
    help = "./manage.py import_quora http://URL-to-JSON.json http://URL-to-topic-CSV"

    def add_arguments(self, parser):
        parser.add_argument("json_url", type=str)
        parser.add_argument("topic_csv_url", type=str)

    def handle(self, *args, **kwargs):
        data_url = kwargs["json_url"]
        topic_csv_url = kwargs["topic_csv_url"]
        lines = requests.get(topic_csv_url).content.split("\n")
        quora_to_tag = {
            line.split("\t")[0]: line.split("\t")[-1].strip()
            for line in lines
            if line.strip()
        }
        posts = requests.get(data_url).json()
        with transaction.atomic():
            quora = Tag.objects.get_or_create(tag="quora")[0]
        for post in posts:
            question = post["originalQuestion"] or post["question"]
            url = "https://www.quora.com" + (
                post["originalQuestionUrl"] or post["href"]
            )
            if question.endswith("Remove Banner"):
                question = question.replace("Remove Banner", "")
            answer = clean_answer(post["answer"])
            date = datetime.datetime.combine(
                parser.parse(post["meta"].replace("Added ", "")).date(),
                datetime.time(random.randint(9, 18), random.randint(0, 59)),
            ).replace(tzinfo=timezone.utc)
            truncated_question = question
            if len(truncated_question) > 250:
                truncated_question = truncated_question[:250] + "..."
            body = '<p><em>My answer to <a href="%s">%s</a> on Quora</em></p>' % (
                url,
                escape(question),
            )
            body += "\n\n" + answer
            body = body.replace("&nbsp;", " ")
            slug = slugify(" ".join(truncated_question.split()[:4]))
            with transaction.atomic():
                entry = Entry.objects.create(
                    slug=slug,
                    created=date,
                    title=truncated_question,
                    body=body,
                    metadata=post,
                )
                entry.tags.add(quora)
                for topic in post["topics"]:
                    tag = quora_to_tag.get(topic)
                    if tag:
                        entry.tags.add(Tag.objects.get_or_create(tag=tag)[0])
            print(entry)


def clean_answer(html):
    soup = Soup(html)
    # Ditch class attributes
    for tag in ("p", "span", "a", "code", "div"):
        for el in soup.findAll(tag):
            del el["class"]
    # On links, kill the rel and target and onclick and tooltip
    for el in soup.findAll("a"):
        del el["rel"]
        del el["target"]
        del el["onclick"]
        del el["data-qt-tooltip"]

    for el in soup.findAll("canvas"):
        el.extract()

    for img in soup.findAll("img"):
        del img["class"]
        del img["data-src"]
        src = img["master_src"]
        del img["master_src"]
        w = img["master_w"]
        del img["master_w"]
        h = img["master_h"]
        del img["master_h"]
        img["src"] = src
        img["width"] = w
        img["height"] = h
        img["style"] = "max-width: 100%"

    # Cleanup YouTube videos
    for div in soup.findAll("div", {"data-video-provider": "youtube"}):
        iframe = Soup(div["data-embed"]).find("iframe")
        src = "https:%s" % iframe["src"].split("?")[0]
        div.replaceWith(
            Soup(
                """
            <iframe width="560" height="315"
                src="%s" frameborder="0" allowfullscreen>
            </iframe>
        """
                % src
            )
        )

    html = str(soup)
    html = html.replace('<a href="/', '<a href="https://www.quora.com/')
    # Replace <br /><br /> with paragraphs
    chunks = html.split("<br /><br />")
    new_chunks = []
    for chunk in chunks:
        if not chunk.startswith("<"):
            chunk = "<p>%s</p>" % chunk
        new_chunks.append(chunk)
    return "\n\n".join(new_chunks)
