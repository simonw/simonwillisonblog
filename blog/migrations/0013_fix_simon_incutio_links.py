from django.db import migrations
from django.utils.dates import MONTHS_3
import re

MONTHS_3_REV = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
MONTHS_3_REV_REV = {value: key for key, value in list(MONTHS_3_REV.items())}

url_re = re.compile(
    r'"http://simon\.incutio\.com/archive/(\d{4})/(\d{2})/(\d{2})/(.*?)"'
)


def fix_url(m):
    yyyy, mm, dd, slug = m.groups()
    month = MONTHS_3_REV_REV[int(mm)].title()
    return '"/{}/{}/{}/{}/"'.format(yyyy, month, dd, slug.replace("#", ""))


def fix_simon_incutio_links(apps, schema_editor):
    Entry = apps.get_model("blog", "Entry")
    actually_fix_them(Entry)


def actually_fix_them(Entry):
    for entry in Entry.objects.filter(body__icontains="simon.incutio"):
        new_body = url_re.sub(fix_url, entry.body)
        if new_body != entry.body:
            Entry.objects.filter(pk=entry.pk).update(body=new_body)
            path = "/%d/%s/%d/%s/" % (
                entry.created.year,
                MONTHS_3[entry.created.month].title(),
                entry.created.day,
                entry.slug,
            )
            print("Updated https://simonwillison.net{}".format(path))


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0012_card_image"),
    ]

    operations = [
        migrations.RunPython(fix_simon_incutio_links),
    ]
