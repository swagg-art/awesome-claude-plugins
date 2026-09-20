/** biome-ignore-all lint/style/useNamingConvention: catalog data uses snake_case fields */

import type { Repo } from '../schemas/repo.schema.ts'
import type { StatsItem } from '../schemas/stats.schema.ts'

/**
 * Market awareness, version 3.
 *
 * Turns the raw catalog snapshot (`repos.json`) and the size time series (`stats.json`) into the
 * numbers a maintainer needs to answer "where is this ecosystem going, and where are the gaps?".
 *
 * Every metric here is derived from data already in the repository, so the report is reproducible
 * offline and never depends on a live GitHub call.
 */
export const MARKET_AWARENESS_VERSION = 3

export type MarketSegmentId =
  | 'security'
  | 'seo-marketing'
  | 'presentations'
  | 'media-creative'
  | 'finance-trading'
  | 'data-analytics'
  | 'devops-cloud'
  | 'browser-automation'
  | 'code-quality'
  | 'docs-writing'
  | 'design-ui'
  | 'research-learning'
  | 'productivity-pm'
  | 'memory-context'
  | 'orchestration'
  | 'mcp-integrations'
  | 'dev-tooling'
  | 'skill-libraries'
  | 'agent-frameworks'
  | 'unclassified'

/**
 * How deliberately a repository serves this market.
 *
 * `purpose-built` names the agent ecosystem outright, `adjacent` is generic AI tooling that also
 * ships a manifest, and `incidental` is a general-purpose project that happens to carry one.
 */
export type RepoIntent = 'purpose-built' | 'adjacent' | 'incidental'

export type DepthBucketId = 'unverified' | 'none' | 'single' | 'small-suite' | 'large-suite' | 'mega-marketplace'

export type SegmentDemand = 'underserved' | 'balanced' | 'crowded' | 'unrated'

export type GrowthTrend = 'accelerating' | 'steady' | 'cooling' | 'unknown'

type SegmentDefinition = {
  id: MarketSegmentId
  label: string
  patterns: readonly RegExp[]
}

/**
 * Ordered most specific to most generic: a repository is filed under the definition matching the
 * most patterns, and ties fall to the earlier (more specific) entry.
 */
