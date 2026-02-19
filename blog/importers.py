import re
from datetime import datetime, timezone

import httpx
import json
from dateutil.parser import parse as parse_datetime

from blog.models import Beat
from blog.management.commands._beat_utils import truncate, unique_slug


def _create_or_update(import_ref, defaults):
    """
    Like update_or_create but only counts as 'updated' if data actually changed.
    Returns (beat, "created" | "updated" | "skipped").
    """
    try:
        existing = Beat.objects.get(import_ref=import_ref)
    except Beat.DoesNotExist:
        beat = Beat.objects.create(import_ref=import_ref, **defaults)
        return beat, "created"

    changed = False
    for key, value in defaults.items():
        if getattr(existing, key) != value:
            changed = True
            setattr(existing, key, value)

    if changed:
        existing.save()
        return existing, "updated"
    return existing, "skipped"


def import_releases(url):
    response = httpx.get(url)
    response.raise_for_status()
    repos = response.json()

    created_count = 0
    skipped_count = 0
    items = []

    for repo_name, info in repos.items():
        description = info.get("description") or ""
        for release in info.get("releases", []):
            version = release["release"]
            import_ref = "release:{}:{}".format(repo_name, version)

            if Beat.objects.filter(import_ref=import_ref).exists():
                skipped_count += 1
                continue

            title = "{} {}".format(repo_name, version)
            created = parse_datetime(release["published_at"])

            beat = Beat.objects.create(
                beat_type="release",
                title=title,
                url=release["url"],
                slug=unique_slug(repo_name, created, import_ref),
                created=created,
                import_ref=import_ref,
                commentary=description,
            )
            items.append(beat)
            created_count += 1

    return {"created": created_count, "skipped": skipped_count, "items": items}


def import_research(url):
    response = httpx.get(url)
    response.raise_for_status()
    text = response.text

    heading_pattern = re.compile(
        r"^### \[([^\]]+)\]\(([^)]+)\) \((\d{4}-\d{2}-\d{2})\)",
        re.MULTILINE,
    )

    matches = list(heading_pattern.finditer(text))
    created_count = 0
    updated_count = 0
    skipped_count = 0
    items = []

    for i, match in enumerate(matches):
        title = match.group(1)
        project_url = match.group(2)
        if not project_url.endswith("#readme"):
            project_url += "#readme"
        date_str = match.group(3)
        created = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        import_ref = "research:{}".format(title)

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        first_para = body.split("\n\n")[0].strip()
        first_para = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", first_para)
        commentary = truncate(first_para)

        defaults = {
            "beat_type": "research",
            "title": title,
            "url": project_url,
            "slug": unique_slug(title, created, import_ref),
            "created": created,
            "commentary": commentary,
        }

        beat, status = _create_or_update(import_ref, defaults)
        if status == "created":
            created_count += 1
            items.append(beat)
        elif status == "updated":
            updated_count += 1
            items.append(beat)
        else:
            skipped_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "items": items,
    }


def import_tils(url):
    response = httpx.get(url)
    response.raise_for_status()
    tils = response.json()

    created_count = 0
    updated_count = 0
    skipped_count = 0
    items = []

    for til in tils:
        topic = til["topic"]
        slug = til["slug"]
        import_ref = "til:{}/{}".format(topic, slug)
        til_url = "https://til.simonwillison.net/{}/{}".format(topic, slug)

        body = (til.get("body") or "").strip()
        first_line = body.split("\n")[0].strip()
        if first_line.startswith("# "):
            lines = [l.strip() for l in body.split("\n")[1:] if l.strip()]
            first_line = lines[0] if lines else ""
        commentary = truncate(first_line)

        created = parse_datetime(til["created_utc"])
        defaults = {
            "beat_type": "til_new",
            "title": til["title"],
            "url": til_url,
            "slug": unique_slug(slug, created, import_ref),
            "created": created,
            "commentary": commentary,
        }

        beat, status = _create_or_update(import_ref, defaults)
        if status == "created":
            created_count += 1
            items.append(beat)
        elif status == "updated":
            updated_count += 1
            items.append(beat)
        else:
            skipped_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "items": items,
    }


def import_tools(url):
    response = httpx.get(url)
    response.raise_for_status()
    tools = response.json()

    created_count = 0
    updated_count = 0
    skipped_count = 0
    items = []

    for tool in tools:
        import_ref = "tool:{}".format(tool["filename"])
        created = parse_datetime(tool["created"])
        defaults = {
            "beat_type": "tool",
            "title": tool["title"],
            "url": "https://tools.simonwillison.net/colophon#{}".format(
                tool["filename"]
            ),
            "slug": unique_slug(tool["slug"], created, import_ref),
            "created": created,
            "commentary": truncate(tool.get("description") or ""),
        }

        beat, status = _create_or_update(import_ref, defaults)
        if status == "created":
            created_count += 1
            items.append(beat)
        elif status == "updated":
            updated_count += 1
            items.append(beat)
        else:
            skipped_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "items": items,
    }


def import_museums(url):
    response = httpx.get(url)
    response.raise_for_status()
    museums = json.loads(response.text)

    created_count = 0
    updated_count = 0
    skipped_count = 0
    items = []

    for museum in museums:
        museum_url = museum.get("url") or ""
        if not museum_url:
            continue

        museum_id = museum_url.rstrip("/").split("/")[-1]
        import_ref = "museum:{}".format(museum_id)

        name = museum["name"]
        address = museum.get("address") or ""

        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        created = datetime.fromisoformat(museum["created"])

        photo_url = museum.get("photo_url") or ""
        image_url = (photo_url + "?h=200") if photo_url else ""
        image_alt = museum.get("photo_alt") or ""

        defaults = {
            "beat_type": "museum",
            "title": name,
            "url": museum_url,
            "slug": unique_slug(slug, created, import_ref),
            "created": created,
            "commentary": address,
            "image_url": image_url or None,
            "image_alt": image_alt or None,
        }

        beat, status = _create_or_update(import_ref, defaults)
        if status == "created":
            created_count += 1
            items.append(beat)
        elif status == "updated":
            updated_count += 1
            items.append(beat)
        else:
            skipped_count += 1

    return {
        "created": created_count,
        "updated": updated_count,
        "skipped": skipped_count,
        "items": items,
    }
