from django.db import migrations


def is_pasted_live_updates_js(html):
    # The copy-and-paste live blog script that poll_live_updates replaces:
    # https://gist.github.com/simonw/713df0fae62e2b03fe794e75beb6253e
    html = (html or "").strip()
    return (
        html.startswith("<script>")
        and html.endswith("</script>")
        and html.count("<script") == 1
        and "pollUpdates" in html
        and "addSortToggleLink" in html
    )


def remove_pasted_live_updates_js(apps, schema_editor):
    Entry = apps.get_model("blog", "Entry")
    for entry in Entry.objects.filter(extra_head_html__contains="pollUpdates"):
        if is_pasted_live_updates_js(entry.extra_head_html):
            entry.extra_head_html = ""
            entry.save(update_fields=["extra_head_html"])


class Migration(migrations.Migration):

    dependencies = [
        ("blog", "0052_entry_poll_live_updates"),
    ]

    operations = [
        migrations.RunPython(
            remove_pasted_live_updates_js,
            migrations.RunPython.noop,
        ),
    ]
