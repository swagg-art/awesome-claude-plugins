# Claude Code plugin market awareness (v3)

Generated 2026-09-20 from the committed catalog snapshot.

| Measure | Value |
| --- | --- |
| Repositories tracked | 35,552 |
| Plugins detected | 93,444 |
| Combined stars | 7,097,679 |
| Catalog snapshot date | 2026-08-27 |

## Ecosystem growth

| Window | Actual span | Added | Change | Per day |
| --- | --- | --- | --- | --- |
| 7-day | 10.2 d | +1,886 | 5.6% | 185.1 |
| 30-day | 41.4 d | +7,791 | 28% | 188.2 |
| 90-day | 90.7 d | +16,547 | 86.9% | 182.5 |

**Trend: steady** — the intake rate is holding within 10% of the previous 30 days.

At the trailing 90-day compound rate the catalog doubles in about 100.5 days.

## Attention concentration

| Measure | Value |
| --- | --- |
| Median stars | 1 |
| Mean stars | 199.6 |
| 90th percentile stars | 26 |
| Traction bar (stars) | 26 |
| Repositories at or above the bar | 10.1% |
| Stars held by the top 1% | 90.1% |
| Stars held by the top 10% | 99% |
| Gini coefficient (stars) | 0.988 |
| Repositories with zero stars | 49.6% |
| Watchers per 1,000 stars | 6.8 |
| Forks per 1,000 stars | 110.9 |

Attention is extremely concentrated: a handful of repositories absorb nearly all of it, so a new entrant competes for a very thin tail.

## Who is actually building for this market

| Cohort | Repositories | Share | Star share |
| --- | --- | --- | --- |
| Purpose-built for the agent ecosystem | 26,828 | 75.5% | 69.7% |
| Adjacent AI tooling | 2,246 | 6.3% | 15.6% |
| Incidental (general project shipping a manifest) | 6,478 | 18.2% | 14.7% |

Cohorts are inferred from repository names and descriptions, so treat them as a directional read rather than a census.

## Segments

| Segment | Repos | Share | Traction | Plugins | Purpose-built | Demand | Supply | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Unclassified | 10,621 | 29.9% | 6.8% | 26,668 | 49.2% | 0.67x | 13.21x | unrated |
| Skill & prompt libraries | 8,967 | 25.2% | 9.1% | 33,841 | 98.5% | 0.9x | 11.15x | crowded |
| MCP servers & integrations | 2,073 | 5.8% | 12.1% | 5,338 | 97% | 1.2x | 2.58x | crowded |
| Orchestration & multi-agent | 1,956 | 5.5% | 10% | 5,230 | 83.1% | 0.99x | 2.43x | crowded |
| Developer tooling | 1,584 | 4.5% | 11.9% | 4,442 | 74.2% | 1.18x | 1.97x | crowded |
| Productivity & project management | 1,341 | 3.8% | 10.4% | 2,093 | 80.2% | 1.03x | 1.67x | crowded |
| Code review, testing & quality | 1,187 | 3.3% | 12% | 2,151 | 79.7% | 1.19x | 1.48x | crowded |
| DevOps, cloud & infrastructure | 945 | 2.7% | 12.6% | 1,639 | 77.2% | 1.25x | 1.18x | balanced |
| Docs & writing | 895 | 2.5% | 13.1% | 1,266 | 75.4% | 1.3x | 1.11x | balanced |
| Research & learning | 888 | 2.5% | 13.7% | 1,624 | 81.3% | 1.36x | 1.1x | balanced |
| Memory & context engineering | 804 | 2.3% | 15.3% | 1,081 | 79.5% | 1.51x | 1x | underserved |
| Media & creative generation | 800 | 2.3% | 14% | 1,083 | 80% | 1.39x | 1x | underserved |
| Agent frameworks & harnesses | 723 | 2% | 16.5% | 1,173 | 50.2% | 1.63x | 0.9x | underserved |
| Data & analytics | 583 | 1.6% | 14.4% | 892 | 70.8% | 1.43x | 0.73x | underserved |
| Security & compliance | 513 | 1.4% | 17.7% | 1,783 | 85.4% | 1.75x | 0.64x | underserved |
| Design & UI | 438 | 1.2% | 15.5% | 754 | 76.7% | 1.53x | 0.54x | underserved |
| Browser & automation | 378 | 1.1% | 12.7% | 501 | 79.1% | 1.26x | 0.47x | underserved |
| SEO, marketing & growth | 368 | 1% | 18.5% | 629 | 85.3% | 1.83x | 0.46x | underserved |
| Finance & trading | 298 | 0.8% | 11.4% | 987 | 76.5% | 1.13x | 0.37x | balanced |
| Slides & presentations | 190 | 0.5% | 23.7% | 269 | 75.3% | 2.35x | 0.24x | underserved |

