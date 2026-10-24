import type {
  DepthBucket,
  EcosystemGrowth,
  IntentBreakdown,
  MarketAwarenessReport,
  MomentumReport,
  RepoRef,
  SegmentInsight,
} from './marketAwareness.ts'

/**
 * Renders a {@link MarketAwarenessReport} as a Markdown briefing.
 *
 * The output is plain Markdown so it can be pasted into an issue, committed as an artifact, or
 * posted to a release note without further processing.
 */
export function renderMarketAwarenessMarkdown(report: MarketAwarenessReport): string {
  return [
    ...renderHeader(report),
    ...renderGrowth(report.growth),
    ...renderConcentration(report),
    ...renderIntent(report.intent),
    ...renderSegments(report.segments),
    ...renderOpportunities(report.segments),
    ...renderDepth(report.depth),
    ...renderLeaders(report.leaders),
    ...renderMomentum(report.momentum),
    ...renderDataHealth(report),
  ].join('\n')
}

const INTENT_LABELS: Record<IntentBreakdown['intent'], string> = {
  'purpose-built': 'Purpose-built for the agent ecosystem',
  adjacent: 'Adjacent AI tooling',
  incidental: 'Incidental (general project shipping a manifest)',
}

const TREND_NOTES: Record<EcosystemGrowth['trend'], string> = {
  accelerating: 'the last 30 days added repositories faster than the 30 days before them',
  steady: 'the intake rate is holding within 10% of the previous 30 days',
  cooling: 'the last 30 days added repositories slower than the 30 days before them',
  unknown: 'not enough snapshots to compare consecutive 30-day windows',
}

function renderHeader(report: MarketAwarenessReport): string[] {
  return [
    `# Claude Code plugin market awareness (v${report.version})`,
    '',
    `Generated ${formatDate(report.generatedAt)} from the committed catalog snapshot.`,
    '',
    '| Measure | Value |',
    '| --- | --- |',
    `| Repositories tracked | ${formatNumber(report.totals.repos)} |`,
    `| Plugins detected | ${formatNumber(report.totals.plugins)} |`,
    `| Combined stars | ${formatNumber(report.totals.stars)} |`,
    `| Catalog snapshot date | ${formatDate(report.growth.asOf)} |`,
    '',
  ]
}

function renderGrowth(growth: EcosystemGrowth): string[] {
  const lines = ['## Ecosystem growth', '']

  if (growth.windows.length === 0) {
    return [...lines, 'Not enough snapshots in `stats.json` to measure growth.', '']
  }

  lines.push('| Window | Actual span | Added | Change | Per day |', '| --- | --- | --- | --- | --- |')
  for (const window of growth.windows) {
    lines.push(
      `| ${window.label} | ${window.actualDays} d | ${formatSigned(window.added)} | ${formatPercent(window.changePercent)} | ${window.perDay} |`
    )
  }

  lines.push('', `**Trend: ${growth.trend}** — ${TREND_NOTES[growth.trend]}.`)
  if (growth.doublingDays !== null) {
    lines.push('', `At the trailing 90-day compound rate the catalog doubles in about ${growth.doublingDays} days.`)
  }
  lines.push('')

  return lines
}

function renderConcentration(report: MarketAwarenessReport): string[] {
  const { concentration, engagement } = report

  return [
    '## Attention concentration',
    '',
    '| Measure | Value |',
    '| --- | --- |',
    `| Median stars | ${formatNumber(concentration.medianStars)} |`,
    `| Mean stars | ${formatNumber(concentration.meanStars)} |`,
    `| 90th percentile stars | ${formatNumber(concentration.p90Stars)} |`,
    `| Traction bar (stars) | ${formatNumber(concentration.tractionBar)} |`,
    `| Repositories at or above the bar | ${formatPercent(concentration.tractionRate)} |`,
    `| Stars held by the top 1% | ${formatPercent(concentration.topOnePercentStarShare)} |`,
    `| Stars held by the top 10% | ${formatPercent(concentration.topTenPercentStarShare)} |`,
    `| Gini coefficient (stars) | ${concentration.giniCoefficient} |`,
    `| Repositories with zero stars | ${formatPercent(concentration.zeroStarShare)} |`,
    `| Watchers per 1,000 stars | ${engagement.watchRatePerThousandStars} |`,
    `| Forks per 1,000 stars | ${engagement.forkRatePerThousandStars} |`,
    '',
    concentrationNote(concentration.giniCoefficient),
    '',
  ]
}

