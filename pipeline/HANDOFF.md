# VA Pulse — Operator Handoff

## What this is

**VA Pulse** is a 2-hour-refreshed news aggregator for Virginia political media,
segmented by community of thought. Built for DPVA's data team as situational
awareness for the 2026 cycle.

It is NOT a personalized news reader. It is a wide-aperture scanner of the VA
political information environment, organized by who's talking and what each
community is collectively focused on.

**Live site:** https://brennertobe07.github.io/dpvanews/
**Repo:** https://github.com/brennertobe07/dpvanews

## Where things live

```
C:\DPVAnews\
├── data\                          # Runtime state — NOT versioned
│   ├── items.json                 # Rolling 30-day item store
│   ├── themes.json                # Latest LLM theme analysis
│   ├── themes-history\            # Daily snapshots (one file per UTC day)
│   │   └── YYYY-MM-DD.json        # Last run of the day wins
│   ├── fetch.log
│   └── analyze.log
├── output\                        # GIT REPO (GitHub Pages root)
│   ├── .git\
│   ├── index.html                 # What GH Pages serves
│   ├── assets\
│   │   └── vadems_logo.jpg
│   └── pipeline\                  # Versioned pipeline source
│       ├── fetch.py
│       ├── analyze.py
│       ├── render.py
│       ├── sources.json           # Source registry — edit this to add/remove sources
│       ├── run_daily.bat          # Canonical run script
│       ├── requirements.txt
│       ├── HANDOFF.md             # This file
│       └── .gitignore
├── run_daily.bat                  # Redirector to output\pipeline\run_daily.bat
└── DPVAnews_handoff.zip           # Archive of original handoff bundle
```

Scripts resolve `sources.json` next to themselves (via `Path(__file__).parent`).
Data location is `C:\DPVAnews\data\` by default; override with `DPVA_DATA_DIR`
env var if testing elsewhere.

## How it runs

**Task Scheduler entry:** `VA Pulse Daily` — runs every 2 hours via
`C:\DPVAnews\run_daily.bat`. That stub calls into the canonical
`C:\DPVAnews\output\pipeline\run_daily.bat`, which does:

1. **fetch.py** — pull RSS for all active sources, dedupe by URL,
   maintain rolling 30-day window in `data\items.json`.
2. **analyze.py** — call Claude Opus 4.7 (`max_tokens=8000`) on a
   per-community windowed slice of items (default 36h; widen up to 7d for
   communities with fewer than 5 items). Write `data\themes.json` AND
   `data\themes-history\YYYY-MM-DD.json` (latest run of UTC day wins).
3. **render.py** — read items + themes + sources, write `output\index.html`.
4. **git push** — commit-all in `output\` and push to GitHub Pages.
   Site is live in ~60s.

**Cost:** ~$0.15–0.20 per Opus call × 12 runs/day = ~$2/day at current prompt
size. Requires `ANTHROPIC_API_KEY` env var (`setx ANTHROPIC_API_KEY ...`).

**Task Scheduler caveat:** runs only when the user is logged in. To run when
logged out, recreate the task with `/ru <user> /rp <password>`.

## Source registry

`output\pipeline\sources.json` is the single source of truth. Each entry:

```json
{
  "id": "blue_virginia",
  "name": "Blue Virginia",
  "feed_url": "https://bluevirginia.us/feed",
  "site_url": "https://bluevirginia.us",
  "community": "va_dem_aligned",
  "geo": "statewide",
  "type": "blog",
  "active": true
}
```

**Communities (6 as of 2026-05-27):**
- `va_dem_aligned` — DPVA + DNC + explicitly Dem voices (Blue Virginia,
  Shirazi, Friday Power Lunch, Dogwood)
- `va_nonpartisan_press` — independent VA reporting (Jarvis, Landry,
  Cardinal News politics, VA Mercury gov+pol, VPM, Radio IQ, Augusta FP)
- `black_va_media` — Black VA News
- `latino_aapi_va_media` — South Asian Herald (El Tiempo Latino pending scraper)
- `lgbtq_va_media` — Washington Blade VA section
- `national_va_focused` — The Hill Campaign, Roll Call Politics

A previous `opposition_aware` / `va_gop` bucket was dropped 2026-05-27. RPV
press releases (the only working VA Republican feed) publish too infrequently
(~1 item per month) to populate a daily-refresh bucket; VA Republican news is
already covered well by the nonpartisan press feeds.

**Inactive sources** stay in `sources.json` with `active: false` and a
`scrape_notes` field documenting *why* (so we don't re-add a broken feed).
Currently inactive: `richmond_free_press` (domain 404'd), `whro_weekly`
(empty feed), `sabato_crystal_ball` (CDN blocks all UAs), `loudoun_times`
(WAF rate-limits after a few requests).

**No-feed sources** (`feed_url: ""`) are placeholders for v2 scraping work:
`axios_richmond`, `el_tiempo_latino`.

## Common operations

### Add a source
1. Edit `output\pipeline\sources.json`, add an entry. If you don't know the
   community color, copy the pattern of an existing source in the same bucket.
2. Run `python fetch.py` from `output\pipeline\` to verify the feed parses.
3. Commit `pipeline\sources.json` (the next scheduled run will commit it too).

### Flip a source on or off
Set `"active": false` (or true). Note: leave inactive sources in the file with
a `scrape_notes` explaining why — they're documentation.

### Recover from a bad run
- Bad themes (LLM produced garbage): `analyze.py` re-runs each scheduled tick,
  so the next 2-hour window self-corrects. If it's urgent, manually re-run:
  `cd C:\DPVAnews\output\pipeline && python analyze.py && python render.py`.
- Bad items.json: it's append-only with 30-day retention, so a single bad
  fetch just adds a row; next fetch will pick up the next batch.
- Pipeline broken: the redirector + canonical scripts are in git. Worst case,
  `git -C output reset --hard <last good commit>` and re-run.

### Inspect theme history
Files live at `C:\DPVAnews\data\themes-history\YYYY-MM-DD.json` — UTC date,
one per day, last run of the day wins. Each file has the full `themes.json`
schema (`by_community`, `cross_community`, `community_specific`,
`generated_at`, `n_items_analyzed`).

### Change the 2-hour cadence
Edit the Task Scheduler entry. The scripts have no built-in cadence assumption.

## Still open

- **Custom subdomain on vadems.org** — name not chosen (candidates: news,
  pulse, signal, dpvanews). Needs `CNAME` file in `output/` + Cloudflare DNS
  record. Matches the deploy pattern of absentee/enr/vantage.
- **Scraping for `axios_richmond` and `el_tiempo_latino`** — deferred to v2.
  Both have no public RSS. Would use `requests` + `beautifulsoup4`.
- **VPM News is sparse** — only returns 2 items per fetch; keep or drop?
- **Theme history viewer** — snapshots are accumulating but there's no UI to
  diff or browse them. Could add a `output/timeline.html` or a "24h ago"
  panel on the main page.
- **Failure-mode banner** — if `analyze.py` fails, the page silently keeps
  showing stale themes. A "last successful refresh" footer would help.

## Conceptual basis

Built on the *Campaigns & Elections* article by Kory Vargas Caro,
"The New Swing Voters Aren't Just Demographics. They're Fans" (May 2026). The
core argument: campaigns need to understand the information environment of
distinct communities, not just demographic targeting. VA Pulse operationalizes
that by pulling feeds from a curated inventory of VA-relevant
creators/journalists/orgs and surfacing what each community is collectively
focused on.

Source list draws from the v4 creator inventory work
(`va_creator_inventory_v4.xlsx`).