const SEGMENT_DEFINITIONS: readonly SegmentDefinition[] = [
  {
    id: 'security',
    label: 'Security & compliance',
    patterns: [
      /\bsecurity\b/,
      /\bvulnerabilit/,
      /\bpentest|\bpenetration test/,
      /\bappsec\b|\bdevsecops\b/,
      /\bthreat model/,
      /\bcompliance\b|\bsoc ?2\b|\bhipaa\b|\bgdpr\b/,
      /\bsecrets? scan|\bcredential/,
      /\bcve\b|\bexploit\b|\bmalware\b/,
      /\bred team|\bowasp\b/,
    ],
  },
  {
    id: 'seo-marketing',
    label: 'SEO, marketing & growth',
    patterns: [
      /\bseo\b|\bgeo\/aeo\b|\bserp\b/,
      /\bmarketing\b/,
      /\bcopywriting\b|\bcopywriter\b/,
      /\bgrowth (engineering|marketing|hacking)\b/,
      /\bbacklinks?\b|\bkeyword research\b/,
      /\bsocial media\b|\btwitter\b|\blinkedin\b/,
      /\bcontent strateg/,
      /\bconversion rate|\bcro\b/,
      /\bnewsletter\b|\bcampaign/,
    ],
  },
  {
    id: 'presentations',
    label: 'Slides & presentations',
    patterns: [/\bslides?\b/, /\bpowerpoint\b|\bpptx?\b/, /\bpresentations?\b/, /\bdecks?\b/, /\bkeynote\b/, /\bslidev\b|\breveal\.js\b/],
  },
  {
    id: 'media-creative',
    label: 'Media & creative generation',
    patterns: [
      /\bvideos?\b/,
      /\bimages?\b|\bthumbnails?\b/,
      /\baudio\b|\bmusic\b|\bvoice(over)?\b|\bspeech\b/,
      /\byoutube\b|\btiktok\b|\binstagram\b/,
      /\bffmpeg\b|\brender(ing)?\b/,
      /\bdiffusion\b|\btext-to-(image|video)\b/,
      /\bpodcast\b|\bsubtitle|\btranscri/,
    ],
  },
  {
    id: 'finance-trading',
    label: 'Finance & trading',
    patterns: [
      /\btrading\b|\btrader\b/,
      /\bfinanc(e|ial)\b/,
      /\bcrypto\b|\bblockchain\b|\bdefi\b|\bweb3\b/,
      /\bstocks?\b|\bequit(y|ies)\b|\bticker\b/,
      /\bportfolio\b|\binvest(ing|ment)?\b/,
      /\baccounting\b|\binvoic|\bbookkeeping\b/,
      /\bquant(itative)? (trading|finance)\b|\bbacktest/,
    ],
  },
  {
    id: 'data-analytics',
    label: 'Data & analytics',
    patterns: [
      /\bsql\b|\bpostgres|\bmysql\b|\bsqlite\b/,
      /\bdatabases?\b|\bdata ?warehouse\b|\bbigquery\b|\bsnowflake\b/,
      /\banalytics\b|\bmetrics\b|\btelemetry\b/,
      /\betl\b|\bdata pipeline|\bdbt\b/,
      /\bdashboards?\b|\bbusiness intelligence\b/,
      /\bspreadsheets?\b|\bexcel\b|\bcsv\b/,
      /\bdata (science|analysis|engineering)\b/,
    ],
  },
  {
    id: 'devops-cloud',
    label: 'DevOps, cloud & infrastructure',
    patterns: [
      /\bkubernetes\b|\bk8s\b|\bhelm\b/,
      /\bdocker\b|\bcontainers?\b/,
      /\bterraform\b|\bpulumi\b|\binfrastructure as code\b/,
      /\baws\b|\bazure\b|\bgcp\b|\bcloudflare\b/,
      /\bci\/cd\b|\bgithub actions\b|\bpipelines?\b/,
      /\bdeploy(ment|ing)?\b|\bprovision/,
      /\bobservability\b|\bmonitoring\b|\bincident\b|\bsre\b/,
      /\bserverless\b|\binfrastructure\b/,
    ],
  },
  {
    id: 'browser-automation',
    label: 'Browser & automation',
    patterns: [
      /\bbrowser\b/,
      /\bplaywright\b|\bpuppeteer\b|\bselenium\b/,
      /\bscrap(e|ing|er)\b|\bcrawl(er|ing)\b/,
      /\bheadless\b/,
      /\bweb automation\b|\bbrowser automation\b/,
      /\bchrome\b|\bdevtools\b/,
    ],
  },
  {
    id: 'code-quality',
    label: 'Code review, testing & quality',
    patterns: [
      /\bcode review\b|\breviewer\b/,
      /\blint(er|ing)?\b|\bstatic analysis\b/,
      /\brefactor(ing)?\b/,
      /\btests?\b|\btesting\b|\btdd\b|\bcoverage\b/,
      /\bdebug(ging|ger)?\b/,
      /\bbugs?\b|\bregressions?\b/,
      /\bcode quality\b|\btech(nical)? debt\b/,
      /\bpull requests?\b|\bpr review\b/,
    ],
  },
  {
    id: 'docs-writing',
    label: 'Docs & writing',
    patterns: [
      /\bdocumentation\b|\bdocs\b/,
      /\bdocstrings?\b|\breadme\b/,
      /\bwriting\b|\bwriter\b|\bediting\b/,
      /\btechnical writing\b|\bchangelogs?\b/,
      /\bmarkdown\b/,
      /\bblog(ging|s)?\b|\barticles?\b/,
      /\bhumaniz|\bproofread/,
    ],
  },
  {
    id: 'design-ui',
    label: 'Design & UI',
    patterns: [
      /\bdesign systems?\b|\bdesign language\b/,
      /\bui\/ux\b|\bux\b|\buser interface\b/,
      /\bfigma\b/,
      /\btailwind\b|\bcss\b|\bshadcn\b/,
      /\bcomponents? librar|\bstorybook\b/,
      /\bfrontend\b|\blanding pages?\b/,
      /\bdiagrams?\b|\bwireframe|\bprototyp/,
      /\bthemes?\b|\bstyling\b/,
    ],
  },
  {
    id: 'research-learning',
    label: 'Research & learning',
    patterns: [
      /\bresearch(er|ing)?\b/,
      /\blearning\b|\bteach(ing|er)?\b|\btutor\b/,
      /\bacademic\b|\bpapers?\b|\bcitations?\b/,
      /\bflashcards?\b|\bquiz(zes)?\b|\bstudy\b/,
      /\bknowledge graph\b/,
      /\bsummariz|\bsynthesiz/,
    ],
  },
  {
    id: 'productivity-pm',
    label: 'Productivity & project management',
    patterns: [
      /\bproject management\b|\bproduct manage/,
      /\bjira\b|\blinear\b|\basana\b|\btrello\b/,
      /\bnotion\b|\bobsidian\b|\bconfluence\b/,
      /\btasks?\b|\btodos?\b|\bbacklog\b|\bsprints?\b/,
      /\bcalendar\b|\bschedul(e|ing)\b|\bmeetings?\b/,
      /\bemail\b|\bgmail\b|\bslack\b|\binbox\b/,
      /\bprd\b|\broadmap\b|\bspecs?\b/,
      /\bcareer\b|\bjob (search|portal)|\bresume\b|\bcv\b/,
    ],
  },
  {
    id: 'memory-context',
    label: 'Memory & context engineering',
    patterns: [
      /\bmemor(y|ies)\b/,
      /\bcontext (window|engineering|management|rot|optimization)\b/,
      /\bpersistent context\b|\bsession (state|memory|recovery)\b/,
      /\brecall\b|\bremember\b/,
      /\brag\b|\bretrieval\b|\bembeddings?\b|\bvector (db|store|search)\b/,
      /\bknowledge base\b/,
      /\bcompact(ion|ing)\b|\btoken (reduction|compression|savings?)\b/,
    ],
  },
  {
    id: 'orchestration',
    label: 'Orchestration & multi-agent',
    patterns: [
      /\bmulti-?agent\b/,
      /\bswarms?\b|\bfleets?\b/,
      /\bsub-?agents?\b/,
      /\borchestrat(e|ion|or)\b/,
      /\bworkflows?\b|\bpipelines? of agents\b/,
      /\bdelegat(e|ion)\b|\bhand-?off\b/,
      /\bautonomous\b|\bagent loops?\b/,
      /\bcoordinat(e|ion)\b|\bparallel agents?\b/,
    ],
  },
  {
    id: 'mcp-integrations',
    label: 'MCP servers & integrations',
    patterns: [
      /\bmcp\b/,
      /\bmodel context protocol\b/,
      /\bintegrations?\b|\bconnectors?\b/,
      /\bapi (wrapper|client|bridge)\b/,
      /\bserver\b/,
      /\bwebhooks?\b|\boauth\b/,
    ],
  },
  {
    id: 'dev-tooling',
    label: 'Developer tooling',
    patterns: [
      /\bcli\b|\bterminal\b|\bshell\b/,
      /\bgit\b|\bcommits?\b|\bbranch(es|ing)?\b/,
      /\bide\b|\beditor\b|\bvs ?code\b|\bjetbrains\b|\bneovim\b/,
      /\bpackage manager\b|\bnpm\b|\bmonorepo\b/,
      /\bbuild tool|\bbundler\b|\bcompiler\b/,
      /\bstatus ?line\b|\bhooks?\b/,
      /\bdev(eloper)? (experience|tooling|workflow)\b/,
    ],
  },
  {
    id: 'skill-libraries',
    label: 'Skill & prompt libraries',
    patterns: [
      /\bskills?\b/,
      /\bprompts?\b/,
      /\bcurated (list|collection)\b|\bawesome\b/,
      /\bcollection of\b|\blibrar(y|ies) of\b/,
      /\bcookbook\b|\bcheat ?sheet\b/,
      /\btemplates?\b|\bboilerplate\b/,
      /\bmarketplace\b|\bcatalog(ue)?\b|\bdirectory\b/,
    ],
  },
  {
    id: 'agent-frameworks',
    label: 'Agent frameworks & harnesses',
    patterns: [
      /\bframeworks?\b/,
      /\bharness(es)?\b/,
      /\bsdks?\b/,
      /\bruntimes?\b/,
      /\bprotocols?\b/,
      /\bplatforms?\b/,
      /\bllm (apps?|applications?|engineering)\b/,
      /\bevals?\b|\bbenchmark(ing|s)?\b/,
    ],
  },
]

