/** biome-ignore-all lint/style/useNamingConvention: Test fixtures mirror catalog field names. */

import { describe, expect, it } from 'vitest'
import type { Repo } from '../schemas/repo.schema.ts'
import type { StatsItem } from '../schemas/stats.schema.ts'
import {
  buildMarketAwarenessReport,
  classifyIntent,
  classifySegment,
  getSegmentLabel,
  MARKET_AWARENESS_VERSION,
} from './marketAwareness.ts'

type RepoOverrides = Partial<Repo> & { owner: string; repo_name: string }

function makeRepo({ owner, repo_name, ...overrides }: RepoOverrides): Repo {
  return {
    html_url: `https://github.com/${owner}/${repo_name}`,
    stargazers_count: 0,
    forks_count: 0,
    subscribers_count: 0,
    description: null,
    owner,
    owner_url: `https://github.com/${owner}`,
    repo_name,
    plugins_count: 1,
    id: 0,
    ...overrides,
  }
}

function makeStats(entries: readonly [string, number][]): StatsItem[] {
  return entries.map(([date, size], index) => ({ id: index + 1, date, size }))
}

describe('classifySegment', () => {
  it('files a repository under the definition matching the most patterns', () => {
    const repo = makeRepo({
      owner: 'acme',
      repo_name: 'scanner',
      description: 'Security scanner that finds vulnerabilities and CVEs during pentest engagements.',
    })
    expect(classifySegment(repo)).toBe('security')
  })

  it('prefers the specific segment over the generic one when both match', () => {
    const repo = makeRepo({
      owner: 'acme',
      repo_name: 'deck-skills',
      description: 'Skills that build slides, presentations and pptx decks.',
    })
    expect(classifySegment(repo)).toBe('presentations')
  })

  it('falls back to unclassified when nothing matches', () => {
    expect(classifySegment(makeRepo({ owner: 'acme', repo_name: 'zzz', description: null }))).toBe('unclassified')
  })

  it('classifies on the repository name when the description is missing', () => {
    expect(classifySegment(makeRepo({ owner: 'acme', repo_name: 'claude-memory-recall', description: null }))).toBe('memory-context')
  })
})

describe('classifyIntent', () => {
  it('recognises repositories that name the agent ecosystem', () => {
    const repo = makeRepo({ owner: 'acme', repo_name: 'thing', description: 'A Claude Code plugin for teams.' })
    expect(classifyIntent(repo)).toBe('purpose-built')
  })

  it('separates generic AI tooling from purpose-built work', () => {
    const repo = makeRepo({ owner: 'acme', repo_name: 'thing', description: 'An LLM inference server.' })
    expect(classifyIntent(repo)).toBe('adjacent')
  })

  it('treats unrelated projects as incidental', () => {
    const repo = makeRepo({ owner: 'acme', repo_name: 'thing', description: 'A CSS grid helper.' })
    expect(classifyIntent(repo)).toBe('incidental')
  })
})

describe('getSegmentLabel', () => {
  it('labels known and unknown segments', () => {
    expect(getSegmentLabel('security')).toBe('Security & compliance')
    expect(getSegmentLabel('unclassified')).toBe('Unclassified')
  })
})

