# -*- coding: utf-8 -*-


from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Blogmark",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("slug", models.SlugField(max_length=64)),
                ("link_url", models.URLField()),
                ("link_title", models.CharField(max_length=255)),
                ("via_url", models.URLField(null=True, blank=True)),
                ("via_title", models.CharField(max_length=255, null=True, blank=True)),
                ("commentary", models.TextField()),
                ("created", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="Entry",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=64)),
                ("body", models.TextField()),
                ("created", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="Photo",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("flickr_id", models.CharField(max_length=32)),
                ("server", models.CharField(max_length=8)),
                ("secret", models.CharField(max_length=32)),
                ("title", models.CharField(max_length=255, null=True, blank=True)),
                ("longitude", models.CharField(max_length=32, null=True, blank=True)),
                ("latitude", models.CharField(max_length=32, null=True, blank=True)),
                ("created", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="Photoset",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("flickr_id", models.CharField(max_length=32)),
                ("title", models.CharField(max_length=255, null=True, blank=True)),
                ("description", models.TextField()),
                (
                    "photos",
                    models.ManyToManyField(related_name="in_photoset", to="blog.Photo"),
                ),
                (
                    "primary",
                    models.ForeignKey(to="blog.Photo", on_delete=models.CASCADE),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Quotation",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("slug", models.SlugField(max_length=64)),
                ("quotation", models.TextField()),
                ("source", models.CharField(max_length=255)),
                ("source_url", models.URLField(null=True, blank=True)),
                ("created", models.DateTimeField()),
            ],
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                (
                    "id",
                    models.AutoField(
                        verbose_name="ID",
                        serialize=False,
                        auto_created=True,
                        primary_key=True,
                    ),
                ),
                ("tag", models.SlugField(unique=True)),
            ],
        ),
        migrations.AddField(
            model_name="quotation",
            name="tags",
            field=models.ManyToManyField(to="blog.Tag", blank=True),
        ),
        migrations.AddField(
            model_name="entry",
            name="tags",
            field=models.ManyToManyField(to="blog.Tag", blank=True),
        ),
        migrations.AddField(
            model_name="blogmark",
            name="tags",
            field=models.ManyToManyField(to="blog.Tag", blank=True),
        ),
    ]
