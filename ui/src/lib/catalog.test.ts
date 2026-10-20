/** biome-ignore-all lint/style/useNamingConvention: Test fixtures mirror catalog field names. */

import { describe, expect, it } from 'vitest'
import { type Repo, RepoSchema } from '../schemas/repo.schema.ts'
import { type CatalogRepo, searchCatalogRepos, searchRepos } from './catalog.ts'

type RepoOverrides = Partial<Omit<Repo, 'owner' | 'repo_name' | 'html_url' | 'owner_url'>>

let nextRepoId = 1

/**
 * Builds a fixture through `RepoSchema` so these tests fail if the catalog shape changes, and so
 * the canonical `html_url` / `owner_url` invariants are derived rather than restated.
 */
function makeRepo(owner: string, repoName: string, overrides: RepoOverrides = {}): CatalogRepo {
  return RepoSchema.parse({
    html_url: `https://github.com/${owner}/${repoName}`,
    owner,
    owner_url: `https://github.com/${owner}`,
    repo_name: repoName,
    stargazers_count: 0,
    forks_count: 0,
    subscribers_count: 0,
    description: null,
    plugins_count: 0,
    id: nextRepoId++,
    ...overrides,
  }) as CatalogRepo
}

describe('searchRepos', () => {
  it('keeps review-needed canonical records discoverable', () => {
    // A null plugin count makes a repository non-indexable, but search must still surface it.
    const reviewNeeded = makeRepo('todorkolev', 'lean-playground', {
      description: 'Containerized workspace for QuantConnect Lean',
      plugins_count: null,
    })
    const unrelated = makeRepo('other-owner', 'unrelated-project', { description: 'Something else entirely' })

    const results = searchRepos([reviewNeeded, unrelated], 'lean-playground', 'stars-desc')

    expect(results.repos).toEqual([reviewNeeded])
  })

  it('counts a null plugin count as zero rather than dropping the record', () => {
    const repos = [makeRepo('owner', 'no-count', { plugins_count: null }), makeRepo('owner', 'two-plugins', { plugins_count: 2 })]

    const results = searchRepos(repos, '', 'stars-desc')

    expect(results.total).toBe(2)
    expect(results.pluginsCount).toBe(2)
  })

  it('paginates without dropping or repeating records', () => {
    const repos = [50, 40, 30, 20, 10].map((stars) =>
      makeRepo('owner', `repo-${stars}`, { description: 'A described repository', stargazers_count: stars })
    )

    const pages = [0, 1, 2].map((page) => searchRepos(repos, '', 'stars-desc', page, 2))

    expect(pages.map((page) => page.repos.length)).toEqual([2, 2, 1])
    expect(pages.map((page) => page.hasMore)).toEqual([true, true, false])
    expect(pages.every((page) => page.total === 5)).toBe(true)
    expect(pages.flatMap((page) => page.repos)).toEqual(repos)
  })

  it('serves nothing past the last page', () => {
    const repos = [makeRepo('owner', 'only-repo')]

    expect(searchRepos(repos, '', 'stars-desc', 1, 24).repos).toEqual([])
  })

  it('orders by fork count when forks-desc is selected', () => {
    const fewForks = makeRepo('owner', 'few-forks', { forks_count: 3, stargazers_count: 9_000 })
    const manyForks = makeRepo('owner', 'many-forks', { forks_count: 300, stargazers_count: 1 })

    const results = searchRepos([fewForks, manyForks], '', 'forks-desc')

    expect(results.repos).toEqual([manyForks, fewForks])
  })

  it('weights plugin count by stars so a popular single-plugin repository outranks an unknown multi-plugin one', () => {
    const unknownWithTwoPlugins = makeRepo('owner', 'two-plugins', { plugins_count: 2, stargazers_count: 0 })
    const popularWithOnePlugin = makeRepo('owner', 'one-plugin', { plugins_count: 1, stargazers_count: 10_000 })

    const results = searchRepos([unknownWithTwoPlugins, popularWithOnePlugin], '', 'plugins-desc')

    expect(results.repos).toEqual([popularWithOnePlugin, unknownWithTwoPlugins])
  })

  it('ranks described repositories above undescribed ones in the default sort', () => {
    const undescribedButPopular = makeRepo('owner', 'popular-no-description', { stargazers_count: 10_000 })
    const describedButQuiet = makeRepo('owner', 'quiet-with-description', { description: 'Explains what it does', stargazers_count: 1 })

    const results = searchRepos([undescribedButPopular, describedButQuiet], '', 'stars-desc')

    expect(results.repos).toEqual([describedButQuiet, undescribedButPopular])
  })
})

describe('searchCatalogRepos', () => {
  it('searches the checked-in catalog', () => {
    const results = searchCatalogRepos('', 'stars-desc')

    expect(results.total).toBeGreaterThan(0)
    expect(results.repos.length).toBeGreaterThan(0)
    expect(results.repos.length).toBeLessThanOrEqual(results.total)
  })
})
