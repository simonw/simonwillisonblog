"""Repeatable imports for newsletter metadata and public monthly content."""

import datetime
import re
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup
from markdown import markdown
from django.conf import settings
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone

from .models import Newsletter

SUBSTACK_FEED = "https://simonw.substack.com/feed"
MONTHLY_REPOSITORY = "https://github.com/simonw/monthly-newsletter-archive"
MONTHLY_RAW = "https://raw.githubusercontent.com/simonw/monthly-newsletter-archive/main"
PRIVATE_MONTHLY_REPOSITORY = "https://github.com/simonw-private/monthly"


class NewsletterImportRateLimitError(Exception):
    """A safe, user-facing error containing only rate-limit timing details."""


def check_github_rate_limit(response):
    if response.status_code not in (403, 429):
        return
    limited = (
        response.status_code == 429
        or response.headers.get("X-RateLimit-Remaining") == "0"
        or bool(response.headers.get("Retry-After"))
    )
    if not limited:
        try:
            data = response.json()
            limited = (
                isinstance(data, dict)
                and "rate limit" in str(data.get("message", "")).lower()
            )
        except ValueError:
            pass
    if not limited:
        return
    message = "GitHub API rate limit exceeded."
    retry_after = response.headers.get("Retry-After", "")
    reset = response.headers.get("X-RateLimit-Reset", "")
    if retry_after.isdigit():
        message += f" Try again in {int(retry_after)} seconds."
    elif reset.isdigit():
        try:
            reset_time = timezone.localtime(
                datetime.datetime.fromtimestamp(int(reset), datetime.timezone.utc)
            )
            message += f" Try again after {reset_time:%B %d at %I:%M %p %Z}."
        except (ValueError, OverflowError, OSError):
            pass
    if message == "GitHub API rate limit exceeded.":
        message += " Please try again later."
    raise NewsletterImportRateLimitError(message)


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


def monthly_index():
    """Read and validate the public index before fetching any issue bodies."""
    response = requests.get(f"{MONTHLY_RAW}/index.json", timeout=20)
    response.raise_for_status()
    issues = response.json()
    if not isinstance(issues, list):
        raise ValueError("Monthly archive index must be a list of dated issues")
    seen = set()
    dated_issues = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError(
                "Monthly archive index needs filename and sent_at for each issue"
            )
        filename = issue.get("filename")
        if not isinstance(filename, str) or not re.fullmatch(
            r"\d{4}-\d{2}-[a-z]+\.md", filename
        ):
            raise ValueError(f"Unexpected monthly newsletter filename: {filename!r}")
        if filename in seen:
            raise ValueError("Monthly archive index contains duplicate filenames")
        seen.add(filename)
        sent_at = issue.get("sent_at")
        if not isinstance(sent_at, str):
            raise ValueError(f"Missing send date for {filename}")
        created = datetime.datetime.fromisoformat(sent_at)
        if created.tzinfo is None:
            raise ValueError(f"Send date must include a timezone for {filename}")
        dated_issues.append((filename, created))
    return dated_issues


