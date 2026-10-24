# Summary report — market awareness script (v3)

**Branch:** `claude/v3-market-awareness-script-8370my`
**Date:** 2026-09-20
**Data snapshot analysed:** 2026-08-27 (35,552 canonical repositories, 93,444 plugins)

## What was built

A market awareness report that turns the committed catalog snapshot into a briefing on ecosystem
growth, attention concentration, segment supply and demand, marketplace depth and movement over
time. It reads only `ui/src/data/repos.json` and `ui/src/data/stats.json`, so it is reproducible
offline and spends no GitHub API quota.

| File | Role |
| --- | --- |
| `ui/src/lib/marketAwareness.ts` | Analysis core: segment taxonomy, growth, concentration, depth, momentum |
| `ui/src/lib/marketAwarenessReport.ts` | Markdown renderer |
| `ui/src/lib/marketAwareness.test.ts` | 18 unit tests over the analysis |
| `ui/src/lib/marketAwarenessReport.test.ts` | 7 unit tests over the rendered output |
| `ui/scripts/marketAwareness.mts` | CLI entry point |
| `docs/market-awareness.md` | Usage and how to read the numbers |
| `artifacts/market-awareness-2026-08-27.{md,json}` | Generated report for the current snapshot |

The analysis lives in `src/lib` rather than inside the script so the existing CI gate already covers
it — `npm run typecheck`, `npm run lint` and `npm run test:unit` all reach it with no workflow
change. The CLI is a thin wrapper that validates its inputs against the repository's existing zod
schemas.

Run it with `npm run market-awareness` from `ui/`; `--baseline <git-rev>` adds the momentum section
by diffing against an earlier revision of `repos.json` from git history.

## What the current snapshot says

- **Intake is steady at roughly 185 repositories a day.** The catalog grew 86.9% over the trailing
  90 days and doubles in about 100 days at that compound rate; the last 30 days tracked within 10%
  of the 30 before them, so this is sustained growth rather than a spike.
- **Attention is almost maximally concentrated.** Gini 0.988, with the top 1% of repositories
  holding 90.1% of all stars and 49.6% of the catalog sitting at zero. Median discovery is
  effectively nil without distribution.
- **Three quarters of the catalog is purpose-built** for the agent ecosystem (75.5% of repositories,
  69.7% of stars). Another 18.2% are general projects that happen to ship a manifest.
- **Skill and prompt libraries are the crowded trade**: 25.2% of all repositories but a 0.9x demand
  index — more supply than the attention it converts.
- **The room is in narrower, execution-heavy segments.** Slides and presentations (2.35x demand on
  0.24x supply), SEO and marketing (1.83x on 0.46x), security and compliance (1.75x on 0.64x) and
  design and UI (1.53x on 0.54x) all convert to traction well above the catalog rate on
  below-baseline supply.
- **Depth is thin.** 79.8% of repositories ship exactly one plugin; only 183 repositories (0.5%)
  are mega-marketplaces of 50+, yet those hold 22,901 plugins — about a quarter of the total.
- **Movement since the 2026-07-30 snapshot:** +7,387 net repositories (7,857 entrants, 470
  drop-outs), +956,282 stars and +19,132 plugins.

## Verification

| Check | Result |
| --- | --- |
| `npm run typecheck` | Pass |
| `npm run lint` | Pass — 1 pre-existing warning in `src/app/about/page.tsx`, untouched by this change |
| `npm run test:unit` | Pass — 55 tests across 11 files, 25 of them new |
| Script against live data | Pass — full report in ~1.6s including schema validation |
| Script with `--baseline` | Pass — verified against real revisions from git history |

## Caveats

Segments are inferred by keyword matching over repository names and descriptions, so they are
directional rather than a census. About a quarter of the catalog carries no description and can only
be matched on its name; the report's data health section separates that from the genuine taxonomy
gap (18.5% of described repositories went unplaced). Star counts are taken as recorded by the
collection pipeline — the script makes no attempt to detect inflated counts.
