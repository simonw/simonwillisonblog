from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0056_newsletter_subtitle"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sponsormessage",
            name="message",
            field=models.TextField(
                help_text="Rendered as Markdown, so it can include inline links."
            ),
        ),
        migrations.AlterField(
            model_name="sponsormessage",
            name="learn_more_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Optional. Links the sponsor name, or the label if one is set.",
            ),
        ),
        migrations.AlterField(
            model_name="sponsormessage",
            name="learn_more_label",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Optional. Shown as a link after the message. Requires a URL.",
                max_length=255,
            ),
        ),
    ]
