"""
va_pulse/render.py

Reads data/items.json, data/themes.json, and sources.json.
Writes a single static HTML page to output/index.html.

Design: serif body for gravitas, sans-serif display type for punch.
Coverage Pulse bar, hero theme treatment, color-banded community columns.

Usage:
    python render.py
"""
import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SITE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = SITE_DIR.parent
DATA_DIR = Path(os.environ.get("DPVA_DATA_DIR", str(PROJECT_ROOT / "data")))
SOURCES_FILE = SCRIPT_DIR / "sources.json"
ITEMS_FILE = DATA_DIR / "items.json"
THEMES_FILE = DATA_DIR / "themes.json"
OUTPUT_FILE = SITE_DIR / "index.html"

ITEMS_PER_COLUMN = 25
PULSE_WINDOW_HOURS = 24
FRESH_HOURS = 6
MAX_SUPPORT_ITEMS = 3
SUMMARY_MAX_CHARS = 100
SITE_TITLE = "VA Pulse"
SITE_TAGLINE = "DAILY SCAN OF VIRGINIA'S POLITICAL INFORMATION ENVIRONMENT"
LOGO_PATH = "assets/vadems_logo.jpg"


def load_json(path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def relative_time(pub_dt, now):
    if pub_dt is None:
        return ""
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    delta = now - pub_dt
    seconds = delta.total_seconds()
    if seconds < 0:
        return "just now"
    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{int(minutes)}m"
    if hours < 24:
        return f"{int(hours)}h"
    if days < 2:
        return "yesterday"
    if days < 7:
        return pub_dt.strftime("%a")
    return pub_dt.strftime("%b %#d") if os.name == "nt" else pub_dt.strftime("%b %-d")


def hours_ago(pub_dt, now):
    if pub_dt is None:
        return None
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)
    return (now - pub_dt).total_seconds() / 3600


