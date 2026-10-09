"""Repeatable imports for newsletter metadata and public monthly content."""

import datetime
import json
import re
import subprocess
import tempfile
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from django.db import transaction
from django.utils.text import slugify

from .models import Newsletter

SUBSTACK_FEED = "https://simonw.substack.com/feed"
MONTHLY_REPOSITORY = "https://github.com/simonw/monthly-newsletter-archive"
PRIVATE_MONTHLY_REPOSITORY = "https://github.com/simonw-private/monthly"


def substack_records(feed_xml):
    root = ElementTree.fromstring(feed_xml)
    items = root.findall("./channel/item")
    if root.tag != "rss" or root.find("channel") is None:
        raise ValueError("Expected a Substack RSS feed")
    records = []
    for item in items:
        title = item.findtext("title", "").strip()
        url = item.findtext("link", "").strip()
        if not title or not url:
            raise ValueError("Every Substack issue needs a title and URL")
        date = parsedate_to_datetime(item.findtext("pubDate", ""))
        if date.tzinfo is None:
            raise ValueError("Substack publication dates must include a timezone")
        enclosure = item.find("enclosure")
        records.append(
            {
                "import_ref": "substack:" + url,
                "kind": Newsletter.Kind.SUBSTACK,
                "title": title,
                "slug": "substack-"
                + slugify(urlparse(url).path.rstrip("/").split("/")[-1]),
                "created": date,
                "url": url,
                "card_image": enclosure.get("url", "") if enclosure is not None else "",
                "body": "",
                "is_public": True,
                "metadata": {"date_source": "substack_publication"},
            }
        )
    return records


