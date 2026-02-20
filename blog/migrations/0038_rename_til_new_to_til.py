from django.db import migrations, models


def rename_til_new_to_til(apps, schema_editor):
    Beat = apps.get_model("blog", "Beat")
    Beat.objects.filter(beat_type="til_new").update(beat_type="til")


def rename_til_to_til_new(apps, schema_editor):
    Beat = apps.get_model("blog", "Beat")
    Beat.objects.filter(beat_type="til").update(beat_type="til_new")


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0037_add_beat_image_fields"),
    ]

    operations = [
        migrations.RunPython(rename_til_new_to_til, rename_til_to_til_new),
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
                ],
                db_index=True,
                max_length=20,
            ),
        ),
    ]
