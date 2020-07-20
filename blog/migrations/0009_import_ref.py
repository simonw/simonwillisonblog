from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0008_entry_tweet_html"),
    ]

    operations = [
        migrations.AddField(
            model_name="blogmark",
            name="import_ref",
            field=models.TextField(max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="entry",
            name="import_ref",
            field=models.TextField(max_length=64, null=True, unique=True),
        ),
        migrations.AddField(
            model_name="quotation",
            name="import_ref",
            field=models.TextField(max_length=64, null=True, unique=True),
        ),
    ]