Traction is the share of a segment at or above the catalog traction bar. Demand is that share against the catalog-wide rate;
supply is the segment repository share against the median classified segment. Segments too small to read are left unrated.

## Where the room is

Segments converting to traction above the catalog rate while carrying below-baseline supply:

- **Memory & context engineering** — 1.51x demand on 1x supply. Bellwethers: thedotmack/claude-mem, mem0ai/mem0, volcengine/OpenViking.
- **Media & creative generation** — 1.39x demand on 1x supply. Bellwethers: mvanhorn/last30days-skill, bradautomates/claude-video, ConardLi/garden-skills.
- **Agent frameworks & harnesses** — 1.63x demand on 0.9x supply. Bellwethers: mukul975/Anthropic-Cybersecurity-Skills, QwenLM/Qwen-MM-Plugins, modelcontextprotocol/ext-apps.
- **Data & analytics** — 1.43x demand on 0.73x supply. Bellwethers: InsForge/InsForge, repowise-dev/repowise, mvanhorn/cli-printing-press.
- **Security & compliance** — 1.75x demand on 0.64x supply. Bellwethers: affaan-m/ECC, alirezarezvani/claude-skills, promptfoo/promptfoo.
- **Design & UI** — 1.53x demand on 0.54x supply. Bellwethers: nextlevelbuilder/ui-ux-pro-max-skill, cathrynlavery/diagram-design, oso95/scroll-world.
- **Browser & automation** — 1.26x demand on 0.47x supply. Bellwethers: ChromeDevTools/chrome-devtools-mcp, vercel-labs/agent-browser, citrolabs/ego-lite.
- **SEO, marketing & growth** — 1.83x demand on 0.46x supply. Bellwethers: coreyhaines31/marketingskills, AgriciDaniel/claude-seo, AgriciDaniel/claude-ads.
- **Slides & presentations** — 2.35x demand on 0.24x supply. Bellwethers: nexu-io/open-design, zarazhangrui/frontend-slides, nicobailon/visual-explainer.

Segments carrying above-baseline supply without the matching pull:

- **Skill & prompt libraries** — 11.15x supply on 0.9x demand.
- **MCP servers & integrations** — 2.58x supply on 1.2x demand.
- **Orchestration & multi-agent** — 2.43x supply on 0.99x demand.
- **Developer tooling** — 1.97x supply on 1.18x demand.
- **Productivity & project management** — 1.67x supply on 1.03x demand.
- **Code review, testing & quality** — 1.48x supply on 1.19x demand.

## Marketplace depth

| Shape | Repos | Share | Plugins |
| --- | --- | --- | --- |
| Plugin count unverified | 297 | 0.8% | 0 |
| No plugins detected | 0 | 0% | 0 |
| Single plugin | 28,368 | 79.8% | 28,368 |
| Small suite (2-9) | 5,506 | 15.5% | 20,887 |
| Large suite (10-49) | 1,198 | 3.4% | 21,288 |
| Mega marketplace (50+) | 183 | 0.5% | 22,901 |

## Attention leaders

