#!/usr/bin/env node

/**
 * Market awareness report, version 3.
 *
 * Reads the committed catalog snapshot and prints a briefing on ecosystem growth, attention
 * concentration, segment supply and demand, marketplace depth, and — with `--baseline` — movement
 * against an earlier revision of `repos.json`.
 *
 * Requires a Node release with TypeScript stripping enabled by default (Node 22.18+ or 24, as
 * pinned by `.nvmrc`).
 *
 * Usage:
 *   npm run market-awareness
 *   npm run market-awareness -- --baseline HEAD~5 --top 15
 *   npm run market-awareness -- --format json --out ../artifacts/market-awareness.json
 */

import { execFileSync } from 'node:child_process'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'
import { buildMarketAwarenessReport } from '../src/lib/marketAwareness.ts'
import { renderMarketAwarenessMarkdown } from '../src/lib/marketAwarenessReport.ts'
import { ReposArraySchema } from '../src/schemas/repo.schema.ts'
import { StatsArraySchema } from '../src/schemas/stats.schema.ts'

const REPOS_PATH_IN_REPOSITORY = 'ui/src/data/repos.json'
const DEFAULT_REPOS_URL = new URL('../src/data/repos.json', import.meta.url)
const DEFAULT_STATS_URL = new URL('../src/data/stats.json', import.meta.url)
const REPOSITORY_ROOT = fileURLToPath(new URL('../..', import.meta.url))

const USAGE = [
  'Usage: node scripts/marketAwareness.mts [options]',
  '',
  'Options:',
  '  --format <md|json>   Output format (default: md)',
  '  --out <path>         Write to a file instead of stdout',
  '  --baseline <rev>     Git revision of repos.json to measure movement against',
  '  --top <n>            Rows per leaderboard (default: 10)',
  '  --repos <path>       Override the catalog snapshot path',
  '  --stats <path>       Override the size time series path',
  '  --no-validate        Skip schema validation of the inputs',
  '  --help               Show this message',
].join('\n')

const { values } = parseArgs({
  options: {
    format: { type: 'string', default: 'md' },
    out: { type: 'string' },
    baseline: { type: 'string' },
    top: { type: 'string', default: '10' },
    repos: { type: 'string' },
    stats: { type: 'string' },
    'no-validate': { type: 'boolean', default: false },
    help: { type: 'boolean', default: false },
  },
})

const validate = !values['no-validate']

try {
  main()
} catch (error) {
  console.error(`market-awareness: ${error instanceof Error ? error.message : String(error)}`)
  if (error instanceof Error && error.cause instanceof Error) {
    console.error(`  caused by: ${error.cause.message}`)
  }
  process.exitCode = 1
}

function main(): void {
  if (values.help) {
    console.log(USAGE)
    return
  }

  if (values.format !== 'md' && values.format !== 'json') {
    throw new Error(`Unsupported --format "${values.format}". Expected "md" or "json".`)
  }

  const topCount = Number.parseInt(values.top ?? '10', 10)
  if (!Number.isInteger(topCount) || topCount < 1) {
    throw new Error(`Invalid --top "${values.top}". Expected a positive integer.`)
  }

  const repos = parseRepos(readSource(resolveInput(values.repos, DEFAULT_REPOS_URL)), values.repos ?? 'repos.json')
  const stats = parseStats(readSource(resolveInput(values.stats, DEFAULT_STATS_URL)))
  const baselineRepos = values.baseline
    ? parseRepos(readBaseline(values.baseline), `${values.baseline}:${REPOS_PATH_IN_REPOSITORY}`)
    : undefined

  const report = buildMarketAwarenessReport({ repos, stats, baselineRepos, baselineLabel: values.baseline, topCount })
  const output = values.format === 'json' ? `${JSON.stringify(report, null, 2)}\n` : `${renderMarketAwarenessMarkdown(report)}\n`

  if (values.out) {
    mkdirSync(dirname(values.out), { recursive: true })
    writeFileSync(values.out, output)
    console.error(`Wrote ${values.format} report for ${report.totals.repos.toLocaleString('en-US')} repositories to ${values.out}`)
    return
  }

  process.stdout.write(output)
}

function resolveInput(override: string | undefined, fallback: URL): URL {
  return override ? pathToFileURL(resolve(process.cwd(), override)) : fallback
}

function readSource(url: URL): string {
  try {
    return readFileSync(url, 'utf8')
  } catch (cause) {
    throw new Error(`Failed to read ${fileURLToPath(url)}`, { cause })
  }
}

function readBaseline(revision: string): string {
  try {
    return execFileSync('git', ['show', `${revision}:${REPOS_PATH_IN_REPOSITORY}`], {
      cwd: REPOSITORY_ROOT,
      encoding: 'utf8',
      maxBuffer: 512 * 1024 * 1024,
    })
  } catch (cause) {
    throw new Error(`Failed to read ${REPOS_PATH_IN_REPOSITORY} at revision "${revision}"`, { cause })
  }
}

function parseRepos(raw: string, label: string) {
  const parsed: unknown = JSON.parse(raw)
  if (!validate) {
    return parsed as ReturnType<typeof ReposArraySchema.parse>
  }

  const result = ReposArraySchema.safeParse(parsed)
  if (!result.success) {
    const issues = result.error.issues
      .slice(0, 5)
      .map((issue) => `${issue.path.join('.')}: ${issue.message}`)
      .join('; ')
    throw new Error(`Invalid catalog data in ${label} (${result.error.issues.length} issue(s)): ${issues}`)
  }

  return result.data
}

function parseStats(raw: string) {
  const parsed: unknown = JSON.parse(raw)
  if (!validate) {
    return parsed as ReturnType<typeof StatsArraySchema.parse>
  }

  const result = StatsArraySchema.safeParse(parsed)
  if (!result.success) {
    throw new Error(`Invalid stats data: ${result.error.issues.map((issue) => issue.message).join(', ')}`)
  }

  return result.data
}
