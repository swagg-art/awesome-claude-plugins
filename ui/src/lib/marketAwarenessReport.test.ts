/** biome-ignore-all lint/style/useNamingConvention: Test fixtures mirror catalog field names. */

import { describe, expect, it } from 'vitest'
import type { Repo } from '../schemas/repo.schema.ts'
import { buildMarketAwarenessReport } from './marketAwareness.ts'
import { renderMarketAwarenessMarkdown } from './marketAwarenessReport.ts'

function makeRepo(owner: string, repoName: string, description: string | null, stars: number, plugins: number | null): Repo {
  return {
    html_url: `https://github.com/${owner}/${repoName}`,
    stargazers_count: stars,
    forks_count: Math.floor(stars / 10),
    subscribers_count: Math.floor(stars / 50),
    description,
    owner,
    owner_url: `https://github.com/${owner}`,
    repo_name: repoName,
    plugins_count: plugins,
    id: 0,
  }
}

const repos: Repo[] = [
  makeRepo('acme', 'alpha', 'Claude Code security plugin for vulnerability scanning.', 500, 60),
  makeRepo('acme', 'beta', 'Claude Code memory and context plugin.', 50, 12),
  makeRepo('acme', 'gamma', 'A skills collection.', 5, 3),
  makeRepo('acme', 'delta', null, 0, null),
]

const stats = [
  { id: 1, date: '2026-01-01T00:00:00.000Z', size: 100 },
  { id: 2, date: '2026-02-01T00:00:00.000Z', size: 200 },
  { id: 3, date: '2026-03-01T00:00:00.000Z', size: 400 },
  { id: 4, date: '2026-04-01T00:00:00.000Z', size: 800 },
]

function render(baselineRepos?: Repo[]): string {
  return renderMarketAwarenessMarkdown(
    buildMarketAwarenessReport({
      repos,
      stats,
      baselineRepos,
      baselineLabel: baselineRepos ? 'HEAD~1' : undefined,
      generatedAt: new Date('2026-04-02T00:00:00.000Z'),
    })
  )
}

describe('renderMarketAwarenessMarkdown', () => {
  it('renders every section of the briefing', () => {
    const markdown = render()

    expect(markdown).toContain('# Claude Code plugin market awareness (v3)')
    for (const heading of [
      '## Ecosystem growth',
      '## Attention concentration',
      '## Who is actually building for this market',
      '## Segments',
      '## Where the room is',
      '## Marketplace depth',
      '## Attention leaders',
      '## Momentum',
      '## Data health',
    ]) {
      expect(markdown).toContain(heading)
    }
  })

  it('renders the generation and snapshot dates as plain days', () => {
    expect(render()).toContain('Generated 2026-04-02 from the committed catalog snapshot.')
  })

  it('emits well-formed table rows', () => {
    const rows = render()
      .split('\n')
      .filter((line) => line.startsWith('|'))

    expect(rows.length).toBeGreaterThan(0)
    for (const row of rows) {
      expect(row.startsWith('| ')).toBe(true)
      expect(row.endsWith(' |')).toBe(true)
      expect(row).not.toContain('|  |')
    }
  })

  it('links attention leaders to their repositories', () => {
    expect(render()).toContain('[acme/alpha](https://github.com/acme/alpha)')
  })

  it('points at the baseline flag when momentum was not requested', () => {
    expect(render()).toContain('Run with `--baseline <git-rev>` to compare against an earlier catalog snapshot.')
  })

  it('renders momentum tables when a baseline is supplied', () => {
    const markdown = render([makeRepo('acme', 'alpha', 'Claude Code security plugin for vulnerability scanning.', 100, 40)])

    expect(markdown).toContain('Compared against `HEAD~1`.')
    expect(markdown).toContain('### Biggest star gains')
    expect(markdown).toContain('### Notable new entrants')
    expect(markdown).toContain('### Segment intake')
  })

  it('renders without a growth table when there are no snapshots', () => {
    const markdown = renderMarketAwarenessMarkdown(buildMarketAwarenessReport({ repos, stats: [] }))
    expect(markdown).toContain('Not enough snapshots in `stats.json` to measure growth.')
  })
})
