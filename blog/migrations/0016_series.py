import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0015_enable_pg_trgm"),
    ]

    operations = [
        migrations.CreateModel(
            name="Series",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created", models.DateTimeField(default=datetime.datetime.utcnow)),
                ("slug", models.SlugField(max_length=64, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("summary", models.TextField()),
            ],
        ),
        migrations.AddField(
            model_name="blogmark",
            name="series",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="blog.series",
            ),
        ),
        migrations.AddField(
            model_name="entry",
            name="series",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="blog.series",
            ),
        ),
        migrations.AddField(
            model_name="quotation",
            name="series",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="blog.series",
            ),
        ),
    ]
