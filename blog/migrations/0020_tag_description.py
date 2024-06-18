from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0019_blogmark_use_markdown"),
    ]

    operations = [
        migrations.AddField(
            model_name="tag",
            name="description",
            field=models.TextField(blank=True),
        ),
    ]