def _git(checkout, *args):
    return subprocess.run(
        ["git", "-C", str(checkout), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def monthly_records(checkout):
    """Read committed public content; archive commits retain original source dates."""
    revision = _git(checkout, "rev-parse", "HEAD")
    filenames = json.loads(_git(checkout, "show", f"{revision}:index.json"))
    if not isinstance(filenames, list):
        raise ValueError("Monthly archive index must be a list of filenames")
    records = []
    for filename in filenames:
        if not isinstance(filename, str) or not re.fullmatch(
            r"\d{4}-\d{2}-[a-z]+\.md", filename
        ):
            raise ValueError(f"Unexpected monthly newsletter filename: {filename!r}")
        body = _git(checkout, "show", f"{revision}:{filename}")
        heading = re.search(r"^# (.+)$", body, re.MULTILINE)
        issue_date = datetime.date.fromisoformat(filename[:7] + "-01")
        title = (
            heading.group(1).strip() if heading else f"LLM digest: {issue_date:%B %Y}"
        )
        dates = _git(
            checkout,
            "log",
            "--follow",
            "--diff-filter=A",
            "--format=%cI",
            revision,
            "--",
            filename,
        ).splitlines()
        if not dates:
            raise ValueError(f"Missing original commit date for {filename}")
        created = datetime.datetime.fromisoformat(dates[-1])
        records.append(
            {
                "import_ref": "monthly:" + filename,
                "kind": Newsletter.Kind.SPONSOR,
                "title": title,
                "slug": "monthly-" + filename[:-3],
                "created": created,
                "url": f"{MONTHLY_REPOSITORY}/blob/main/{filename}",
                "body": body,
                "is_public": True,
                "metadata": {
                    "issue_month": filename[:7],
                    "date_source": "original_source_commit",
                    "source_filename": filename,
                    "source_revision": revision,
                    "title_source": "heading" if heading else "issue_month",
                },
            }
        )
    return records


def save_records(records, dry_run=False, include_items=False):
    counts = {"created": 0, "updated": 0, "skipped": 0}
    # Validate every record before saving any of them, including during dry runs.
    pending = []
    seen = set()
    for record in records:
        data = record.copy()
        import_ref = data.pop("import_ref")
        if import_ref in seen:
            raise ValueError(f"Duplicate newsletter source: {import_ref}")
        seen.add(import_ref)
        existing = Newsletter.objects.filter(import_ref=import_ref).first()
        obj = existing or Newsletter(import_ref=import_ref)
        if existing:
            # Preserve editorial choices unrelated to the imported source.
            data.pop("slug", None)
            data["metadata"] = {**obj.metadata, **data.get("metadata", {})}
        changed = any(getattr(obj, key) != value for key, value in data.items())
        for key, value in data.items():
            setattr(obj, key, value)
        obj.full_clean()
        status = "created" if existing is None else "updated" if changed else "skipped"
        counts[status] += 1
        if status != "skipped":
            pending.append(obj)
    if not dry_run:
        with transaction.atomic():
            for obj in pending:
                obj.save()
    if include_items:
        counts["items"] = pending
    return counts


def import_substack(url=SUBSTACK_FEED, dry_run=False, include_items=False):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return save_records(
        substack_records(response.content), dry_run=dry_run, include_items=include_items
    )


def substack_archive_records(posts):
    records = []
    for post in posts:
        url = post["canonical_url"]
        date = datetime.datetime.fromisoformat(post["post_date"])
        if date.tzinfo is None:
            raise ValueError("Substack publication dates must include a timezone")
        records.append(
            {
                "import_ref": "substack:" + url,
                "kind": Newsletter.Kind.SUBSTACK,
                "title": post["title"],
                "slug": "substack-"
                + slugify(urlparse(url).path.rstrip("/").split("/")[-1]),
                # Match RSS precision so an RSS refresh doesn't change the send date.
                "created": date.replace(microsecond=0),
                "url": url,
                "card_image": post.get("cover_image") or "",
                "body": "",
                "is_public": True,
                "metadata": {"date_source": "substack_publication"},
            }
        )
    return records


def fetch_substack_archive_page(offset):
    response = requests.get(
        "https://simonw.substack.com/api/v1/archive",
        params={"sort": "new", "offset": offset, "limit": 12},
        timeout=20,
    )
    response.raise_for_status()
    posts = response.json()
    if not isinstance(posts, list):
        raise ValueError("Expected a list from the Substack archive")
    return substack_archive_records(posts)


def import_substack_archive_page(offset=0):
    records = fetch_substack_archive_page(offset)
    result = save_records(records, include_items=True)
    result["next_offset"] = offset + 12 if records else None
    result["source_refs"] = [record["import_ref"] for record in records]
    return result


def import_substack_archive(dry_run=False):
    records = []
    seen = set()
    # This is Substack's website endpoint, not a documented stable API.
    for offset in range(0, 12000, 12):
        page = fetch_substack_archive_page(offset)
        if not page:
            return save_records(records, dry_run=dry_run)
        for record in page:
            if record["import_ref"] in seen:
                raise ValueError(
                    "Substack archive returned duplicate posts; retry the import"
                )
            seen.add(record["import_ref"])
        records.extend(page)
    raise ValueError("Substack archive pagination exceeded the import limit")


def private_monthly_records(checkout, public_records):
    """Import only listing metadata for issues not already available publicly."""
    public_refs = {record["import_ref"] for record in public_records}
    public_refs.update(
        Newsletter.objects.filter(kind=Newsletter.Kind.SPONSOR, is_public=True)
        .exclude(import_ref=None)
        .values_list("import_ref", flat=True)
    )
    revision = _git(checkout, "rev-parse", "HEAD")
    filenames = _git(checkout, "ls-tree", "--name-only", revision).splitlines()
    records = []
    for filename in filenames:
        if not re.fullmatch(r"\d{4}-\d{2}-[a-z]+\.md", filename):
            continue
        import_ref = "monthly:" + filename
        if import_ref in public_refs:
            continue
        # The private body is never stored in the blog database or metadata.
        first_line = _git(checkout, "show", f"{revision}:{filename}").split("\n", 1)[0]
        issue_date = datetime.date.fromisoformat(filename[:7] + "-01")
        title = (
            first_line[2:].strip()
            if first_line.startswith("# ")
            else f"LLM digest: {issue_date:%B %Y}"
        )
        dates = _git(
            checkout,
            "log",
            "--follow",
            "--diff-filter=A",
            "--format=%cI",
            revision,
            "--",
            filename,
        ).splitlines()
        if not dates:
            raise ValueError(f"Missing original commit date for {filename}")
        records.append(
            {
                "import_ref": import_ref,
                "kind": Newsletter.Kind.SPONSOR,
                "title": title,
                "slug": "monthly-" + filename[:-3],
                "created": datetime.datetime.fromisoformat(dates[-1]),
                "url": f"{PRIVATE_MONTHLY_REPOSITORY}/blob/main/{filename}",
                "is_public": False,
                "metadata": {
                    "issue_month": filename[:7],
                    "date_source": "original_source_commit",
                    "source_filename": filename,
                    "source_revision": revision,
                    "title_source": (
                        "heading" if first_line.startswith("# ") else "issue_month"
                    ),
                },
            }
        )
    return records


def import_monthly(checkout=None, dry_run=False, private_checkout=None):
    def import_checkout(public_checkout):
        records = monthly_records(public_checkout)
        if private_checkout:
            records.extend(private_monthly_records(private_checkout, records))
        return save_records(records, dry_run=dry_run)

    if checkout:
        return import_checkout(Path(checkout))
    with tempfile.TemporaryDirectory(prefix="monthly-newsletters-") as directory:
        subprocess.run(
            ["git", "clone", "--quiet", MONTHLY_REPOSITORY + ".git", directory],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return import_checkout(directory)