def monthly_records(dated_issues=None):
    """Fetch the public index and Markdown over HTTP, with no local checkout."""
    if dated_issues is None:
        dated_issues = monthly_index()
    records = []
    for filename, created in dated_issues:
        response = requests.get(f"{MONTHLY_RAW}/{filename}", timeout=20)
        response.raise_for_status()
        body = response.content.decode("utf-8").strip()
        headings = BeautifulSoup(markdown(body, extensions=["extra"]), "html.parser")
        heading = re.search(r"^# (.+)$", body, re.MULTILINE)
        issue_date = datetime.date.fromisoformat(filename[:7] + "-01")
        title = (
            heading.group(1).strip() if heading else f"LLM digest: {issue_date:%B %Y}"
        )
        records.append(
            {
                "import_ref": "monthly:" + filename,
                "kind": Newsletter.Kind.SPONSOR,
                "title": title,
                "slug": "monthly-" + filename[:-3],
                "created": created,
                "url": f"{MONTHLY_REPOSITORY}/blob/main/{filename}",
                "body": body,
                "preview_headings": "\n".join(
                    heading.get_text() for heading in headings.find_all("h2")
                ),
                "is_public": True,
                "metadata": {
                    "issue_month": filename[:7],
                    "date_source": "original_source_commit",
                    "source_filename": filename,
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
            if existing.preview_headings.strip():
                data.pop("preview_headings", None)
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


def import_monthly(dry_run=False):
    return save_records(monthly_records(), dry_run=dry_run)


def import_public_monthly_page(offset=0):
    # One issue per request keeps admin imports short and safely repeatable.
    issues = monthly_index()
    records = monthly_records(issues[offset : offset + 1])
    result = save_records(records, include_items=True)
    result["next_offset"] = offset + 1 if offset + 1 < len(issues) else None
    result["source_refs"] = [record["import_ref"] for record in records]
    return result


def import_private_monthly():
    """Fetch only the latest unpublished issue's listing and preview headings."""
    token = settings.GH_API_SIMONW_PRIVATE_MONTHLY
    if not token:
        raise ValueError("Set GH_API_SIMONW_PRIVATE_MONTHLY to enable this importer.")

    def github(path, params=None, raw=False):
        response = requests.get(
            "https://api.github.com/repos/simonw-private/monthly/" + path,
            params=params,
            headers={
                "Authorization": "Bearer " + token,
                "Accept": (
                    "application/vnd.github.raw+json"
                    if raw
                    else "application/vnd.github+json"
                ),
            },
            timeout=10,
            allow_redirects=False,
        )
        # Do not include private response contents or credentials in errors.
        check_github_rate_limit(response)
        if response.status_code != 200:
            raise ValueError(
                f"Private GitHub import failed (HTTP {response.status_code}). Check the repository token and its Contents read permission."
            )
        return response

    public_refs = {"monthly:" + filename for filename, date in monthly_index()}
    public_refs.update(
        Newsletter.objects.filter(
            kind=Newsletter.Kind.SPONSOR, is_public=True
        ).values_list("import_ref", flat=True)
    )
    entries = github("contents", {"ref": "main"}).json()
    if not isinstance(entries, list):
        raise ValueError("Expected a private repository file listing")
    filenames = sorted(
        entry["name"]
        for entry in entries
        if entry.get("type") == "file"
        and re.fullmatch(r"\d{4}-\d{2}-[a-z]+\.md", entry.get("name", ""))
        and "monthly:" + entry["name"] not in public_refs
    )
    if not filenames:
        return {"created": 0, "updated": 0, "skipped": 0, "items": []}
    filename = filenames[-1]
    existing = Newsletter.objects.filter(import_ref="monthly:" + filename).first()
    if existing:
        created = existing.created
    else:
        oldest = None
        for page in range(1, 101):
            response = github(
                "commits",
                {"sha": "main", "path": filename, "per_page": 100, "page": page},
            )
            commits = response.json()
            if not isinstance(commits, list):
                raise ValueError("Expected private issue commit history")
            if commits:
                oldest = commits[-1]
            if "next" not in response.links:
                break
        else:
            raise ValueError("Private issue commit history exceeded pagination limit")
        if oldest is None:
            raise ValueError("Missing original send date for private issue")
        created = datetime.datetime.fromisoformat(oldest["commit"]["committer"]["date"])
        if created.tzinfo is None:
            raise ValueError("Private issue send date must include a timezone")
    response = github("contents/" + filename, {"ref": "main"}, raw=True)
    # Parse headings in memory; never store the private Markdown or rendered body.
    headings = BeautifulSoup(
        markdown(response.content.decode("utf-8"), extensions=["extra"]), "html.parser"
    )
    title = headings.find("h1")
    issue_date = datetime.date.fromisoformat(filename[:7] + "-01")
    record = {
        "import_ref": "monthly:" + filename,
        "kind": Newsletter.Kind.SPONSOR,
        "title": title.get_text() if title else f"LLM digest: {issue_date:%B %Y}",
        "slug": "monthly-" + filename[:-3],
        "created": created,
        "url": f"{PRIVATE_MONTHLY_REPOSITORY}/blob/main/{filename}",
        "is_public": False,
        "metadata": {
            "issue_month": filename[:7],
            "date_source": "original_source_commit",
            "source_filename": filename,
            "title_source": "heading" if title else "issue_month",
        },
    }
    if not existing or not existing.preview_headings.strip():
        record["preview_headings"] = "\n".join(
            heading.get_text() for heading in headings.find_all("h2")
        )
    return save_records([record], include_items=True)
