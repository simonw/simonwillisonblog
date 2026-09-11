from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("guides", "0003_chapter_is_unlisted"),
    ]

    operations = [
        # Existing revisions have no record of the guide's visibility when
        # they were saved. Leave them NULL so they are only visible to staff.
        migrations.AddField(
            model_name="chapterchange",
            name="guide_is_draft",
            field=models.BooleanField(null=True),
        ),
    ]
