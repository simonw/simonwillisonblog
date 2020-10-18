# -*- coding: utf-8 -*-


from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ("contenttypes", "0002_remove_content_type_name"),
        ("blog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Comment",
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
                ("object_id", models.PositiveIntegerField(db_index=True)),
                ("body", models.TextField()),
                ("created", models.DateTimeField()),
                ("name", models.CharField(max_length=50)),
                ("url", models.URLField(max_length=255, null=True, blank=True)),
                ("email", models.CharField(max_length=50, null=True, blank=True)),
                ("openid", models.CharField(max_length=255, null=True, blank=True)),
                ("ip", models.GenericIPAddressField()),
                (
                    "spam_status",
                    models.CharField(
                        max_length=16,
                        choices=[
                            (b"normal", b"Not suspected"),
                            (b"approved", b"Approved"),
                            (b"suspected", b"Suspected"),
                            (b"spam", b"SPAM"),
                        ],
                    ),
                ),
                ("visible_on_site", models.BooleanField(default=True, db_index=True)),
                ("spam_reason", models.TextField()),
                (
                    "content_type",
                    models.ForeignKey(
                        to="contenttypes.ContentType", on_delete=models.CASCADE
                    ),
                ),
            ],
            options={
                "ordering": ["-created"],
                "get_latest_by": "created",
            },
        ),
        migrations.AlterModelOptions(
            name="blogmark",
            options={"ordering": ("-created",)},
        ),
        migrations.AlterModelOptions(
            name="entry",
            options={"ordering": ("-created",)},
        ),
        migrations.AlterModelOptions(
            name="quotation",
            options={"ordering": ("-created",)},
        ),
    ]
