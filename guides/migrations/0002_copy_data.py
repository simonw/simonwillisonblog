from django.db import migrations


def copy_data(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    cursor = schema_editor.connection.cursor()

    # Copy Guide rows preserving PKs
    cursor.execute("""
        INSERT INTO guides_guide (id, created, updated, title, slug, description, is_draft)
        SELECT id, created, updated, title, slug, description, is_draft
        FROM blog_guide
    """)

    # Copy GuideSection rows preserving PKs
    cursor.execute("""
        INSERT INTO guides_guidesection (id, guide_id, title, slug, "order")
        SELECT id, guide_id, title, slug, "order"
        FROM blog_guidesection
    """)

    # Copy Chapter rows preserving PKs
    cursor.execute("""
        INSERT INTO guides_chapter (
            id, created, slug, metadata, search_document, import_ref,
            card_image, series_id, is_draft, guide_id, section_id,
            updated, title, body, "order"
        )
        SELECT
            id, created, slug, metadata, search_document, import_ref,
            card_image, series_id, is_draft, guide_id, section_id,
            updated, title, body, "order"
        FROM blog_chapter
    """)

    # Copy Chapter tags M2M
    cursor.execute("""
        INSERT INTO guides_chapter_tags (id, chapter_id, tag_id)
        SELECT id, chapter_id, tag_id
        FROM blog_chapter_tags
    """)

    # Copy ChapterChange rows preserving PKs
    cursor.execute("""
        INSERT INTO guides_chapterchange (id, chapter_id, created, title, body, is_draft, is_notable, change_note)
        SELECT id, chapter_id, created, title, body, is_draft, is_notable, change_note
        FROM blog_chapterchange
    """)

    # Reset sequences so new inserts get correct IDs
    cursor.execute("""
        SELECT setval(pg_get_serial_sequence('guides_guide', 'id'),
            COALESCE((SELECT MAX(id) FROM guides_guide), 0) + 1, false)
    """)
    cursor.execute("""
        SELECT setval(pg_get_serial_sequence('guides_guidesection', 'id'),
            COALESCE((SELECT MAX(id) FROM guides_guidesection), 0) + 1, false)
    """)
    cursor.execute("""
        SELECT setval(pg_get_serial_sequence('guides_chapter', 'id'),
            COALESCE((SELECT MAX(id) FROM guides_chapter), 0) + 1, false)
    """)
    cursor.execute("""
        SELECT setval(pg_get_serial_sequence('guides_chapter_tags', 'id'),
            COALESCE((SELECT MAX(id) FROM guides_chapter_tags), 0) + 1, false)
    """)
    cursor.execute("""
        SELECT setval(pg_get_serial_sequence('guides_chapterchange', 'id'),
            COALESCE((SELECT MAX(id) FROM guides_chapterchange), 0) + 1, false)
    """)


class Migration(migrations.Migration):

    dependencies = [
        ("guides", "0001_initial"),
        ("blog", "0044_chapter_section_fk"),
    ]

    operations = [
        migrations.RunPython(copy_data, migrations.RunPython.noop),
    ]
