# VA Pulse

A 2-hour-refreshed scanner of the Virginia political information environment,
built for DPVA's data team as situational awareness for the 2026 cycle.

**Live site:** https://brennertobe07.github.io/dpvanews/

## What it does

Pulls RSS from ~20 curated VA-relevant sources, segments items by community
of thought (VA Dem-aligned, nonpartisan press, Black VA media, Latino/AAPI
VA media, LGBTQ VA media, national VA-focused), and uses Claude Opus to
surface what each community is collectively focused on.

It is NOT a personalized news reader. It is a wide-aperture scanner.

## How it works

1. **fetch** — RSS pull from active sources, dedupe by URL, 30-day rolling store.
2. **analyze** — Claude Opus 4.7 extracts per-community + cross-community themes.
3. **render** — single static HTML page, no JS framework.
4. **push** — committed and pushed to this repo, served via GitHub Pages.

Runs every 2 hours via Windows Task Scheduler on Brenner's machine.

## Layout

- `index.html`, `assets/` — what GitHub Pages serves
- `pipeline/` — versioned Python source for fetch / analyze / render

The full operator guide (how to add a source, recover from a bad run, where
state lives, etc.) is in [`pipeline/HANDOFF.md`](pipeline/HANDOFF.md).

## Source registry

[`pipeline/sources.json`](pipeline/sources.json) is the single source of
truth — edit there to add, remove, or deactivate a source.