function concentrationNote(giniCoefficient: number): string {
  if (giniCoefficient >= 0.9) {
    return 'Attention is extremely concentrated: a handful of repositories absorb nearly all of it, so a new entrant competes for a very thin tail.'
  }
  if (giniCoefficient >= 0.7) {
    return 'Attention is heavily concentrated, which is normal for an open catalog but means median discovery is hard without distribution.'
  }
  return 'Attention is comparatively evenly spread across the catalog.'
}

function renderIntent(intent: readonly IntentBreakdown[]): string[] {
  const lines = [
    '## Who is actually building for this market',
    '',
    '| Cohort | Repositories | Share | Star share |',
    '| --- | --- | --- | --- |',
  ]

  for (const entry of intent) {
    lines.push(
      `| ${INTENT_LABELS[entry.intent]} | ${formatNumber(entry.repos)} | ${formatPercent(entry.share)} | ${formatPercent(entry.starShare)} |`
    )
  }

  lines.push(
    '',
    'Cohorts are inferred from repository names and descriptions, so treat them as a directional read rather than a census.',
    ''
  )

  return lines
}

function renderSegments(segments: readonly SegmentInsight[]): string[] {
  const lines = [
    '## Segments',
    '',
    '| Segment | Repos | Share | Traction | Plugins | Purpose-built | Demand | Supply | Verdict |',
    '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
  ]

  for (const segment of segments) {
    const cells = [
      segment.label,
      formatNumber(segment.repos),
      formatPercent(segment.repoShare),
      formatPercent(segment.tractionRate),
      formatNumber(segment.plugins),
      formatPercent(segment.purposeBuiltShare),
      `${segment.demandIndex}x`,
      `${segment.supplyIndex}x`,
      segment.demand,
    ]
    lines.push(`| ${cells.join(' | ')} |`)
  }

  lines.push(
    '',
    'Traction is the share of a segment at or above the catalog traction bar. Demand is that share against the catalog-wide rate;',
    'supply is the segment repository share against the median classified segment. Segments too small to read are left unrated.',
    ''
  )

  return lines
}

function renderOpportunities(segments: readonly SegmentInsight[]): string[] {
  const underserved = segments.filter((segment) => segment.demand === 'underserved')
  const crowded = segments.filter((segment) => segment.demand === 'crowded')
  const lines = ['## Where the room is', '']

  if (underserved.length === 0) {
    lines.push('No segment currently clears the underserved threshold (demand at or above 1.2x with supply at or below parity).')
  } else {
    lines.push('Segments converting to traction above the catalog rate while carrying below-baseline supply:', '')
    for (const segment of underserved) {
      const exemplars = segment.exemplars.map((exemplar) => exemplar.path).join(', ')
      lines.push(`- **${segment.label}** — ${segment.demandIndex}x demand on ${segment.supplyIndex}x supply. Bellwethers: ${exemplars}.`)
    }
  }

  if (crowded.length > 0) {
    lines.push('', 'Segments carrying above-baseline supply without the matching pull:', '')
    for (const segment of crowded) {
      lines.push(`- **${segment.label}** — ${segment.supplyIndex}x supply on ${segment.demandIndex}x demand.`)
    }
  }

  lines.push('')

  return lines
}

function renderDepth(depth: readonly DepthBucket[]): string[] {
  const lines = ['## Marketplace depth', '', '| Shape | Repos | Share | Plugins |', '| --- | --- | --- | --- |']

  for (const bucket of depth) {
    lines.push(`| ${bucket.label} | ${formatNumber(bucket.repos)} | ${formatPercent(bucket.share)} | ${formatNumber(bucket.plugins)} |`)
  }

  lines.push('')

  return lines
}

function renderLeaders(leaders: readonly RepoRef[]): string[] {
  const lines = ['## Attention leaders', '', '| Repository | Stars | Plugins |', '| --- | --- | --- |']

  for (const leader of leaders) {
    lines.push(`| [${leader.path}](${leader.url}) | ${formatNumber(leader.stars)} | ${formatNumber(leader.plugins)} |`)
  }

  lines.push('')

  return lines
}

