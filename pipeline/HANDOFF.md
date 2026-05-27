# DPVA News Aggregator — Project Handoff

## Project location
`C:\DPVAnews\` on Brenner's Windows machine.

## What this project is

A daily-refreshed, Drudge-style news aggregator for Virginia political media,
segmented by community of thought. It serves the Democratic Party of Virginia's
data team as situational awareness for the 2026 cycle.

The conceptual basis: the Campaigns & Elections article "The New Swing Voters
Aren't Just Demographics. They're Fans" argues that campaigns need to understand
the information environment of distinct communities, not just demographic
segments. This tool operationalizes that idea by pulling feeds from a curated
inventory of VA-relevant creators/journalists/orgs and surfacing what each
community is collectively focused on.

It is NOT a personalized news reader. It is a wide-aperture scanner.

## Three things it does

1. **Live link feed (Drudge-style)** — daily fetch of headlines from RSS feeds
   of curated VA sources. Rendered as a static HTML page on GitHub Pages.
   Columns grouped by community: VA Dem-aligned, VA nonpartisan press, Black VA
   media, Latino/AAPI VA media, LGBTQ VA media, national-VA-focused.

2. **Theme detection (LLM)** — once daily, the last 24-36 hours of headlines +
   first paragraphs are sent to the Anthropic API. Claude returns structured
   JSON with: per-community themes, cross-community themes, and
   community-specific themes (the most strategically valuable — what each
   community is uniquely focused on).

3. **Community segmentation** — the theme output is rendered as a panel at the
   top of the page so the user can scan "what's hot where" before drilling
   into headlines.

## Architecture

Two-process design:

- **Daily job** (Python, run via Windows Task Scheduler):
  `fetch.py` → `analyze.py` → `render.py` → `git push` to the GitHub Pages repo
- **What users see**: static HTML page on GitHub Pages, refreshed daily

Storage: JSON files in `C:\DPVAnews\data\`, no DB.
Source registry: JSON file `C:\DPVAnews\sources.json` (easy to edit, no code
change to add a source).

This pattern matches Brenner's existing deployments
(absentee.vadems.org, enr.vadems.org, vantage.vadems.org).

## Target folder structure

```
C:\DPVAnews\
├── sources.json              # Source registry — DONE
├── fetch.py                  # RSS fetcher — DONE
├── analyze.py                # LLM theme extraction — DONE
├── render.py                 # HTML generator — TODO
├── run_daily.bat             # Task Scheduler entry point — TODO
├── README.md                 # Setup/operation notes — TODO
├── requirements.txt          # Python deps — TODO
├── data/
│   ├── items.json            # Rolling 30-day item store (auto-generated)
│   ├── themes.json           # Latest LLM theme analysis (auto-generated)
│   ├── fetch.log             # Append-only fetch log
│   └── analyze.log           # Append-only analyze log
├── output/
│   └── index.html            # The rendered page (gets pushed to GitHub Pages)
└── templates/                # If we extract HTML/CSS to templates (optional)
```

## What's already built (drop these in `C:\DPVAnews\`)

### `sources.json` — DONE

22 sources across 7 community buckets, each tagged with:
`id, name, feed_url, site_url, community, geo, type, active`

Communities defined:
- `va_dem_aligned` — Blue Virginia, Friday Power Lunch, Sam Shirazi, VA Dogwood
- `va_nonpartisan_press` — Brandon Jarvis, Cardinal News, VA Mercury, VPM,
  WHRO, Radio IQ, Augusta Free Press, Loudoun Times-Mirror, Drew Landry,
  Axios Richmond (no RSS — scrape later)
- `black_va_media` — Black Virginia News, Richmond Free Press
- `latino_aapi_va_media` — South Asian Herald, El Tiempo Latino (no RSS)
- `lgbtq_va_media` — Washington Blade (VA section)
- `national_va_focused` — Sabato's Crystal Ball
- `opposition_aware` — John Reid / WRVA (inactive by default; flip to track)

This source list comes directly from the v4 creator inventory work
(`va_creator_inventory_v4.xlsx`). Adding sources later = one JSON entry.

### `fetch.py` — DONE

- Reads `sources.json`, fetches RSS for all `active: true` sources
- Pulls latest 15 items per source per run
- Dedupes by URL against existing store
- Maintains rolling 30-day window in `data/items.json`
- Each item stored with: `url, title, summary, published, source_id,
  source_name, community, geo, fetched_at`
- Uses `feedparser` for RSS, strips HTML from summaries, truncates to 600 chars
- Logs to `data/fetch.log`
- Reads `DPVA_NEWS_ROOT` env var if set; otherwise defaults to `C:\DPVAnews`

### `analyze.py` — DONE

- Loads `data/items.json`, filters to last 36 hours
- Groups items by community
- Sends compact prompt to Anthropic API (Claude Opus 4.7) with all
  recent items grouped by community
- Receives JSON with three sections:
  - `by_community`: per-community theme lists
  - `cross_community`: themes appearing across multiple communities
  - `community_specific`: themes concentrated in one community
    (the strategically most valuable output)
- Writes to `data/themes.json`
- Requires `ANTHROPIC_API_KEY` env var
- Cost: ~1-2 cents per run

Note: the API model string is currently `claude-opus-4-7`. The script also
notes Sonnet as a cheaper alternative. Either works; verify the latest model
string from the Anthropic docs if needed.

## What still needs to be built

### `render.py` — the HTML generator (HIGH PRIORITY)

Reads `data/items.json` and `data/themes.json`, writes `output/index.html`.

**Design requirements** (from the conversation):
- Dark-themed, matches the Vantage Election Explorer aesthetic
  (vantage.vadems.org)
- Single static HTML file, all CSS inline, no JS framework
- Drudge-style: dense, link-forward, no images, scannable
- Top section: theme panel — "Hot this week" + "Community-specific" themes
  from `themes.json`
- Below: multi-column layout grouped by community. Each column has the
  community label as header (color-coded per `sources.json` `communities`
  block), items listed newest-first
- Each item: hyperlinked title, source name (smaller), relative timestamp
  ("2h ago", "yesterday", "Mon")
- Footer: "Last refreshed: [datetime] · [N] items from [M] sources"
- Mobile responsive (single column stack at narrow widths)

**Sketch of structure**:
```python
# render.py outline
load items.json, themes.json, sources.json
group items by community (newest first within each)
for each community, take top 15-20 items
render Jinja2-style template (use f-strings or string.Template — keep
  dependencies minimal)
