from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0014_entry_custom_template"),
    ]

    operations = [TrigramExtension()]