function renderMomentum(momentum: MomentumReport | null): string[] {
  if (!momentum) {
    return ['## Momentum', '', 'Run with `--baseline <git-rev>` to compare against an earlier catalog snapshot.', '']
  }

  const lines = [
    '## Momentum',
    '',
    `Compared against \`${momentum.baseline}\`.`,
    '',
    '| Measure | Value |',
    '| --- | --- |',
    `| Repositories then | ${formatNumber(momentum.baselineRepos)} |`,
    `| Repositories now | ${formatNumber(momentum.currentRepos)} |`,
    `| Net change | ${formatSigned(momentum.netRepoChange)} |`,
    `| New entrants | ${formatNumber(momentum.entrants)} |`,
    `| Dropped out | ${formatNumber(momentum.exits)} |`,
    `| Star change | ${formatSigned(momentum.starDelta)} |`,
    `| Plugin change | ${formatSigned(momentum.pluginDelta)} |`,
    '',
  ]

  if (momentum.topGainers.length > 0) {
    lines.push('### Biggest star gains', '', '| Repository | Stars | Gain | Change |', '| --- | --- | --- | --- |')
    for (const entry of momentum.topGainers) {
      lines.push(
        `| [${entry.path}](${entry.url}) | ${formatNumber(entry.stars)} | ${formatSigned(entry.starDelta)} | ${formatPercent(entry.starDeltaPercent)} |`
      )
    }
    lines.push('')
  }

  if (momentum.topBreakouts.length > 0) {
    lines.push('### Fastest climbers', '', '| Repository | Then | Now | Change |', '| --- | --- | --- | --- |')
    for (const entry of momentum.topBreakouts) {
      lines.push(
        `| [${entry.path}](${entry.url}) | ${formatNumber(entry.previousStars)} | ${formatNumber(entry.stars)} | ${formatPercent(entry.starDeltaPercent)} |`
      )
    }
    lines.push('')
  }

  if (momentum.topNewEntrants.length > 0) {
    lines.push('### Notable new entrants', '', '| Repository | Stars | Plugins |', '| --- | --- | --- |')
    for (const entry of momentum.topNewEntrants) {
      lines.push(`| [${entry.path}](${entry.url}) | ${formatNumber(entry.stars)} | ${formatNumber(entry.plugins)} |`)
    }
    lines.push('')
  }

  const movingSegments = momentum.segments.filter((segment) => segment.repoDelta !== 0).slice(0, 10)
  if (movingSegments.length > 0) {
    lines.push('### Segment intake', '', '| Segment | Then | Now | Net repos | Star change |', '| --- | --- | --- | --- | --- |')
    for (const segment of movingSegments) {
      const cells = [
        segment.label,
        formatNumber(segment.previousRepos),
        formatNumber(segment.repos),
        formatSigned(segment.repoDelta),
        formatSigned(segment.starDelta),
      ]
      lines.push(`| ${cells.join(' | ')} |`)
    }
    lines.push('')
  }

  return lines
}

function renderDataHealth(report: MarketAwarenessReport): string[] {
  const { dataHealth } = report

  return [
    '## Data health',
    '',
    '| Check | Value |',
    '| --- | --- |',
    `| Raw records | ${formatNumber(dataHealth.repos)} |`,
    `| Canonical records analysed | ${formatNumber(dataHealth.canonicalRepos)} |`,
    `| Case-duplicate paths skipped | ${formatNumber(dataHealth.duplicatePaths)} |`,
    `| Missing description | ${formatNumber(dataHealth.missingDescription)} |`,
    `| Plugin count unverified | ${formatNumber(dataHealth.unverifiedPluginCount)} |`,
    `| Zero-star repositories | ${formatNumber(dataHealth.zeroStar)} |`,
    `| Unclassified by segment | ${formatPercent(dataHealth.unclassifiedShare)} |`,
    `| Unclassified despite having a description | ${formatPercent(dataHealth.describedUnclassifiedShare)} |`,
    '',
    'Repositories with no description can only be matched on their name, so the second figure is the real taxonomy gap:',
    'when it climbs, the segment patterns need extending rather than the market lacking a theme.',
    '',
  ]
}

function formatNumber(value: number): string {
  return value.toLocaleString('en-US')
}

function formatSigned(value: number): string {
  return value > 0 ? `+${formatNumber(value)}` : formatNumber(value)
}

function formatPercent(value: number): string {
  return `${value}%`
}

function formatDate(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toISOString().slice(0, 10)
}
