from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0047_beat_note"),
    ]

    operations = [
        migrations.AlterField(
            model_name="beat",
            name="beat_type",
            field=models.CharField(
                choices=[
                    ("release", "Release"),
                    ("til", "TIL"),
                    ("til_update", "TIL updated"),
                    ("research", "Research"),
                    ("tool", "Tool"),
                    ("museum", "Museum"),
                    ("sighting", "Sighting"),
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