write output/index.html
```

Suggested: pure Python f-string templating, no Jinja, to keep
dependencies = `feedparser` + `anthropic` only.

### `run_daily.bat` — Task Scheduler entry point

```bat
@echo off
cd /d C:\DPVAnews
set ANTHROPIC_API_KEY=...   REM or pull from a more secure location
python fetch.py
python analyze.py
python render.py
cd output
git add index.html
git commit -m "Daily refresh %DATE%"
git push
```

The API key handling needs thought — see "Open questions" below.

### `requirements.txt`

```
feedparser>=6.0
anthropic>=0.40
```

### `README.md`

Operator-facing notes: how to add sources, how to flip a source on/off, how to
re-run pieces individually, where logs live, how to recover from a bad run.

### GitHub Pages repo setup

Brenner has a pattern here from existing projects. The `output/` folder
contents (or just `index.html`) gets pushed to a repo like
`brennertobe07/dpvanews` and served at `news.vadems.org` or similar.
Cloudflare Zero Trust for access control, matching the existing vadems.org
deployments.

## Open questions / decisions to make

1. **API key storage**. Plain env var in `run_daily.bat` is simplest but means
   the key is in cleartext in the script. Options:
   - Windows Credential Manager + a small Python helper to fetch it
   - Encrypted file with a local decryption step
   - Just accept the risk for a low-value key — the worst case is someone
     racks up a small API bill. Brenner can decide.

2. **Subdomain**. `news.vadems.org`? `pulse.vadems.org`?
   `signal.vadems.org`? `dpvanews.vadems.org`? Naming TBD.

3. **Access control**. Cloudflare Zero Trust like the other vadems.org
   sites, or public? This page reveals nothing internal — it's just an
   aggregator of public sources — so a case for public could be made.

4. **Sources with no RSS**. `axios_richmond`, `el_tiempo_latino`, and
   `wrva_audacy` are in `sources.json` with empty `feed_url`. Two options:
   (a) leave them out of v1 entirely; (b) add a small scraping module
   (use `requests` + `beautifulsoup4`) that pulls headline links from
   homepages. I'd defer scraping to v2 — ship working RSS first.

5. **Theme persistence/history**. `analyze.py` currently overwrites
   `themes.json` every run. Worth keeping a history (`themes/2026-05-26.json`)
   so we can spot trends over weeks. Easy add — discuss with Brenner.

6. **Failure modes**. What happens when a feed is down? When the LLM call
   fails? When git push fails? Currently logs and exits non-zero, but the
   page keeps showing stale data. Add a "last successful refresh" banner.

## Existing assets in this conversation that informed the build

- `va_creator_inventory_v4.xlsx` — full inventory of 63 VA-relevant
  creators across 6 community tabs + 2 sourcing-plan tabs. The `sources.json`
  draws from the entries with RSS feeds and reasonable institutional weight.

- The 2026 article (Campaigns & Elections, May 2026) by Kory Vargas Caro,
  "The New Swing Voters Aren't Just Demographics. They're Fans" — conceptual
  basis. Key argument: campaigns need to understand the information
  environment of distinct communities, not just demographic targeting.

## Suggested order of work for the next session

1. Confirm the three completed files (`sources.json`, `fetch.py`,
   `analyze.py`) work in `C:\DPVAnews` — install deps, run `fetch.py`, look
   at `data/items.json`, fix any feed URLs that 404 or have format issues.

2. Write `render.py`. Get the HTML to look right on a static file first
   before automating anything. Iterate on the design until the dark-themed
   Drudge-feel is right.

3. Wire up `run_daily.bat` and test end-to-end (fetch → analyze → render).

4. Set up the GitHub Pages repo and `news.vadems.org` (or chosen name)
   subdomain.

5. Add Task Scheduler entry for 6 AM ET daily.

6. Watch it run for a week, fix the inevitable feed quirks, then decide on
   v2 additions (scraping for non-RSS sources, theme history, etc.).

## What to tell Claude Code on first prompt

"I'm building a daily-refreshed VA political news aggregator at
`C:\DPVAnews`. The project handoff document is at
`C:\DPVAnews\HANDOFF.md` — read it first. `sources.json`, `fetch.py`, and
`analyze.py` are already in place. The next task is `render.py` — see the
'What still needs to be built' section of the handoff."
