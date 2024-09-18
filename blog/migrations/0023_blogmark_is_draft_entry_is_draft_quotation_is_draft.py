# Generated by Django 5.1 on 2024-09-18 05:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0022_alter_blogmark_use_markdown"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogmark",
            name="is_draft",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="entry",
            name="is_draft",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="quotation",
            name="is_draft",
            field=models.BooleanField(default=False),
        ),
    ]