const PURPOSE_BUILT_PATTERNS: readonly RegExp[] = [
  /\bclaude( code)?\b/,
  /\bagent skills?\b/,
  /\bsub-?agents?\b/,
  /\bplugins?\b/,
  /\bskills?\b/,
  /\bmarketplace\b/,
  /\bslash commands?\b/,
  /\bcoding agents?\b|\bai agents?\b/,
  /\bmcp\b/,
  /\bcodex\b|\bcursor\b|\bopencode\b|\bgemini cli\b|\bcopilot\b|\bantigravity\b/,
]

const ADJACENT_PATTERNS: readonly RegExp[] = [
  /\bai\b/,
  /\bllms?\b/,
  /\bagents?\b/,
  /\bgpt\b/,
  /\bprompt/,
  /\bmodels?\b/,
  /\banthropic\b|\bopenai\b/,
]

const BREAKOUT_MINIMUM_STARS = 100

/** Below this many repositories a segment's traction rate is too noisy to call over- or under-served. */
const SEGMENT_RATING_MINIMUM_REPOS = 50

export type SegmentInsight = {
  id: MarketSegmentId
  label: string
  repos: number
  repoShare: number
  stars: number
  starShare: number
  medianStars: number
  plugins: number
  purposeBuiltShare: number
  /** Share of segment repositories at or above the catalog traction bar. */
  tractionRate: number
  /** Segment traction rate relative to the catalog traction rate. Above 1 means outsized pull. */
  demandIndex: number
  /** Share of repositories in this segment relative to an even split across segments. */
  supplyIndex: number
  demand: SegmentDemand
  exemplars: readonly RepoRef[]
}

