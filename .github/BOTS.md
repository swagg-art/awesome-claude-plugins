# Bot autopilot

How the automated maintenance in this repository is wired, what lands without review,
and what always waits for a human.

## What runs on its own

| Bot / job | Config | Schedule | Autopilot |
|---|---|---|---|
| Renovate — tooling & type deps | `.github/renovate.json` | Wed 14:00–15:00 (Europe/Athens) | Auto-merges on green CI |
| Renovate — runtime deps (minor/patch) | `.github/renovate.json` | Fri 16:00–17:00 | Auto-merges on green CI |
| Renovate — GitHub Actions (minor/patch/digest) | `.github/renovate.json` | Wed 14:00–15:00 | Auto-merges on green CI |
| Renovate — lock file maintenance | `.github/renovate.json` | 1st of the month, before 09:00 | Auto-merges on green CI |
| Renovate — security fixes | `vulnerabilityAlerts` | Any time, no release-age delay | Auto-merges on green CI |
| Renovate — framework (`next`, `react`, `react-dom`) | `.github/renovate.json` | Mon 10:00–11:00 | Manual review |
| Renovate — non-framework majors | `.github/renovate.json` | Tue 09:00–10:00 | Manual review |
| IndexNow sitemap submission | `.github/workflows/indexnow.yml` | Mon 04:17 UTC | Fully automated |
| CI | `.github/workflows/ci.yml` | Every push to `main` and every PR | Gate for everything above |

Updates that auto-merge carry a `minimumReleaseAge` of 3 days (7 for framework and
majors), so a freshly published release is never merged the moment it appears.

## How a bot PR gets merged

1. Renovate opens the PR in its scheduled window and adds the `automerge` label to the
   groups listed above.
2. CI runs typecheck, lint, unit tests, a production build, and the Playwright e2e suite.
3. Renovate (`platformAutomerge`) and `.github/workflows/bot-autopilot.yml` both ask
   GitHub to auto-merge the PR with a squash commit.
4. GitHub completes the merge only once branch protection is satisfied — required checks
   green, and required reviews in place if the branch requires them. Nothing in this repo
   approves a PR on a human's behalf.

A red CI run stops the merge and leaves the PR open for a human.

## Repository settings this depends on

- **Settings → General → Pull Requests → Allow auto-merge**: must be enabled, otherwise
  `gh pr merge --auto` and Renovate's `platformAutomerge` both fail and the PRs simply
  wait for a manual merge.
- **Branch protection on `main`**: require the `app` check from `CI`. This is what keeps
  a broken update from auto-merging.

## Turning it off

- One PR: remove the `automerge` label, or run `gh pr merge --disable-auto <number>`.
- One group: set `"automerge": false` on that rule in `.github/renovate.json`.
- Everything: set `"platformAutomerge": false` at the top level of `.github/renovate.json`
  and delete `.github/workflows/bot-autopilot.yml`.

## Still manual

The `chore(data): refresh dataset` commits (`README.md`, `ui/src/data/repos.json`,
`ui/src/data/stats.json`) come from a crawler that lives outside this repository, so they
cannot be scheduled from here. Moving that crawler — or a thin client for it — into
`ui/scripts/` is what it would take to put the dataset refresh on autopilot too.