def truncate(text, max_chars):
    if not text or len(text) <= max_chars:
        return text or ""
    cut = text[: max_chars - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:—-") + "…"


def group_items_by_community(items, communities_order):
    groups = {cid: [] for cid in communities_order}
    for item in items:
        cid = item.get("community")
        if cid in groups:
            groups[cid].append(item)
    for cid in groups:
        groups[cid].sort(key=lambda x: x.get("published", ""), reverse=True)
    return groups


def count_recent_by_community(items, now, hours):
    counts = {}
    for item in items:
        pub = parse_iso(item.get("published"))
        if pub is None:
            continue
        if hours_ago(pub, now) <= hours:
            counts[item["community"]] = counts.get(item["community"], 0) + 1
    return counts


def render_coverage_pulse(counts_24h, communities, communities_order):
    """Stacked horizontal bar showing per-community 24h volume."""
    total = sum(counts_24h.values())
    if total == 0:
        return ""

    segments = []
    legend = []
    for cid in communities_order:
        n = counts_24h.get(cid, 0)
        if n == 0:
            continue
        comm = communities.get(cid, {})
        label = html.escape(comm.get("label", cid))
        color = comm.get("color", "#888")
        pct = (n / total) * 100
        segments.append(
            f'<div class="pulse-seg" style="flex-grow:{n};background:{color}" '
            f'title="{label}: {n} stories">'
            f'<span class="pulse-seg-n">{n}</span>'
            f'</div>'
        )
        legend.append(
            f'<span class="pulse-legend-item">'
            f'<span class="pulse-dot" style="background:{color}"></span>'
            f'{label} <b>{n}</b>'
            f'</span>'
        )

    return f"""
<section class="pulse">
  <div class="pulse-label">Coverage Pulse <span class="pulse-sub">last {PULSE_WINDOW_HOURS}h &middot; {total} stories</span></div>
  <div class="pulse-bar">{"".join(segments)}</div>
  <div class="pulse-legend">{"".join(legend)}</div>
</section>
"""


def pick_hero_theme(themes):
    """Return (theme_dict, kind) where kind is 'cross' or 'specific' or None."""
    if not themes:
        return None, None
    cross = themes.get("cross_community") or []
    if cross:
        hero = max(cross, key=lambda t: len(t.get("communities") or []))
        return hero, "cross"
    specific = themes.get("community_specific") or []
    if specific:
        return specific[0], "specific"
    return None, None


def render_supporting_items(items, communities, now, css_class="supports", max_items=MAX_SUPPORT_ITEMS):
    if not items:
        return ""
    lines = []
    for it in items[:max_items]:
        url = html.escape(it.get("url", ""), quote=True)
        title = html.escape(it.get("title", ""))
        source = html.escape(it.get("source_name", ""))
        cid = it.get("community", "")
        color = communities.get(cid, {}).get("color", "#888")
        pub_dt = parse_iso(it.get("published"))
        rel = html.escape(relative_time(pub_dt, now))
        lines.append(
            f'<li class="support-item">'
            f'<span class="support-dot" style="background:{color}" title="{source}"></span>'
            f'<a class="support-link" href="{url}" target="_blank" rel="noopener">{title}</a>'
            f'<span class="support-meta">{rel}</span>'
            f'</li>'
        )
    return f'<ul class="{css_class}">{"".join(lines)}</ul>'


def render_hero_theme(hero, kind, communities, now):
    if not hero:
        return ""
    theme_name = html.escape(hero.get("theme", ""))
    summary = html.escape(hero.get("summary", ""))

    if kind == "cross":
        comm_ids = hero.get("communities") or []
        dots = "".join(
            f'<span class="dot" style="background:{communities.get(cid, {}).get("color", "#888")}" '
            f'title="{html.escape(communities.get(cid, {}).get("label", cid))}"></span>'
            for cid in comm_ids
        )
        tag = f"DOMINANT STORY &middot; {len(comm_ids)} COMMUNITIES"
    else:
        cid = hero.get("community", "")
        comm = communities.get(cid, {})
        dots = (
            f'<span class="dot" style="background:{comm.get("color", "#888")}"></span>'
        )
        tag = f"COMMUNITY-SPECIFIC &middot; {html.escape(comm.get('label', cid)).upper()}"

    supports = render_supporting_items(
        hero.get("supporting_items") or [], communities, now, css_class="supports supports--hero"
    )

    return f"""
<section class="hero">
  <div class="hero-tag"><span class="hero-tag-text">{tag}</span><span class="hero-dots">{dots}</span></div>
  <h2 class="hero-headline">{theme_name}</h2>
  <p class="hero-deck">{summary}</p>
  {supports}
</section>
"""


def render_other_themes(themes, hero, communities, now):
    if not themes:
        return ""
    cross = list(themes.get("cross_community") or [])
    specific = list(themes.get("community_specific") or [])

    if hero in cross:
        cross.remove(hero)
    elif hero in specific:
        specific.remove(hero)

    if not cross and not specific:
        return ""

    cards = []
    for t in cross:
        theme_name = html.escape(t.get("theme", ""))
        summary = html.escape(truncate(t.get("summary", ""), SUMMARY_MAX_CHARS))
        comm_ids = t.get("communities") or []
        dots = "".join(
            f'<span class="dot" style="background:{communities.get(cid, {}).get("color", "#888")}" '
            f'title="{html.escape(communities.get(cid, {}).get("label", cid))}"></span>'
            for cid in comm_ids
        )
        supports = render_supporting_items(
            t.get("supporting_items") or [], communities, now
        )
        cards.append(
            f'<div class="theme-card theme-card--cross">'
            f'<div class="theme-card-tag">'
            f'<span class="theme-card-tag-text">CROSS &middot; {len(comm_ids)}</span>'
            f'<span class="theme-card-dots">{dots}</span>'
            f'</div>'
            f'<div class="theme-card-name">{theme_name}</div>'
            f'<div class="theme-card-summary">{summary}</div>'
            f'{supports}'
            f'</div>'
        )

    for t in specific:
        theme_name = html.escape(t.get("theme", ""))
        summary = html.escape(truncate(t.get("summary", ""), SUMMARY_MAX_CHARS))
        cid = t.get("community", "")
        comm = communities.get(cid, {})
        comm_label = html.escape(comm.get("label", cid))
        color = comm.get("color", "#888")
        supports = render_supporting_items(
            t.get("supporting_items") or [], communities, now
        )
        cards.append(
            f'<div class="theme-card theme-card--specific" style="--c:{color}">'
            f'<div class="theme-card-tag" style="color:{color}">{comm_label.upper()} ONLY</div>'
            f'<div class="theme-card-name">{theme_name}</div>'
            f'<div class="theme-card-summary">{summary}</div>'
            f'{supports}'
            f'</div>'
        )

    return f'<section class="themes-grid">{"".join(cards)}</section>'


def render_item(item, now, is_lead=False):
    url = html.escape(item.get("url", ""), quote=True)
    title = html.escape(item.get("title", ""))
    source = html.escape(item.get("source_name", ""))
    pub_dt = parse_iso(item.get("published"))
    rel = html.escape(relative_time(pub_dt, now))
    hrs = hours_ago(pub_dt, now)
    fresh = hrs is not None and hrs <= FRESH_HOURS

    classes = ["item"]
    if is_lead:
        classes.append("item--lead")
    if fresh:
        classes.append("item--fresh")

    fresh_dot = '<span class="fresh-dot">&bull;</span> ' if fresh else ""

    return (
        f'<li class="{" ".join(classes)}">'
        f'{fresh_dot}'
        f'<a class="item-title" href="{url}" target="_blank" rel="noopener">{title}</a>'
        f'<div class="item-meta">'
        f'<span class="item-source">{source}</span>'
        f'<span class="item-time">{rel}</span>'
        f'</div>'
        f'</li>'
    )


def render_columns(groups, communities, counts_24h, now):
    cols = []
    for cid, items in groups.items():
        if not items:
            continue
        comm = communities.get(cid, {})
        label = html.escape(comm.get("label", cid))
        color = comm.get("color", "#888")
        n_24h = counts_24h.get(cid, 0)
        n_total = len(items)
        rendered = "\n".join(
            render_item(it, now, is_lead=(i == 0))
            for i, it in enumerate(items[:ITEMS_PER_COLUMN])
        )
        cols.append(
            f'<section class="column" style="--c:{color}">'
            f'<div class="column-band"></div>'
            f'<header class="column-header">'
            f'<h2 class="column-title">{label}</h2>'
            f'<div class="column-counts">'
            f'<span class="column-24h"><b>{n_24h}</b> today</span>'
            f'<span class="column-total">{n_total} in store</span>'
            f'</div>'
            f'</header>'
            f'<ul class="item-list">{rendered}</ul>'
            f'</section>'
        )
    return "\n".join(cols)


CSS = """
* { box-sizing: border-box; }
html, body {
  margin: 0;
  padding: 0;
  background: #fafaf7;
  color: #111;
  font-family: "Times New Roman", Times, Georgia, serif;
  font-size: 15px;
  line-height: 1.35;
  -webkit-font-smoothing: antialiased;
}
a { color: #0a2540; text-decoration: none; }
a:visited { color: #4a1d6e; }
a:hover { color: #cc0000; text-decoration: underline; }

.sans {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
}

.wrap {
  max-width: 1600px;
  margin: 0 auto;
  padding: 18px 24px 56px;
}

/* MASTHEAD */
header.masthead {
  text-align: center;
  padding-bottom: 10px;
  border-bottom: 3px double #111;
  margin-bottom: 18px;
}
.masthead .logo {
  height: 52px;
  width: auto;
  margin-bottom: 4px;
}
.masthead h1 {
  margin: 0;
  font-family: "Times New Roman", Times, serif;
  font-weight: 900;
  font-size: 56px;
  letter-spacing: -0.02em;
  line-height: 1;
}
.masthead .tagline {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10px;
  letter-spacing: 0.22em;
  color: #666;
  margin: 6px 0 4px;
  font-weight: 700;
}
.masthead .date {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 11px;
  letter-spacing: 0.15em;
  color: #333;
  font-weight: 600;
}

/* COVERAGE PULSE */
.pulse {
  margin-bottom: 24px;
  padding: 10px 14px;
  background: #fff;
  border: 1px solid #e5e5e5;
}
.pulse-label {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-weight: 800;
  color: #111;
  margin-bottom: 6px;
}
.pulse-sub {
  font-weight: 500;
  color: #888;
  letter-spacing: 0.08em;
  margin-left: 6px;
}
.pulse-bar {
  display: flex;
  width: 100%;
  height: 18px;
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 8px;
}
.pulse-seg {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  color: #fff;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  transition: filter 0.15s;
}
.pulse-seg:hover { filter: brightness(0.9); }
.pulse-seg-n { text-shadow: 0 0 2px rgba(0,0,0,0.3); }
.pulse-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 11px;
  color: #444;
}
.pulse-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.pulse-legend-item b { color: #111; }
.pulse-dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

/* HERO THEME */
.hero {
  margin-bottom: 24px;
  padding: 20px 24px 18px;
  background: #fff;
  border-left: 5px solid #b91c1c;
  border-top: 1px solid #e5e5e5;
  border-right: 1px solid #e5e5e5;
  border-bottom: 1px solid #e5e5e5;
}
.hero-tag {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.hero-tag-text {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.22em;
  color: #b91c1c;
  text-transform: uppercase;
}
.hero-headline {
  margin: 0 0 8px;
  font-family: "Times New Roman", Times, serif;
  font-weight: 900;
  font-size: 34px;
  line-height: 1.08;
  letter-spacing: -0.018em;
  color: #111;
}
.hero-deck {
  margin: 0;
  font-size: 16px;
  line-height: 1.45;
  color: #444;
  font-style: italic;
}
.hero-dots { display: inline-flex; gap: 4px; }
.dot {
  display: inline-block;
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

/* SUPPORTING ITEMS (under hero + theme cards) */
.supports {
  list-style: none;
  margin: 8px 0 0;
  padding: 8px 0 0;
  border-top: 1px solid #eee;
}
.supports--hero {
  margin-top: 14px;
  padding-top: 12px;
}
.support-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 0;
  font-size: 11px;
  line-height: 1.3;
}
.supports--hero .support-item {
  font-size: 14px;
  padding: 3px 0;
}
.support-dot {
  flex-shrink: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  display: inline-block;
  align-self: center;
}
.support-link {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-weight: 600;
  color: #0a2540;
  flex: 1;
  min-width: 0;
}
.supports--hero .support-link {
  font-family: "Times New Roman", Times, Georgia, serif;
  font-weight: 700;
  letter-spacing: 0;
}
.support-meta {
  flex-shrink: 0;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10px;
  color: #aaa;
  font-variant-numeric: tabular-nums;
}

/* THEME CARDS GRID */
.themes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}
.theme-card {
  background: #fff;
  border: 1px solid #e5e5e5;
  padding: 12px 14px;
  position: relative;
}
.theme-card--specific {
  border-left: 4px solid var(--c, #888);
}
.theme-card-tag {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #888;
  margin-bottom: 5px;
  min-height: 12px;
}
.theme-card-tag-text { color: #b91c1c; }
.theme-card-dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.theme-card-dots .dot { width: 8px; height: 8px; }
.theme-card-name {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-weight: 800;
  font-size: 14px;
  line-height: 1.25;
  letter-spacing: -0.003em;
  margin-bottom: 3px;
  color: #111;
}
.theme-card-summary {
  font-family: "Times New Roman", Times, Georgia, serif;
  font-style: italic;
  font-size: 12px;
  color: #666;
  line-height: 1.4;
}

/* COMMUNITY COLUMNS */
.columns {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
  gap: 18px;
  align-items: start;
}
.column {
  background: #fff;
  border: 1px solid #e5e5e5;
  min-width: 0;
  position: relative;
  overflow: hidden;
}
.column-band {
  height: 5px;
  background: var(--c, #888);
}
.column-header {
  padding: 10px 14px 8px;
  border-bottom: 2px solid #111;
}
.column-title {
  margin: 0 0 4px;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #111;
}
.column-counts {
  display: flex;
  justify-content: space-between;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 10px;
  color: #777;
  letter-spacing: 0.04em;
}
.column-24h b {
  color: var(--c, #111);
  font-size: 12px;
  margin-right: 2px;
}
.item-list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.item {
  padding: 7px 12px;
  border-bottom: 1px dotted #e0e0e0;
  font-size: 13px;
  line-height: 1.3;
}
.item:last-child { border-bottom: none; }
.item--lead {
  padding-top: 10px;
  padding-bottom: 10px;
}
.item--lead .item-title {
  font-size: 13px;
  font-weight: 800;
  line-height: 1.22;
}
.item-title {
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-weight: 700;
  letter-spacing: -0.003em;
  word-wrap: break-word;
}
.item-meta {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  margin-top: 2px;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 9px;
  color: #999;
  letter-spacing: 0.03em;
}
.item-source {
  color: #777;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.item-time {
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}
.fresh-dot {
  color: #cc0000;
  font-weight: 900;
  font-size: 18px;
  line-height: 0;
  vertical-align: middle;
  margin-right: 1px;
}

footer.foot {
  margin-top: 40px;
  padding-top: 14px;
  border-top: 3px double #111;
  font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
  font-size: 11px;
  color: #666;
  text-align: center;
  letter-spacing: 0.06em;
}
footer.foot div + div { margin-top: 4px; }

.empty {
  padding: 32px;
  text-align: center;
  color: #666;
  font-style: italic;
  border: 1px dashed #ccc;
  background: #fff;
}

@media (max-width: 700px) {
  .wrap { padding: 14px 14px 40px; }
  .masthead h1 { font-size: 36px; }
  .hero-headline { font-size: 24px; }
  .columns { gap: 14px; }
}
"""


def render_html(items, themes, sources_config, now):
    communities = sources_config.get("communities", {})
    communities_order = list(communities.keys())

    active_sources = [s for s in sources_config.get("sources", []) if s.get("active", True)]
    n_sources_active = len(active_sources)

    counts_24h = count_recent_by_community(items, now, PULSE_WINDOW_HOURS)

    groups = group_items_by_community(items, communities_order)
    n_items_shown = sum(min(len(g), ITEMS_PER_COLUMN) for g in groups.values())

    pulse = render_coverage_pulse(counts_24h, communities, communities_order)
    hero_theme, hero_kind = pick_hero_theme(themes)
    hero_html = render_hero_theme(hero_theme, hero_kind, communities, now)
    other_themes = render_other_themes(themes, hero_theme, communities, now)
    columns_html = render_columns(groups, communities, counts_24h, now)
    if not columns_html:
        columns_html = '<div class="empty">No items yet. Run <code>fetch.py</code> to populate.</div>'

    local_now = now.astimezone()
    refreshed = local_now.strftime("%b %d, %Y at %I:%M %p %Z").strip()
    date_header = local_now.strftime("%A, %B %d, %Y").upper()

    themes_note = ""
    if themes and themes.get("generated_at"):
        gen = parse_iso(themes["generated_at"])
        if gen:
            themes_note = f' &middot; themes refreshed {relative_time(gen, now)} ago'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(SITE_TITLE)} &mdash; {html.escape(date_header.title())}</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <header class="masthead">
    <img class="logo" src="{LOGO_PATH}" alt="Virginia Democrats">
    <div class="tagline">{html.escape(SITE_TAGLINE)}</div>
    <div class="date">{html.escape(date_header)}</div>
  </header>

  {pulse}

  {hero_html}

  {other_themes}

  <section class="columns">
    {columns_html}
  </section>

  <footer class="foot">
    <div>Last refreshed: {html.escape(refreshed)}{themes_note}</div>
    <div>{n_items_shown} headlines shown &middot; {len(items)} in 30-day store &middot; {n_sources_active} active sources</div>
  </footer>
</div>
</body>
</html>
"""


def main():
    items = load_json(ITEMS_FILE, [])
    themes = load_json(THEMES_FILE, {})
    sources_config = load_json(SOURCES_FILE, None)
    if sources_config is None:
        print(f"ERROR: {SOURCES_FILE} not found", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    page = render_html(items, themes, sources_config, now)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(page)

    print(f"Wrote {OUTPUT_FILE} ({len(page):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
