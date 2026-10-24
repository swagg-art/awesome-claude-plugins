# Market awareness report (v3)

`ui/scripts/marketAwareness.mts` turns the committed catalog snapshot into a briefing on where the
Claude Code plugin ecosystem is going and where the gaps are. It reads `ui/src/data/repos.json` and
`ui/src/data/stats.json` only, so it is reproducible offline and never spends GitHub API quota.

## Running it

```bash
cd ui
npm run market-awareness                                   # Markdown to stdout
npm run market-awareness -- --baseline 1e10d4e --top 15    # add movement vs an earlier snapshot
npm run market-awareness -- --format json --out ../artifacts/market-awareness.json
```

| Flag | Default | Purpose |
| --- | --- | --- |
| `--format <md\|json>` | `md` | Markdown briefing or the machine-readable report |
| `--out <path>` | stdout | Write to a file, creating parent directories |
| `--baseline <rev>` | none | Git revision of `repos.json` to measure movement against |
| `--top <n>` | `10` | Rows per leaderboard |
| `--repos <path>` / `--stats <path>` | committed data | Override the inputs |
| `--no-validate` | validation on | Skip schema validation of the inputs |

Requires a Node release that strips TypeScript by default (Node 22.18+ or the Node 24 pinned in
`.nvmrc`), because the CLI imports the typed analysis library directly.

## What it measures

- **Ecosystem growth** — 7/30/90-day intake from `stats.json`, the compound doubling time, and
  whether the last 30 days ran faster or slower than the 30 before them. Snapshots are irregular, so
  each window reports the span it actually covers rather than the span it asked for.
- **Attention concentration** — median, mean and p90 stars, top 1%/10% star share, and a Gini
  coefficient. Roughly half the catalog sits at zero stars, so the median alone says very little.
- **Build intent** — how much of the catalog is purpose-built for the agent ecosystem versus generic
  AI tooling versus a general project that happens to ship a manifest.
- **Segments** — a keyword taxonomy over repository names and descriptions, with supply (share of
  repositories, against the median classified segment) and demand (share of the segment at or above
  the catalog traction bar, against the catalog-wide rate).
- **Marketplace depth** — single plugins versus suites versus mega-marketplaces.
- **Momentum** — with `--baseline`, new entrants, drop-outs, star gainers, fastest climbers and
  per-segment intake against an earlier revision of `repos.json`.
- **Data health** — duplicates, missing descriptions, unverified plugin counts, and how much of the
  catalog the taxonomy failed to place.

## Reading the numbers honestly

- Segments come from keyword matching on names and descriptions, so they are directional, not a
  census. About a quarter of the catalog has no description at all and can only be matched on its
  name; the data health section separates that from the real taxonomy gap.
- The traction bar is the catalog's own 90th percentile, so it moves with the catalog. A demand
  index of 1.0 means a segment converts to traction at exactly the catalog-wide rate.
- Segments below 50 repositories are left `unrated` because their traction rate is too noisy to call.
- Star counts are whatever the collection pipeline recorded; the script does not attempt to detect
  or correct inflated counts.

## Extending the taxonomy

Segments live in `SEGMENT_DEFINITIONS` in `ui/src/lib/marketAwareness.ts`, ordered most specific to
most generic — a repository is filed under the definition matching the most patterns, and ties fall
to the earlier entry. Add patterns when "unclassified despite having a description" climbs in the
data health section, and keep the regexes at module top level so they are compiled once.

Generated reports are committed under `artifacts/`.
