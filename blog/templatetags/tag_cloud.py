from django import template
from django.utils.safestring import mark_safe

register = template.Library()

from blog.models import Tag

# Classes for different levels
CLASSES = (
    "--skip--",  # We don't show the least popular tags
    "not-popular-at-all",
    "not-very-popular",
    "somewhat-popular",
    "somewhat-more-popular",
    "popular",
    "more-than-just-popular",
    "very-popular",
    "ultra-popular",
)


def make_css_rules(
    min_size=0.7, max_size=2.0, units="em", selector_prefix=".tag-cloud ."
):
    num_classes = len(CLASSES)
    diff_each_time = (max_size - min_size) / (num_classes - 1)
    for i, klass in enumerate(CLASSES):
        print(
            "%s%s { font-size: %.2f%s; }"
            % (selector_prefix, klass, min_size + (i * diff_each_time), units)
        )


import math


def log(f):
    try:
        return math.log(f)
    except OverflowError:
        return 0


@register.inclusion_tag("includes/tag_cloud.html")
def tag_cloud_for_tags(tags):
    """
    Renders a tag cloud of tags. Input should be a non-de-duped list of tag
    strings.
    """
    return _tag_cloud_helper(tags)


def _tag_cloud_helper(tags):
    # Count them all up
    tag_counts = {}
    for tag in tags:
        try:
            tag_counts[tag] += 1
        except KeyError:
            tag_counts[tag] = 1
    min_count = min(tag_counts.values())
    max_count = max(tag_counts.values())
    tags = list(tag_counts.keys())
    tags.sort()
    html_tags = []
    intervals = 10.0
    log_max = log(max_count)
    log_min = log(min_count)
    diff = log_max - log_min
    if diff < 0.01:
        # Avoid divide-by-zero problems
        diff = 0.01
    for tag in tags:
        score = tag_counts[tag]
        index = int((len(CLASSES) - 1) * (log(score) - log_min) / diff)
        if CLASSES[index] == "--skip--":
            continue
        html_tags.append(
            mark_safe(
                '<a href="/tags/%s/" title="%d item%s" class="%s">%s</a>'
                % (tag, score, (score != 1 and "s" or ""), CLASSES[index], tag)
            )
        )
    return {"tags": html_tags}


@register.inclusion_tag("includes/tag_cloud.html")
def tag_cloud():
    # We do this with raw SQL for efficiency
    from django.db import connection

    # Get tags for entries, blogmarks, quotations
    cursor = connection.cursor()
    cursor.execute(
        "select tag from blog_entry_tags, blog_tag where blog_entry_tags.tag_id = blog_tag.id"
    )
    entry_tags = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "select tag from blog_blogmark_tags, blog_tag where blog_blogmark_tags.tag_id = blog_tag.id"
    )
    blogmark_tags = [row[0] for row in cursor.fetchall()]
    cursor.execute(
        "select tag from blog_quotation_tags, blog_tag where blog_quotation_tags.tag_id = blog_tag.id"
    )
    quotation_tags = [row[0] for row in cursor.fetchall()]
    cursor.close()
    # Add them together
    tags = entry_tags + blogmark_tags + quotation_tags
    return _tag_cloud_helper(tags)
