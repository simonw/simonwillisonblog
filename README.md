# simonwillisonblog

[![GitHub Actions](https://github.com/simonw/simonwillisonblog/actions/workflows/ci.yml/badge.svg)](https://github.com/simonw/simonwillisonblog/actions)

The code that runs my weblog, https://simonwillison.net/

## Search Engine

This blog includes a built-in search engine. Here's how it works:

1. The search functionality is implemented in the `search` function in `blog/search.py`.
2. It uses a combination of full-text search and tag-based filtering.
3. The search index is built and updated automatically when new content is added to the blog.
4. Users can search for content using keywords, which are matched against the full text of blog entries and blogmarks.
5. The search results are ranked based on relevance and can be further filtered by tags.
6. The search interface is integrated into the blog's user interface, allowing for a seamless user experience.

For more details on the implementation, refer to the `search` function in `blog/search.py`.

## S3 Manager

The admin tools include `/tools/s3/`, backed by `s3-web-manager-django`, for browsing and uploading files to the configured S3 bucket. `S3_WEB_MANAGER_PUBLIC_URL_BASE` is set to `https://static.simonwillison.net/` so copied and viewed object URLs use the public static host plus the path in the bucket.

## Newsletters

The separate `Newsletter` model stores Substack listing metadata and monthly sponsor newsletters with Markdown bodies. `created` is the original send date; `is_public` controls whether the content is public, while `is_draft` hides the listing itself. Only public, non-draft sponsor issues receive a search document. `/newsletters/` lists the ten most recent non-draft issues, using lazy-loaded thumbnails, followed by year links. `/newsletters/<year>/` lists every non-draft issue sent that year, newest first without pagination. Public sponsor issues link to their Markdown-rendered pages at `/newsletters/<slug>/`; Substack and sponsors-only issues link to their external URLs. Day and month archives include newsletter listings; the general year archive includes newsletter counts without listing their titles. Newsletters stay off the homepage and tag pages. Site search includes public, non-draft sponsor issues with a Newsletter type filter, body excerpts, and send-date filters. Substack, sponsors-only issues, drafts, and preview headings are excluded from search. Selecting a tag excludes newsletters; excluding a tag still permits them as untagged content. Newsletters do not appear in the bulk-tagging tool. Imported records can be inspected and edited at `/admin/blog/newsletter/`.

On `/admin/importers/`, the Substack **Import latest** button imports the RSS feed’s latest 20 issues. **Import all** walks the complete Substack archive in batches, showing cumulative results. Keep the page open until it completes. Each batch is saved independently, so an interrupted import can be rerun safely. Both buttons fetch fresh source data and preserve existing draft status and custom slugs. No local data export is needed to import Substack on production.

Both Substack import methods use the same source identity and store no post body. The full archive uses Substack's public website endpoint, which is not a documented stable API.

The public monthly importer downloads `index.json` and the listed UTF-8 Markdown files from `raw.githubusercontent.com/simonw/monthly-newsletter-archive/main`, with no Git executable or local checkout required. The index contains objects with `filename` and timezone-aware ISO 8601 `sent_at` fields. The archive's `sync.sh` generates those dates from each file's original first-add commit, so the blog needs no GitHub API lookups. Missing or invalid dates abort the import without guessing. Publish the updated archive index before deploying this importer. Missing titles use `LLM digest: Month Year`, with that choice recorded in metadata. The entire batch is fetched and validated before saving. Repeated imports update existing source records without duplicating them and preserve locally edited slugs, draft status, preview headings, and unrelated metadata. The **Import public newsletters** button on `/admin/importers/` imports one issue per request and displays cumulative results; keep the page open until it finishes. It requires no GitHub token.

Private issues display a sponsorship note and preview headings, with no public content page or search document. Their bodies are not stored. When a matching filename appears in the public archive, the same record gains its public body and local permalink. A private import never changes an already-public issue back to sponsors only.

The admin's `Preview headings` field accepts one plain-text heading per line. These render as a bulleted preview beneath sponsors-only issues on the latest and year pages, above the sponsorship note. They are not part of the search document, and imports preserve this manually edited field.

The private monthly importer button on `/admin/importers/` is disabled unless `GH_API_SIMONW_PRIVATE_MONTHLY` is configured. Use a GitHub token restricted to `simonw-private/monthly` with Contents read permission. The API importer compares filenames with the public index and existing public records, then imports the latest unpublished issue's title, original commit date, private GitHub link, and second-level Markdown headings. It never stores the private body, and preserves existing non-empty preview headings. The token stays on the server and is only sent to the private repository's GitHub API endpoints. GitHub rate-limit failures display a specific message with the reset time or retry delay when available. Restart the server after changing the environment variable.
