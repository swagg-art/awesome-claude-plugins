import { describe, expect, it } from 'vitest'
import { searchCatalogRepos } from '../lib/catalog.ts'
import { CATALOG_PAGE_SIZE } from '../lib/catalogPagination.ts'
import { BASE_URL } from '../lib/constants.ts'
import sitemap from './sitemap.ts'

const BROWSE_PREFIX = `${BASE_URL}/browse/`

function getLastServedBrowsePage(): number {
  return Math.ceil(searchCatalogRepos('', 'stars-desc').total / CATALOG_PAGE_SIZE)
}

function getListedBrowsePages(): number[] {
  return sitemap()
    .map((entry) => entry.url)
    .filter((url) => url.startsWith(BROWSE_PREFIX))
    .map((url) => Number(url.slice(BROWSE_PREFIX.length)))
    .filter((page) => Number.isInteger(page))
}

describe('sitemap', () => {
  /**
   * Regression guard: the browse-page count was derived from the indexable subset while
   * `/browse/[page]` paginates every canonical repository, so the tail of the pagination answered
   * 200 while never appearing in the sitemap.
   */
  it('lists every browse page that serves repositories', () => {
    const listedBrowsePages = getListedBrowsePages()
    const lastServedPage = getLastServedBrowsePage()

    // `/browse/1` permanently redirects to `/`, so the listed range starts at page 2.
    expect(Math.min(...listedBrowsePages)).toBe(2)
    expect(Math.max(...listedBrowsePages)).toBe(lastServedPage)
    expect(listedBrowsePages).toHaveLength(lastServedPage - 1)
  })

  it('does not list a browse page beyond the served range', () => {
    const lastServedPage = getLastServedBrowsePage()

    expect(searchCatalogRepos('', 'stars-desc', lastServedPage - 1).repos).not.toHaveLength(0)
    expect(searchCatalogRepos('', 'stars-desc', lastServedPage).repos).toHaveLength(0)
  })

  it('includes the catalog entry points', () => {
    const urls = sitemap().map((entry) => entry.url)

    expect(urls).toEqual(expect.arrayContaining([`${BASE_URL}/`, `${BASE_URL}/stats`, `${BASE_URL}/about`, `${BASE_URL}/privacy`]))
  })
})
