# Bots autopilot — summary report

**Date:** 2026-09-16
**Branch:** `claude/bots-autopilot-ayt9fw`
**Scope:** put the repository's maintenance bots on autopilot

## Problem

Maintenance in this repository was bot-*assisted*, not bot-*driven*. Renovate opened PRs
on a weekly schedule, but every one of them — including lock file maintenance and
`@types/*` patches — waited on a human to click merge. Two further problems made that
worse:

1. **The Renovate config was silently half-broken.** `renovate-config-validator` reported
   `Config migration necessary`: `matchPackagePatterns` (the `^@types/` grouping rule) and
   `excludePackageNames` (the framework carve-out on majors) are deprecated. Renovate
   migrates them in memory, but the config as written is no longer canonical and the
   grouping it expresses is one release away from not applying at all.
2. **Nothing merged anything.** There was no auto-merge path, so the backlog grew between
   maintenance sessions.

## Changes

| File | Change |
|---|---|
| `.github/renovate.json` | Migrated deprecated matchers; added an auto-merge policy, a security-alert fast path, a GitHub Actions rule, and flow controls |
| `.github/workflows/bot-autopilot.yml` | New: queues labelled bot PRs for GitHub native auto-merge |
| `.github/workflows/ci.yml` | Added a concurrency group so superseded PR runs are cancelled |
| `.github/BOTS.md` | New: documents what merges itself, what waits for a human, and the repo settings it depends on |

### Renovate policy

Auto-merges once CI is green (all with a 3-day `minimumReleaseAge`, so nothing merges the
hour it is published):

- tooling and type dependencies (minor/patch)
- runtime dependencies (minor/patch)
- GitHub Actions (minor/patch/digest) — a new rule; action versions were previously
  ungoverned
- lock file maintenance
- security fixes, which additionally bypass the weekly windows (`schedule: at any time`,
  no release-age delay, `prCreation: immediate`)

Always waits for a human:

- `next`, `react`, `react-dom` at any update type
- every non-framework major

Flow controls added: `rebaseWhen: behind-base-branch`, `prConcurrentLimit: 5`,
`prHourlyLimit: 2`, `automergeStrategy: squash`, `platformAutomerge: true`, plus a
`dependencies` label on every PR and a dependency dashboard.

### Merge path and its limits

`platformAutomerge` (Renovate) and `bot-autopilot.yml` both request GitHub's native
auto-merge; the workflow is redundancy for the case where Renovate's own call does not go
through, and it also covers Dependabot security PRs. The workflow uses
`pull_request_target` to keep a writable token on bot branches, checks out no repository
code, and runs only the GitHub CLI.

**The workflow does not approve pull requests.** An earlier draft included a step that
approved bot PRs as `github-actions[bot]` so they could satisfy a required-review rule;
that step was removed, because a workflow approving its own merges defeats the review
requirement it is meant to satisfy. GitHub's auto-merge therefore remains fully gated by
branch protection: required checks must pass, and required reviews must be present.

## Prerequisites the repository owner must enable

Neither can be set from a pull request:

1. **Settings → General → Pull Requests → Allow auto-merge.** Without it,
   `gh pr merge --auto` and `platformAutomerge` both fail and PRs wait for a manual merge —
   the same behaviour as today, so nothing regresses, but nothing improves either.
2. **Branch protection on `main` requiring the `app` check from `CI`.** This is the safety
   gate; without it, auto-merge could land a PR before CI reports.

If required reviews are also enabled on `main`, bot PRs will need one human approval each
and auto-merge will only shorten the wait, not remove it.

## Verification

- `renovate-config-validator` on the new `.github/renovate.json`:
  `Config validated successfully against 1 file(s)`, with the migration warning gone.
- All three workflow files parse as YAML.
- No files under `ui/` changed, so the existing typecheck / lint / unit / build / e2e
  pipeline is untouched.

## Out of scope

The `chore(data): refresh dataset` commits — `README.md`, `ui/src/data/repos.json`,
`ui/src/data/stats.json`, roughly weekly — are produced by a crawler that does not live in
this repository, so they cannot be scheduled from here. Putting the dataset refresh on
autopilot means moving that crawler (or a thin client for it) into `ui/scripts/` and adding
a scheduled workflow that commits the result. That is the single largest remaining manual
task in this repository and the obvious next step.