export type RepoRef = {
  path: string
  url: string
  stars: number
  plugins: number
}

export type GrowthWindow = {
  label: string
  requestedDays: number
  actualDays: number
  from: string
  to: string
  startSize: number
  endSize: number
  added: number
  changePercent: number
  perDay: number
}

export type EcosystemGrowth = {
  asOf: string
  size: number
  snapshots: number
  windows: readonly GrowthWindow[]
  trend: GrowthTrend
  doublingDays: number | null
}

export type ConcentrationStats = {
  totalStars: number
  medianStars: number
  meanStars: number
  p90Stars: number
  /** Star count a repository must reach to count as having traction (the catalog 90th percentile). */
  tractionBar: number
  tractionRate: number
  topOnePercentStarShare: number
  topTenPercentStarShare: number
  giniCoefficient: number
  zeroStarShare: number
}

export type DepthBucket = {
  id: DepthBucketId
  label: string
  repos: number
  share: number
  plugins: number
}

export type EngagementStats = {
  totalForks: number
  totalSubscribers: number
  /** Watchers per 1,000 stars across the catalog: a coarse read on attention that converts to follow-through. */
  watchRatePerThousandStars: number
  forkRatePerThousandStars: number
}

export type IntentBreakdown = {
  intent: RepoIntent
  repos: number
  share: number
  stars: number
  starShare: number
}

export type DataHealth = {
  repos: number
  canonicalRepos: number
  duplicatePaths: number
  missingDescription: number
  unverifiedPluginCount: number
  zeroStar: number
  unclassifiedShare: number
  /** Unclassified share counting only repositories that actually have a description to classify. */
  describedUnclassifiedShare: number
}

export type MomentumEntry = RepoRef & {
  previousStars: number
  starDelta: number
  starDeltaPercent: number
  pluginDelta: number
  segment: MarketSegmentId
}

export type SegmentMomentum = {
  id: MarketSegmentId
  label: string
  repos: number
  previousRepos: number
  repoDelta: number
  starDelta: number
}

export type MomentumReport = {
  baseline: string
  baselineRepos: number
  currentRepos: number
  entrants: number
  exits: number
  netRepoChange: number
  starDelta: number
  pluginDelta: number
  topGainers: readonly MomentumEntry[]
  topBreakouts: readonly MomentumEntry[]
  topNewEntrants: readonly RepoRef[]
  segments: readonly SegmentMomentum[]
}

export type MarketAwarenessReport = {
  version: number
  generatedAt: string
  totals: {
    repos: number
    plugins: number
    stars: number
  }
  growth: EcosystemGrowth
  concentration: ConcentrationStats
  engagement: EngagementStats
  intent: readonly IntentBreakdown[]
  segments: readonly SegmentInsight[]
  depth: readonly DepthBucket[]
  leaders: readonly RepoRef[]
  dataHealth: DataHealth
  momentum: MomentumReport | null
}

export type MarketAwarenessInput = {
  repos: readonly Repo[]
  stats: readonly StatsItem[]
  baselineRepos?: readonly Repo[]
  baselineLabel?: string
  topCount?: number
  generatedAt?: Date
}

const DEPTH_BUCKETS: readonly { id: DepthBucketId; label: string; test: (pluginCount: number | null) => boolean }[] = [
  { id: 'unverified', label: 'Plugin count unverified', test: (count) => count === null },
  { id: 'none', label: 'No plugins detected', test: (count) => count === 0 },
  { id: 'single', label: 'Single plugin', test: (count) => count === 1 },
  { id: 'small-suite', label: 'Small suite (2-9)', test: (count) => count !== null && count >= 2 && count <= 9 },
  { id: 'large-suite', label: 'Large suite (10-49)', test: (count) => count !== null && count >= 10 && count <= 49 },
  { id: 'mega-marketplace', label: 'Mega marketplace (50+)', test: (count) => count !== null && count >= 50 },
]

export function classifySegment(repo: Repo): MarketSegmentId {
  const haystack = buildHaystack(repo)
  if (!haystack) {
    return 'unclassified'
  }

  let bestId: MarketSegmentId = 'unclassified'
  let bestScore = 0
  for (const definition of SEGMENT_DEFINITIONS) {
    let score = 0
    for (const pattern of definition.patterns) {
      if (pattern.test(haystack)) {
        score += 1
      }
    }
    if (score > bestScore) {
      bestScore = score
      bestId = definition.id
    }
  }

  return bestId
}

