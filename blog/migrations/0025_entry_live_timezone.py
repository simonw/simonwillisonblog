# Generated by Django 5.1.1 on 2024-10-01 17:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0024_liveupdate"),
    ]

    operations = [
        migrations.AddField(
            model_name="entry",
            name="live_timezone",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]