| Repository | Stars | Plugins |
| --- | --- | --- |
| [obra/superpowers](https://github.com/obra/superpowers) | 277,576 | 1 |
| [affaan-m/ECC](https://github.com/affaan-m/ECC) | 243,315 | 1 |
| [mattpocock/skills](https://github.com/mattpocock/skills) | 237,750 | 1 |
| [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 207,396 | 1 |
| [anthropics/skills](https://github.com/anthropics/skills) | 171,612 | 5 |
| [f/prompts.chat](https://github.com/f/prompts.chat) | 167,904 | 1 |
| [anthropics/claude-code](https://github.com/anthropics/claude-code) | 143,025 | 13 |
| [vercel/next.js](https://github.com/vercel/next.js) | 141,939 | 1 |
| [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 120,961 | 1 |
| [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 111,940 | 1 |

## Momentum

Compared against `1e10d4e`.

| Measure | Value |
| --- | --- |
| Repositories then | 28,165 |
| Repositories now | 35,552 |
| Net change | +7,387 |
| New entrants | 7,857 |
| Dropped out | 470 |
| Star change | +956,282 |
| Plugin change | +19,132 |

### Biggest star gains

| Repository | Stars | Gain | Change |
| --- | --- | --- | --- |
| [mattpocock/skills](https://github.com/mattpocock/skills) | 237,750 | +43,588 | 22.4% |
| [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) | 26,986 | +24,089 | 831.5% |
| [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | 111,940 | +20,590 | 22.5% |
| [obra/superpowers](https://github.com/obra/superpowers) | 277,576 | +14,886 | 5.7% |
| [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 80,855 | +12,027 | 17.5% |
| [ayghri/i-have-adhd](https://github.com/ayghri/i-have-adhd) | 24,451 | +11,363 | 86.8% |
| [freestylefly/awesome-gpt-image-2](https://github.com/freestylefly/awesome-gpt-image-2) | 20,086 | +11,218 | 126.5% |
| [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | 62,608 | +10,349 | 19.8% |
| [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) | 207,396 | +10,047 | 5.1% |
| [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 120,961 | +9,798 | 8.8% |

### Fastest climbers

| Repository | Then | Now | Change |
| --- | --- | --- | --- |
| [cathrynlavery/diagram-design](https://github.com/cathrynlavery/diagram-design) | 2,897 | 26,986 | 831.5% |
| [anthropics/claude-plugins-community](https://github.com/anthropics/claude-plugins-community) | 324 | 1,864 | 475.3% |
| [humanlayer/skills](https://github.com/humanlayer/skills) | 105 | 499 | 375.2% |
| [coji/natural-japanese](https://github.com/coji/natural-japanese) | 132 | 511 | 287.1% |
| [danielealbano/android-remote-control-mcp](https://github.com/danielealbano/android-remote-control-mcp) | 174 | 573 | 229.3% |
| [ifixai-ai/iFixAi](https://github.com/ifixai-ai/iFixAi) | 3,456 | 11,176 | 223.4% |
| [coreyhaines31/makerskills](https://github.com/coreyhaines31/makerskills) | 231 | 681 | 194.8% |
| [devcxl/mattpocock-skills-zh](https://github.com/devcxl/mattpocock-skills-zh) | 111 | 269 | 142.3% |
| [WorldFlowAI/everything-claude-code](https://github.com/WorldFlowAI/everything-claude-code) | 730 | 1,723 | 136% |
| [citrolabs/ego-lite](https://github.com/citrolabs/ego-lite) | 5,817 | 13,645 | 134.6% |

### Notable new entrants

| Repository | Stars | Plugins |
| --- | --- | --- |
| [storybookjs/storybook](https://github.com/storybookjs/storybook) | 90,940 | 1 |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | 43,756 | 1 |
| [huggingface/diffusers](https://github.com/huggingface/diffusers) | 34,385 | 1 |
| [garrytan/gbrain](https://github.com/garrytan/gbrain) | 29,142 | 3 |
| [clockworklabs/SpacetimeDB](https://github.com/clockworklabs/SpacetimeDB) | 25,075 | 1 |
| [google/skills](https://github.com/google/skills) | 18,711 | 23 |
| [guillaumemeyer/watermarks-remover](https://github.com/guillaumemeyer/watermarks-remover) | 18,536 | 1 |
| [every-app/open-seo](https://github.com/every-app/open-seo) | 13,595 | 1 |
| [xberg-io/xberg](https://github.com/xberg-io/xberg) | 9,221 | 1 |
| [fastrepl/anarlog](https://github.com/fastrepl/anarlog) | 9,181 | 1 |

### Segment intake

| Segment | Then | Now | Net repos | Star change |
| --- | --- | --- | --- | --- |
| Unclassified | 8,523 | 10,621 | +2,098 | +125,121 |
| Skill & prompt libraries | 7,267 | 8,967 | +1,700 | +273,199 |
| MCP servers & integrations | 1,519 | 2,073 | +554 | +31,457 |
| Developer tooling | 1,215 | 1,584 | +369 | -12,021 |
| Orchestration & multi-agent | 1,619 | 1,956 | +337 | +23,191 |
| Productivity & project management | 1,077 | 1,341 | +264 | +15,373 |
| Code review, testing & quality | 927 | 1,187 | +260 | +103,393 |
| Docs & writing | 664 | 895 | +231 | +32,872 |
| DevOps, cloud & infrastructure | 716 | 945 | +229 | +13,102 |
| Media & creative generation | 593 | 800 | +207 | +64,115 |

## Data health

| Check | Value |
| --- | --- |
| Raw records | 35,588 |
| Canonical records analysed | 35,552 |
| Case-duplicate paths skipped | 36 |
| Missing description | 9,247 |
| Plugin count unverified | 297 |
| Zero-star repositories | 17,624 |
| Unclassified by segment | 29.9% |
| Unclassified despite having a description | 18.5% |

Repositories with no description can only be matched on their name, so the second figure is the real taxonomy gap:
when it climbs, the segment patterns need extending rather than the market lacking a theme.