describe('buildMarketAwarenessReport', () => {
  const stats = makeStats([
    ['2026-01-01T00:00:00.000Z', 100],
    ['2026-02-01T00:00:00.000Z', 200],
    ['2026-03-01T00:00:00.000Z', 400],
    ['2026-04-01T00:00:00.000Z', 800],
  ])

  const repos: Repo[] = [
    makeRepo({ owner: 'acme', repo_name: 'alpha', description: 'Claude Code security plugin.', stargazers_count: 500, plugins_count: 60 }),
    makeRepo({ owner: 'acme', repo_name: 'beta', description: 'Claude Code memory plugin.', stargazers_count: 50, plugins_count: 12 }),
    makeRepo({ owner: 'acme', repo_name: 'gamma', description: 'A skills collection.', stargazers_count: 5, plugins_count: 3 }),
    makeRepo({ owner: 'acme', repo_name: 'delta', description: null, stargazers_count: 0, plugins_count: null }),
  ]

  it('reports totals over canonical repositories only', () => {
    const duplicate = makeRepo({ owner: 'ACME', repo_name: 'Alpha', stargazers_count: 999, plugins_count: 99 })
    const report = buildMarketAwarenessReport({ repos: [...repos, duplicate], stats })

    expect(report.version).toBe(MARKET_AWARENESS_VERSION)
    expect(report.totals.repos).toBe(4)
    expect(report.totals.stars).toBe(555)
    expect(report.totals.plugins).toBe(75)
    expect(report.dataHealth.duplicatePaths).toBe(1)
  })

  it('skips records without an owner or repository name', () => {
    const headless = makeRepo({ owner: 'acme', repo_name: 'epsilon' })
    const report = buildMarketAwarenessReport({ repos: [...repos, { ...headless, owner: null }], stats })
    expect(report.totals.repos).toBe(4)
  })

  it('measures growth against the nearest snapshot at or before each cutoff', () => {
    const report = buildMarketAwarenessReport({ repos, stats })
    const window = report.growth.windows.find((entry) => entry.requestedDays === 30)

    expect(report.growth.asOf).toBe('2026-04-01T00:00:00.000Z')
    expect(report.growth.size).toBe(800)
    expect(window?.startSize).toBe(400)
    expect(window?.added).toBe(400)
    expect(window?.changePercent).toBe(100)
    expect(report.growth.doublingDays).toBeGreaterThan(0)
  })

  it('reports an unknown trend when there are too few snapshots to compare', () => {
    const report = buildMarketAwarenessReport({ repos, stats: makeStats([['2026-04-01T00:00:00.000Z', 800]]) })
    expect(report.growth.trend).toBe('unknown')
    expect(report.growth.windows).toEqual([])
    expect(report.growth.doublingDays).toBeNull()
  })

  it('measures concentration and holds the traction bar at one star or more', () => {
    const report = buildMarketAwarenessReport({ repos, stats })

    expect(report.concentration.totalStars).toBe(555)
    expect(report.concentration.tractionBar).toBeGreaterThanOrEqual(1)
    expect(report.concentration.giniCoefficient).toBeGreaterThan(0)
    expect(report.concentration.zeroStarShare).toBe(25)
  })

  it('buckets repositories by marketplace depth', () => {
    const report = buildMarketAwarenessReport({ repos, stats })
    const byId = Object.fromEntries(report.depth.map((bucket) => [bucket.id, bucket.repos]))

    expect(byId['mega-marketplace']).toBe(1)
    expect(byId['large-suite']).toBe(1)
    expect(byId['small-suite']).toBe(1)
    expect(byId.unverified).toBe(1)
  })

  it('separates the raw unclassified share from the share that had a description to match', () => {
    const report = buildMarketAwarenessReport({ repos, stats })

    expect(report.dataHealth.missingDescription).toBe(1)
    expect(report.dataHealth.unclassifiedShare).toBeGreaterThan(0)
    expect(report.dataHealth.describedUnclassifiedShare).toBe(0)
  })

  it('leaves momentum unset without a baseline', () => {
    expect(buildMarketAwarenessReport({ repos, stats }).momentum).toBeNull()
  })

  it('measures movement against a baseline snapshot', () => {
    const baselineRepos: Repo[] = [
      makeRepo({
        owner: 'acme',
        repo_name: 'alpha',
        description: 'Claude Code security plugin.',
        stargazers_count: 100,
        plugins_count: 40,
      }),
      makeRepo({ owner: 'acme', repo_name: 'beta', description: 'Claude Code memory plugin.', stargazers_count: 50, plugins_count: 12 }),
      makeRepo({ owner: 'acme', repo_name: 'retired', description: 'Gone from the catalog.', stargazers_count: 7, plugins_count: 1 }),
    ]

    const report = buildMarketAwarenessReport({ repos, stats, baselineRepos, baselineLabel: 'HEAD~1' })
    const momentum = report.momentum

    expect(momentum?.baseline).toBe('HEAD~1')
    expect(momentum?.entrants).toBe(2)
    expect(momentum?.exits).toBe(1)
    expect(momentum?.netRepoChange).toBe(1)
    expect(momentum?.starDelta).toBe(555 - 157)
    expect(momentum?.topGainers[0]?.path).toBe('acme/alpha')
    expect(momentum?.topGainers[0]?.starDelta).toBe(400)
    expect(momentum?.topGainers[0]?.starDeltaPercent).toBe(400)
    expect(momentum?.topGainers[0]?.pluginDelta).toBe(20)
    expect(momentum?.topBreakouts[0]?.path).toBe('acme/alpha')
  })

  it('does not divide by zero when the catalog is empty', () => {
    const report = buildMarketAwarenessReport({ repos: [], stats: [] })

    expect(report.totals).toEqual({ repos: 0, plugins: 0, stars: 0 })
    expect(report.concentration.giniCoefficient).toBe(0)
    expect(report.dataHealth.describedUnclassifiedShare).toBe(0)
    expect(report.segments).toEqual([])
  })
})