export function classifyIntent(repo: Repo): RepoIntent {
  const haystack = buildHaystack(repo)
  if (!haystack) {
    return 'incidental'
  }
  if (PURPOSE_BUILT_PATTERNS.some((pattern) => pattern.test(haystack))) {
    return 'purpose-built'
  }
  if (ADJACENT_PATTERNS.some((pattern) => pattern.test(haystack))) {
    return 'adjacent'
  }
  return 'incidental'
}

export function getSegmentLabel(id: MarketSegmentId): string {
  return SEGMENT_DEFINITIONS.find((definition) => definition.id === id)?.label ?? 'Unclassified'
}

export function buildMarketAwarenessReport(input: MarketAwarenessInput): MarketAwarenessReport {
  const topCount = input.topCount ?? 10
  const canonical = getCanonicalRepos(input.repos)
  const duplicatePaths = input.repos.filter((repo) => repo.owner && repo.repo_name).length - canonical.length
  const stars = canonical.map((repo) => repo.stargazers_count ?? 0)
  const totalStars = sum(stars)
  const totalPlugins = sum(canonical.map((repo) => repo.plugins_count ?? 0))
  const concentration = buildConcentration(stars)

  const segments = buildSegments(canonical, {
    totalStars,
    tractionBar: concentration.tractionBar,
    tractionRate: concentration.tractionRate,
    topCount,
  })
  const unclassified = canonical.filter((repo) => classifySegment(repo) === 'unclassified')
  const described = canonical.filter((repo) => Boolean(repo.description?.trim()))

  return {
    version: MARKET_AWARENESS_VERSION,
    generatedAt: (input.generatedAt ?? new Date()).toISOString(),
    totals: { repos: canonical.length, plugins: totalPlugins, stars: totalStars },
    growth: buildGrowth(input.stats),
    concentration,
    engagement: buildEngagement(canonical, totalStars),
    intent: buildIntent(canonical, totalStars),
    segments,
    depth: buildDepth(canonical),
    leaders: [...canonical]
      .sort((left, right) => (right.stargazers_count ?? 0) - (left.stargazers_count ?? 0))
      .slice(0, topCount)
      .map(toRepoRef),
    dataHealth: {
      repos: input.repos.length,
      canonicalRepos: canonical.length,
      duplicatePaths,
      missingDescription: canonical.filter((repo) => !repo.description?.trim()).length,
      unverifiedPluginCount: canonical.filter((repo) => repo.plugins_count === null).length,
      zeroStar: canonical.filter((repo) => (repo.stargazers_count ?? 0) === 0).length,
      unclassifiedShare: round(ratio(unclassified.length, canonical.length) * 100, 1),
      describedUnclassifiedShare: round(
        ratio(unclassified.filter((repo) => Boolean(repo.description?.trim())).length, described.length) * 100,
        1
      ),
    },
    momentum: input.baselineRepos ? buildMomentum(canonical, input.baselineRepos, input.baselineLabel ?? 'baseline', topCount) : null,
  }
}

function buildHaystack(repo: Repo): string {
  return `${repo.repo_name ?? ''} ${repo.description ?? ''}`.toLowerCase()
}

function getCanonicalRepos(repos: readonly Repo[]): Repo[] {
  const seen = new Set<string>()
  return repos.filter((repo) => {
    if (!(repo.owner && repo.repo_name)) {
      return false
    }
    const key = `${repo.owner}/${repo.repo_name}`.toLowerCase()
    if (seen.has(key)) {
      return false
    }
    seen.add(key)
    return true
  })
}

function buildGrowth(stats: readonly StatsItem[]): EcosystemGrowth {
  const ordered = [...stats]
    .filter((entry) => Number.isFinite(new Date(entry.date).getTime()))
    .sort((left, right) => new Date(left.date).getTime() - new Date(right.date).getTime())
  const latest = ordered.at(-1)

  if (!latest) {
    return { asOf: 'unknown', size: 0, snapshots: 0, windows: [], trend: 'unknown', doublingDays: null }
  }

  const windows = [
    buildWindow(ordered, latest, 7, '7-day'),
    buildWindow(ordered, latest, 30, '30-day'),
    buildWindow(ordered, latest, 90, '90-day'),
  ].filter((window): window is GrowthWindow => window !== null)

  return {
    asOf: latest.date,
    size: latest.size,
    snapshots: ordered.length,
    windows,
    trend: buildTrend(ordered, latest),
    doublingDays: buildDoublingDays(windows),
  }
}

function buildWindow(ordered: readonly StatsItem[], latest: StatsItem, days: number, label: string): GrowthWindow | null {
  const start = findSnapshotBefore(ordered, latest, days)
  if (!start || start.date === latest.date) {
    return null
  }

  const actualDays = daysBetween(start.date, latest.date)
  if (actualDays <= 0) {
    return null
  }

  const added = latest.size - start.size
  return {
    label,
    requestedDays: days,
    actualDays: round(actualDays, 1),
    from: start.date,
    to: latest.date,
    startSize: start.size,
    endSize: latest.size,
    added,
    changePercent: round(ratio(added, start.size) * 100, 1),
    perDay: round(added / actualDays, 1),
  }
}

