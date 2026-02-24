# Design: Guide Sections

Optional ordered groupings of chapters within a guide. Sections are purely
organizational — they affect the table of contents and sidebar display but
do not have their own pages or URLs.

## Example structure

```
NAME OF GUIDE
- Getting started          (standalone chapter, order=0)
- Basics                   (section, order=1)
  - Glossary               (chapter in section, order=0)
  - Installation           (chapter in section, order=1)
- Intermediate             (section, order=2)
  - Chapter A              (chapter in section, order=0)
  - Chapter B              (chapter in section, order=1)
- Appendix                 (section, order=3)
  - Chapter C              (chapter in section, order=0)
```

Standalone chapters and sections share a single ordering namespace at the
guide level. A standalone chapter with `order=0` appears before a section
with `order=1`. Chapters inside a section use `order` for positioning
within that section.

## New model: `GuideSection`

```python
class GuideSection(models.Model):
    guide = models.ForeignKey(Guide, related_name="sections", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64)
    order = models.IntegerField(default=0)

    class Meta:
        ordering = ("order",)
        unique_together = (("guide", "slug"),)

    def __str__(self):
        return self.title
```

No `is_draft`, no `description`, no `get_absolute_url`. Sections are
display-only containers.

## Change to `Chapter` model

Add one nullable FK:

```python
section = models.ForeignKey(
    GuideSection,
    related_name="chapters",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
)
```

`SET_NULL` on delete: if a section is removed, its chapters become
standalone rather than being deleted.

The existing `order` field on Chapter continues to work as before. For
chapters in a section, `order` determines position within the section.
For standalone chapters, `order` determines position among top-level
items alongside sections.

## Migration

One migration:
1. Create `GuideSection` table
2. Add nullable `section` FK to `Chapter`

Fully backwards-compatible. All existing chapters remain standalone
(section=NULL). Existing guides render identically to today.

## Admin changes

Remove all inlines from guide-related admin classes:
- Remove `ChapterInline` from `GuideAdmin`
- Remove `ChapterChangeInline` from `ChapterAdmin`

Add `GuideSectionAdmin`:
- `list_display`: `title`, `guide`, `order`
- `list_filter`: `guide`
- `prepopulated_fields`: `slug` from `title`

Update `ChapterAdmin`:
- Add `section` to fields/list_display
- Add `section` to `list_filter`

Ordering is managed by manually editing the `order` integers. A better
reordering tool can be built later.

## View changes

### `guide_detail` view

Build a TOC data structure that interleaves standalone chapters and
sections:

```python
def build_guide_toc(guide, include_drafts=False):
    """
    Returns a list of items, each either:
      {"type": "chapter", "order": int, "chapter": Chapter}
      {"type": "section", "order": int, "section": GuideSection, "chapters": [Chapter, ...]}
    Sorted by order. Empty sections are excluded.
    """
    qs = guide.chapters.all()
    if not include_drafts:
        qs = qs.filter(is_draft=False)

    standalone = list(qs.filter(section__isnull=True).order_by("order", "created"))
    sections = guide.sections.order_by("order")

    toc = []
    for ch in standalone:
        toc.append({"type": "chapter", "order": ch.order, "chapter": ch})

    for sec in sections:
        sec_chapters = list(qs.filter(section=sec).order_by("order", "created"))
        if sec_chapters:  # hide empty sections
            toc.append({
                "type": "section",
                "order": sec.order,
                "section": sec,
                "chapters": sec_chapters,
            })

    toc.sort(key=lambda item: item["order"])
    return toc
```

Pass `toc` to the template instead of `chapters`.

### Flattening for navigation

Prev/next navigation ignores sections entirely — it walks the flat
reading order:

```python
def flatten_toc(toc):
    flat = []
    for item in toc:
        if item["type"] == "chapter":
            flat.append(item["chapter"])
        else:
            flat.extend(item["chapters"])
    return flat
```

`chapter_detail` uses `flatten_toc` for computing `previous_chapter` and
`next_chapter`, exactly as the current view does.

### `chapter_detail` view

The sidebar chapter list uses the same TOC structure to show sections as
non-clickable headings with their chapters nested beneath.

Pass both `toc` (for sidebar) and `flat_chapters` (for prev/next) to the
template context.

## Template changes

### `guide_detail.html`

```html
<ol style="margin-top: 1em">
  {% for item in toc %}
    {% if item.type == "chapter" %}
      <li style="margin-left: 2em; list-style-type: decimal; margin-bottom: 0.3em">
        <a href="{{ item.chapter.get_absolute_url }}">{{ item.chapter.title }}</a>
        {% if item.chapter.is_draft %} <em>(draft)</em>{% endif %}
      </li>
    {% elif item.type == "section" %}
      <li style="margin-left: 2em; list-style-type: none; margin-bottom: 0.3em">
        <strong>{{ item.section.title }}</strong>
        <ol>
          {% for ch in item.chapters %}
            <li style="margin-left: 2em; list-style-type: decimal; margin-bottom: 0.3em">
              <a href="{{ ch.get_absolute_url }}">{{ ch.title }}</a>
              {% if ch.is_draft %} <em>(draft)</em>{% endif %}
            </li>
          {% endfor %}
        </ol>
      </li>
    {% endif %}
  {% endfor %}
</ol>
```

### `chapter_detail.html` sidebar

Same nested structure in the `{% block secondary %}` sidebar list,
highlighting the current chapter:

```html
<ol>
  {% for item in toc %}
    {% if item.type == "chapter" %}
      {% if item.chapter.pk == chapter.pk %}
        <li><strong>{{ item.chapter.title }}</strong></li>
      {% else %}
        <li><a href="{{ item.chapter.get_absolute_url }}">{{ item.chapter.title }}</a></li>
      {% endif %}
    {% elif item.type == "section" %}
      <li>
        <strong>{{ item.section.title }}</strong>
        <ol>
          {% for ch in item.chapters %}
            {% if ch.pk == chapter.pk %}
              <li><strong>{{ ch.title }}</strong></li>
            {% else %}
              <li><a href="{{ ch.get_absolute_url }}">{{ ch.title }}</a></li>
            {% endif %}
          {% endfor %}
        </ol>
      </li>
    {% endif %}
  {% endfor %}
</ol>
```

## What does NOT change

- **URL structure**: chapters stay at `/guides/{guide-slug}/{chapter-slug}/`
- **ChapterChange tracking**: unaffected, sections are not tracked content
- **Search indexing**: chapters index the same way
- **`guide_index` view**: shows guide listing with chapter counts, unchanged
- **Prev/next navigation logic**: still flat linear walk, sections invisible
- **Draft system**: guide and chapter `is_draft` flags work as before
- **Feeds, archives, homepage**: chapters appear in these based on existing
  logic, sections have no effect

## Files to modify

| File | Change |
|------|--------|
| `blog/models.py` | Add `GuideSection` model, add `section` FK to `Chapter` |
| `blog/admin.py` | Remove inlines, add `GuideSectionAdmin`, update `ChapterAdmin` |
| `blog/views.py` | Add `build_guide_toc`/`flatten_toc`, update `guide_detail` and `chapter_detail` |
| `templates/guide_detail.html` | Render nested TOC |
| `templates/chapter_detail.html` | Render nested sidebar |
| `blog/factories.py` | Add `GuideSectionFactory` |
| `blog/tests.py` | Add section tests, update existing tests for removed inlines |
| `blog/migrations/00XX_*.py` | Generated migration |
