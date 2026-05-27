"""
va_pulse/analyze.py

Calls Anthropic API on the last 24h of items to extract themes:
  1. Overall themes (what's hot across all of VA media right now)
  2. Themes by community (what each segment is talking about)

Writes data/themes.json for the renderer to consume.

Usage:
    export ANTHROPIC_API_KEY=...
    python analyze.py

Cost note: ~1-2 cents per daily run at this volume.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from anthropic import Anthropic
except ImportError:
    print("ERROR: pip install anthropic", file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
DATA_DIR = Path(os.environ.get("DPVA_DATA_DIR", str(PROJECT_ROOT / "data")))
SOURCES_FILE = SCRIPT_DIR / "sources.json"
ITEMS_FILE = DATA_DIR / "items.json"
THEMES_FILE = DATA_DIR / "themes.json"
LOG_FILE = DATA_DIR / "analyze.log"

ANALYSIS_WINDOW_HOURS = 36  # Slightly more than 24h to handle morning runs
LOW_VOLUME_MIN_ITEMS = 5    # If a community has fewer than this in the default window…
LOW_VOLUME_MAX_HOURS = 7 * 24  # …widen its window up to this much (e.g. official party press = sporadic)
MAX_ITEMS_PER_COMMUNITY = 40  # Cap to keep context window manageable
MODEL = "claude-opus-4-7"  # Or claude-sonnet-4-6 for cheaper runs


def log(msg):
    timestamp = datetime.now(timezone.utc).isoformat()
    line = f"{timestamp} | {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_items():
    if not ITEMS_FILE.exists():
        return []
    with open(ITEMS_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_sources():
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _parse_dt(item):
    try:
        return datetime.fromisoformat(item["published"])
    except (ValueError, TypeError):
        return None


def group_recent_by_community(
    items,
    default_hours=ANALYSIS_WINDOW_HOURS,
    min_items=LOW_VOLUME_MIN_ITEMS,
    max_hours=LOW_VOLUME_MAX_HOURS,
):
    """Group items by community, applying a per-community window. Low-volume
    communities (fewer than min_items in default_hours) get a widened window up
    to max_hours so sporadic publishers (e.g. party press releases) still appear.
    Returns (groups, window_used_hours_per_community)."""
    now = datetime.now(timezone.utc)
    default_cutoff = now - timedelta(hours=default_hours)
    max_cutoff = now - timedelta(hours=max_hours)

    by_community = {}
    for item in items:
        pub_dt = _parse_dt(item)
        if pub_dt is None or pub_dt < max_cutoff:
            continue
        by_community.setdefault(item["community"], []).append((pub_dt, item))

    groups = {}
    windows_used = {}
    for cid, dated in by_community.items():
        in_default = [it for dt, it in dated if dt >= default_cutoff]
        if len(in_default) >= min_items:
            groups[cid] = in_default
            windows_used[cid] = default_hours
        else:
            groups[cid] = [it for _, it in dated]
            windows_used[cid] = max_hours
    return groups, windows_used


def format_items_for_prompt(items, start_index, max_items=MAX_ITEMS_PER_COMMUNITY):
    """Compact representation for the LLM. Returns (text, index_map) where
    index_map maps the global integer ID shown to the LLM back to the item dict.
    """
    items = items[:max_items]
    lines = []
    index_map = {}
    for offset, item in enumerate(items):
        n = start_index + offset
        index_map[n] = item
        title = item["title"]
        summary = item["summary"][:200] if item["summary"] else ""
        source = item["source_name"]
        lines.append(f"[{n}] [{source}] {title}")
        if summary:
            lines.append(f"     {summary}")
    return "\n".join(lines), index_map


PROMPT_TEMPLATE = """You are analyzing the Virginia political media environment for a state party data team. Below are recent headlines from {n_sources} sources over the past {hours} hours, grouped by community. Each item is prefixed with a bracketed integer ID like [42] — use those IDs to cite the specific items that support each theme.

Your job: identify themes and patterns.

For each community grouping, list 3-5 themes that show up in its coverage. Then identify "cross-community themes" — topics that appeared across multiple communities — and "community-specific themes" — topics concentrated in just one or two communities. The community-specific themes are the most valuable; they reveal what each segment of VA's information environment is uniquely focused on.

Be specific. "Politics" is not a theme; "Spanberger's first 100 days" is. "Affordability" is not a theme; "data center tax breaks driving up residential electric bills" is.

For every theme in cross_community and community_specific, include a "supporting_items" array containing 2-4 of the integer IDs from the DATA below that most directly evidence the theme. Use only IDs that actually appear in the DATA.

Output strict JSON in this exact shape:

{{
  "generated_at": "ISO datetime",
  "window_hours": {hours},
  "by_community": {{
    "community_id": {{
      "label": "human-readable label",
      "n_items": int,
      "themes": [
        {{"theme": "specific theme name", "summary": "1-2 sentence what this is about", "n_mentions": int}}
      ]
    }}
  }},
  "cross_community": [
    {{"theme": "...", "summary": "...", "communities": ["id1", "id2"], "supporting_items": [12, 17, 23]}}
  ],
  "community_specific": [
    {{"theme": "...", "summary": "...", "community": "id", "why_notable": "...", "supporting_items": [4, 9]}}
  ]
}}

DATA:

{data}

Output only the JSON, no preamble."""


def build_prompt(community_groups, community_labels, windows_used):
    sections = []
    n_sources_seen = set()
    global_index = {}
    counter = 1
    for community_id, items in community_groups.items():
        label = community_labels.get(community_id, community_id)
        win = windows_used.get(community_id, ANALYSIS_WINDOW_HOURS)
        win_note = f" — window: past {win}h" if win != ANALYSIS_WINDOW_HOURS else ""
        sections.append(f"\n### {label} (community_id={community_id}) — {len(items)} items{win_note}\n")
        formatted, idx_map = format_items_for_prompt(items, start_index=counter)
        sections.append(formatted)
        global_index.update(idx_map)
        counter += len(idx_map)
        for item in items:
            n_sources_seen.add(item["source_id"])

    prompt = PROMPT_TEMPLATE.format(
        n_sources=len(n_sources_seen),
        hours=ANALYSIS_WINDOW_HOURS,
        data="\n".join(sections),
    )
    return prompt, global_index


def resolve_supporting_items(theme, global_index):
    """Replace integer IDs in supporting_items with full item dicts."""
    raw = theme.get("supporting_items") or theme.get("supporting_item_ids") or []
    resolved = []
    seen_urls = set()
    for entry in raw:
        try:
            n = int(entry)
        except (TypeError, ValueError):
            continue
        item = global_index.get(n)
        if not item:
            continue
        if item["url"] in seen_urls:
            continue
        seen_urls.add(item["url"])
        resolved.append({
            "url": item["url"],
            "title": item["title"],
            "source_name": item["source_name"],
            "community": item["community"],
            "published": item["published"],
        })
    theme["supporting_items"] = resolved
    return theme


def main():
    log("=" * 60)
    log("ANALYZE RUN START")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log("ERROR: ANTHROPIC_API_KEY not set")
        return 1

    items = load_items()
    if not items:
        log("No items to analyze — run fetch.py first")
        return 1

    groups, windows_used = group_recent_by_community(items)
    total_recent = sum(len(v) for v in groups.values())
    log(f"Items in analysis window (per-community): {total_recent}")
    if total_recent < 5:
        log("Too few items to analyze meaningfully")
        return 1

    config = load_sources()
    community_labels = {cid: c["label"] for cid, c in config["communities"].items()}

    widened = {cid: h for cid, h in windows_used.items() if h != ANALYSIS_WINDOW_HOURS}
    log(f"Communities represented: {list(groups.keys())}")
    if widened:
        log(f"Widened windows: {widened}")

    prompt, global_index = build_prompt(groups, community_labels, windows_used)
    log(f"Prompt size: {len(prompt)} chars · {len(global_index)} items indexed")

    client = Anthropic(api_key=api_key)
    log(f"Calling {MODEL}…")
    response = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "max_tokens":
        log(f"WARNING: response hit max_tokens — JSON likely truncated")

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

    try:
        themes = json.loads(raw)
    except json.JSONDecodeError as e:
        log(f"ERROR: LLM did not return valid JSON: {e}")
        log(f"First 500 chars of response: {raw[:500]}")
        return 1

    for t in themes.get("cross_community") or []:
        resolve_supporting_items(t, global_index)
    for t in themes.get("community_specific") or []:
        resolve_supporting_items(t, global_index)

    n_resolved = sum(
        len(t.get("supporting_items") or [])
        for section in ("cross_community", "community_specific")
        for t in (themes.get(section) or [])
    )
    log(f"Resolved {n_resolved} supporting items across themes")

    themes["generated_at"] = datetime.now(timezone.utc).isoformat()
    themes["model"] = MODEL
    themes["n_items_analyzed"] = total_recent

    THEMES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(THEMES_FILE, "w", encoding="utf-8") as f:
        json.dump(themes, f, indent=2, ensure_ascii=False)
    log(f"Wrote {THEMES_FILE}")
    log("ANALYZE RUN END")
    return 0


if __name__ == "__main__":
    sys.exit(main())