function findSnapshotBefore(ordered: readonly StatsItem[], latest: StatsItem, days: number): StatsItem | null {
  const cutoff = new Date(latest.date).getTime() - days * 86_400_000
  let candidate: StatsItem | null = null
  for (const entry of ordered) {
    if (new Date(entry.date).getTime() <= cutoff) {
      candidate = entry
    }
  }
  return candidate ?? ordered[0] ?? null
}

function buildTrend(ordered: readonly StatsItem[], latest: StatsItem): GrowthTrend {
  const recent = buildWindow(ordered, latest, 30, 'recent')
  if (!recent) {
    return 'unknown'
  }

  const priorAnchor = ordered.find((entry) => entry.date === recent.from)
  if (!priorAnchor) {
    return 'unknown'
  }

  const prior = buildWindow(ordered, priorAnchor, 30, 'prior')
  if (!prior || prior.perDay <= 0) {
    return 'unknown'
  }

  const change = (recent.perDay - prior.perDay) / prior.perDay
  if (change > 0.1) {
    return 'accelerating'
  }
  if (change < -0.1) {
    return 'cooling'
  }
  return 'steady'
}

function buildDoublingDays(windows: readonly GrowthWindow[]): number | null {
  const window = windows.find((entry) => entry.requestedDays === 90) ?? windows.at(-1)
  if (!window || window.startSize <= 0 || window.endSize <= window.startSize) {
    return null
  }

  const dailyRate = (window.endSize / window.startSize) ** (1 / window.actualDays) - 1
  if (dailyRate <= 0) {
    return null
  }

  return round(Math.log(2) / Math.log(1 + dailyRate), 1)
}

function buildConcentration(stars: readonly number[]): ConcentrationStats {
  const sorted = [...stars].sort((left, right) => left - right)
  const total = sum(sorted)
  const descending = [...sorted].reverse()
  const tractionBar = getTractionBar(sorted)

  return {
    totalStars: total,
    medianStars: median(sorted),
    meanStars: round(ratio(total, sorted.length), 1),
    p90Stars: percentile(sorted, 90),
    tractionBar,
    tractionRate: round(ratio(sorted.filter((value) => value >= tractionBar).length, sorted.length) * 100, 1),
    topOnePercentStarShare: round(topShare(descending, total, 0.01) * 100, 1),
    topTenPercentStarShare: round(topShare(descending, total, 0.1) * 100, 1),
    giniCoefficient: round(gini(sorted), 3),
    zeroStarShare: round(ratio(sorted.filter((value) => value === 0).length, sorted.length) * 100, 1),
  }
}

/**
 * The star count that separates repositories somebody noticed from the long tail.
 *
 * Half the catalog sits at zero stars, so the median cannot discriminate between segments. The
 * 90th percentile moves with the catalog instead of being hard-coded, and a floor of one star
 * keeps the bar meaningful if the distribution ever collapses.
 */
function getTractionBar(sortedAscending: readonly number[]): number {
  return Math.max(1, percentile(sortedAscending, 90))
}

function buildEngagement(repos: readonly Repo[], totalStars: number): EngagementStats {
  const totalForks = sum(repos.map((repo) => repo.forks_count ?? 0))
  const totalSubscribers = sum(repos.map((repo) => repo.subscribers_count ?? 0))

  return {
    totalForks,
    totalSubscribers,
    watchRatePerThousandStars: round(ratio(totalSubscribers, totalStars) * 1000, 1),
    forkRatePerThousandStars: round(ratio(totalForks, totalStars) * 1000, 1),
  }
}

function buildIntent(repos: readonly Repo[], totalStars: number): IntentBreakdown[] {
  const intents: RepoIntent[] = ['purpose-built', 'adjacent', 'incidental']
  const classified = repos.map((repo) => ({ repo, intent: classifyIntent(repo) }))

  return intents.map((intent) => {
    const matching = classified.filter((entry) => entry.intent === intent)
    const stars = sum(matching.map((entry) => entry.repo.stargazers_count ?? 0))
    return {
      intent,
      repos: matching.length,
      share: round(ratio(matching.length, repos.length) * 100, 1),
      stars,
      starShare: round(ratio(stars, totalStars) * 100, 1),
    }
  })
}

