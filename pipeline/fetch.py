"""
va_pulse/fetch.py

Fetches latest items from all active sources in sources.json.
Stores rolling 30-day window in data/items.json.
Deduplicates by URL.

Usage:
    python fetch.py

Designed to run daily via Windows Task Scheduler.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import feedparser
except ImportError:
    print("ERROR: pip install feedparser", file=sys.stderr)
    sys.exit(1)

# sources.json sits next to this script (versioned in git).
# Runtime data lives outside the repo at C:\DPVAnews\data\ — override with DPVA_DATA_DIR.
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = Path(os.environ.get("DPVA_DATA_DIR", str(PROJECT_ROOT / "data")))
SOURCES_FILE = SCRIPT_DIR / "sources.json"
ITEMS_FILE = DATA_DIR / "items.json"
LOG_FILE = DATA_DIR / "fetch.log"

RETENTION_DAYS = 30
ITEMS_PER_SOURCE_PER_FETCH = 15  # Don't pull more than this per source per run
USER_AGENT = "VAPulse/1.0 (DPVA aggregator)"


def log(msg):
    """Append timestamped log line."""
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} | {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_sources():
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_existing_items():
    if not ITEMS_FILE.exists():
        return []
    with open(ITEMS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_items(items):
    ITEMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)


def parse_entry_date(entry):
    """Pull a usable datetime out of a feedparser entry; return UTC datetime."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(field)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return datetime.now(timezone.utc)


def clean_summary(text, max_chars=600):
    """Strip HTML, collapse whitespace, truncate."""
    if not text:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return text


def fetch_source(source):
    """Pull latest items from one source. Returns list of dicts."""
    if not source.get("feed_url"):
        log(f"  SKIP {source['id']}: no feed_url (scraping not yet implemented)")
        return []

    try:
        parsed = feedparser.parse(source["feed_url"], agent=USER_AGENT)
    except Exception as e:
        log(f"  ERROR {source['id']}: {e}")
        return []

    if parsed.bozo and not parsed.entries:
        log(f"  ERROR {source['id']}: feed unparseable ({parsed.bozo_exception})")
        return []

    items = []
    for entry in parsed.entries[:ITEMS_PER_SOURCE_PER_FETCH]:
        url = entry.get("link", "").strip()
        if not url:
            continue
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        summary = clean_summary(entry.get("summary") or entry.get("description") or "")
        pub_dt = parse_entry_date(entry)

        items.append({
            "url": url,
            "title": title,
            "summary": summary,
            "published": pub_dt.isoformat(),
            "source_id": source["id"],
            "source_name": source["name"],
            "community": source["community"],
            "geo": source["geo"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        })

    log(f"  OK   {source['id']}: {len(items)} items")
    return items


def main():
    log("=" * 60)
    log("FETCH RUN START")

    config = load_sources()
    existing = load_existing_items()
    existing_urls = {item["url"] for item in existing}
    log(f"Existing items in store: {len(existing)}")

    active_sources = [s for s in config["sources"] if s.get("active", True)]
    log(f"Active sources to fetch: {len(active_sources)}")

    new_items = []
    for source in active_sources:
        for item in fetch_source(source):
            if item["url"] not in existing_urls:
                new_items.append(item)
                existing_urls.add(item["url"])

    log(f"New items this run: {len(new_items)}")

    combined = existing + new_items
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    pruned = []
    for item in combined:
        try:
            pub_dt = datetime.fromisoformat(item["published"])
        except (ValueError, TypeError):
            pub_dt = datetime.now(timezone.utc)
        if pub_dt >= cutoff:
            pruned.append(item)

    pruned.sort(key=lambda x: x["published"], reverse=True)
    log(f"After 30-day retention: {len(pruned)} items")

    save_items(pruned)
    log(f"Wrote {ITEMS_FILE}")
    log("FETCH RUN END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
