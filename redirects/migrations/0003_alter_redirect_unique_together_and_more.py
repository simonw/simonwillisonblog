# Generated by Django 5.1 on 2024-08-13 22:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("redirects", "0002_auto_20171001_2242"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="redirect",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="redirect",
            constraint=models.UniqueConstraint(
                fields=("domain", "path"), name="unique_redirect"
            ),
        ),
    ]