function buildSegments(
  repos: readonly Repo[],
  context: { totalStars: number; tractionBar: number; tractionRate: number; topCount: number }
): readonly SegmentInsight[] {
  const grouped = new Map<MarketSegmentId, Repo[]>()
  for (const repo of repos) {
    const id = classifySegment(repo)
    const bucket = grouped.get(id)
    if (bucket) {
      bucket.push(repo)
    } else {
      grouped.set(id, [repo])
    }
  }

  const classifiedShares = [...grouped.entries()]
    .filter(([id]) => id !== 'unclassified')
    .map(([, members]) => ratio(members.length, repos.length))
  const baselineShare = median(classifiedShares)

  return [...grouped.entries()]
    .map(([id, members]) => {
      const segmentStars = sum(members.map((repo) => repo.stargazers_count ?? 0))
      const segmentMedian = median(members.map((repo) => repo.stargazers_count ?? 0))
      const repoShare = ratio(members.length, repos.length)
      const withTraction = members.filter((repo) => (repo.stargazers_count ?? 0) >= context.tractionBar).length
      const tractionRate = round(ratio(withTraction, members.length) * 100, 1)
      const demandIndex = context.tractionRate > 0 ? round(tractionRate / context.tractionRate, 2) : 0
      const supplyIndex = baselineShare > 0 ? round(repoShare / baselineShare, 2) : 0

      return {
        id,
        label: getSegmentLabel(id),
        repos: members.length,
        repoShare: round(repoShare * 100, 1),
        stars: segmentStars,
        starShare: round(ratio(segmentStars, context.totalStars) * 100, 1),
        medianStars: segmentMedian,
        plugins: sum(members.map((repo) => repo.plugins_count ?? 0)),
        tractionRate,
        purposeBuiltShare: round(ratio(members.filter((repo) => classifyIntent(repo) === 'purpose-built').length, members.length) * 100, 1),
        demandIndex,
        supplyIndex,
        demand: getSegmentDemand(id, demandIndex, supplyIndex, members.length),
        exemplars: pickExemplars(members, Math.min(3, context.topCount)),
      }
    })
    .sort((left, right) => right.repos - left.repos)
}

/**
 * Picks the repositories that best represent a segment.
 *
 * Star rank alone would headline broad segments with general-purpose projects that merely match a
 * keyword, so purpose-built repositories are ranked first and the rest only fill the remainder.
 */
function pickExemplars(members: readonly Repo[], count: number): readonly RepoRef[] {
  const byStars = [...members].sort((left, right) => (right.stargazers_count ?? 0) - (left.stargazers_count ?? 0))
  const purposeBuilt = byStars.filter((repo) => classifyIntent(repo) === 'purpose-built')
  const remainder = byStars.filter((repo) => classifyIntent(repo) !== 'purpose-built')

  return [...purposeBuilt, ...remainder].slice(0, count).map(toRepoRef)
}

function getSegmentDemand(id: MarketSegmentId, demandIndex: number, supplyIndex: number, repoCount: number): SegmentDemand {
  if (id === 'unclassified' || repoCount < SEGMENT_RATING_MINIMUM_REPOS) {
    return 'unrated'
  }
  if (demandIndex >= 1.2 && supplyIndex <= 1) {
    return 'underserved'
  }
  if (supplyIndex >= 1.2 && demandIndex <= 1.2) {
    return 'crowded'
  }
  return 'balanced'
}

function buildDepth(repos: readonly Repo[]): readonly DepthBucket[] {
  return DEPTH_BUCKETS.map((bucket) => {
    const members = repos.filter((repo) => bucket.test(repo.plugins_count))
    return {
      id: bucket.id,
      label: bucket.label,
      repos: members.length,
      share: round(ratio(members.length, repos.length) * 100, 1),
      plugins: sum(members.map((repo) => repo.plugins_count ?? 0)),
    }
  })
}

function buildMomentum(current: readonly Repo[], baseline: readonly Repo[], baselineLabel: string, topCount: number): MomentumReport {
  const baselineCanonical = getCanonicalRepos(baseline)
  const baselineByPath = new Map(baselineCanonical.map((repo) => [repoPath(repo).toLowerCase(), repo]))
  const currentPaths = new Set(current.map((repo) => repoPath(repo).toLowerCase()))

  const tracked: MomentumEntry[] = []
  const entrants: RepoRef[] = []

  for (const repo of current) {
    const previous = baselineByPath.get(repoPath(repo).toLowerCase())
    if (!previous) {
      entrants.push(toRepoRef(repo))
      continue
    }

    const previousStars = previous.stargazers_count ?? 0
    const starDelta = (repo.stargazers_count ?? 0) - previousStars
    tracked.push({
      ...toRepoRef(repo),
      previousStars,
      starDelta,
      starDeltaPercent: round(ratio(starDelta, previousStars) * 100, 1),
      pluginDelta: (repo.plugins_count ?? 0) - (previous.plugins_count ?? 0),
      segment: classifySegment(repo),
    })
  }

  const currentStars = sum(current.map((repo) => repo.stargazers_count ?? 0))
  const baselineStars = sum(baselineCanonical.map((repo) => repo.stargazers_count ?? 0))

  return {
    baseline: baselineLabel,
    baselineRepos: baselineCanonical.length,
    currentRepos: current.length,
    entrants: entrants.length,
    exits: baselineCanonical.filter((repo) => !currentPaths.has(repoPath(repo).toLowerCase())).length,
    netRepoChange: current.length - baselineCanonical.length,
    starDelta: currentStars - baselineStars,
    pluginDelta: sum(current.map((repo) => repo.plugins_count ?? 0)) - sum(baselineCanonical.map((repo) => repo.plugins_count ?? 0)),
    topGainers: [...tracked].sort((left, right) => right.starDelta - left.starDelta).slice(0, topCount),
    topBreakouts: tracked
      .filter((entry) => entry.previousStars >= BREAKOUT_MINIMUM_STARS && entry.starDelta > 0)
      .sort((left, right) => right.starDeltaPercent - left.starDeltaPercent)
      .slice(0, topCount),
    topNewEntrants: [...entrants].sort((left, right) => right.stars - left.stars).slice(0, topCount),
    segments: buildSegmentMomentum(current, baselineCanonical),
  }
}

function buildSegmentMomentum(current: readonly Repo[], baseline: readonly Repo[]): readonly SegmentMomentum[] {
  const currentBySegment = countBySegment(current)
  const baselineBySegment = countBySegment(baseline)
  const ids = new Set<MarketSegmentId>([...currentBySegment.keys(), ...baselineBySegment.keys()])

  return [...ids]
    .map((id) => {
      const now = currentBySegment.get(id) ?? { repos: 0, stars: 0 }
      const before = baselineBySegment.get(id) ?? { repos: 0, stars: 0 }
      return {
        id,
        label: getSegmentLabel(id),
        repos: now.repos,
        previousRepos: before.repos,
        repoDelta: now.repos - before.repos,
        starDelta: now.stars - before.stars,
      }
    })
    .sort((left, right) => right.repoDelta - left.repoDelta)
}

function countBySegment(repos: readonly Repo[]): Map<MarketSegmentId, { repos: number; stars: number }> {
  const counts = new Map<MarketSegmentId, { repos: number; stars: number }>()
  for (const repo of repos) {
    const id = classifySegment(repo)
    const entry = counts.get(id) ?? { repos: 0, stars: 0 }
    entry.repos += 1
    entry.stars += repo.stargazers_count ?? 0
    counts.set(id, entry)
  }
  return counts
}

function toRepoRef(repo: Repo): RepoRef {
  return {
    path: repoPath(repo),
    url: repo.html_url,
    stars: repo.stargazers_count ?? 0,
    plugins: repo.plugins_count ?? 0,
  }
}

function repoPath(repo: Repo): string {
  return `${repo.owner ?? '?'}/${repo.repo_name ?? '?'}`
}

function sum(values: readonly number[]): number {
  return values.reduce((total, value) => total + value, 0)
}

function ratio(numerator: number, denominator: number): number {
  return denominator === 0 ? 0 : numerator / denominator
}

function median(values: readonly number[]): number {
  if (values.length === 0) {
    return 0
  }
  const sorted = [...values].sort((left, right) => left - right)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 0 ? (sorted[middle - 1] + sorted[middle]) / 2 : sorted[middle]
}

function percentile(sortedAscending: readonly number[], target: number): number {
  if (sortedAscending.length === 0) {
    return 0
  }
  const index = Math.min(sortedAscending.length - 1, Math.max(0, Math.ceil((target / 100) * sortedAscending.length) - 1))
  return sortedAscending[index]
}

function topShare(sortedDescending: readonly number[], total: number, fraction: number): number {
  if (sortedDescending.length === 0 || total === 0) {
    return 0
  }
  const take = Math.max(1, Math.round(sortedDescending.length * fraction))
  return ratio(sum(sortedDescending.slice(0, take)), total)
}

function gini(sortedAscending: readonly number[]): number {
  const count = sortedAscending.length
  const total = sum(sortedAscending)
  if (count === 0 || total === 0) {
    return 0
  }

  let weighted = 0
  for (const [index, value] of sortedAscending.entries()) {
    weighted += (index + 1) * value
  }

  return (2 * weighted) / (count * total) - (count + 1) / count
}

function daysBetween(from: string, to: string): number {
  return (new Date(to).getTime() - new Date(from).getTime()) / 86_400_000
}

function round(value: number, decimals: number): number {
  if (!Number.isFinite(value)) {
    return 0
  }
  const factor = 10 ** decimals
  return Math.round(value * factor) / factor
}
