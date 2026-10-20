/** biome-ignore-all lint/style/useNamingConvention: <n8n> */
import type { MetadataRoute } from 'next'
import { getCanonicalCatalogRepos, getCatalogLastModified, getIndexableCatalogRepos, getRepoCanonicalPath } from '../lib/catalog.ts'
import { CATALOG_PAGE_SIZE } from '../lib/catalogPagination.ts'
import { BASE_URL } from '../lib/constants.ts'

export default function sitemap(): MetadataRoute.Sitemap {
  const catalogLastModified = getCatalogLastModified()
  const canonicalCatalogRepos = getCanonicalCatalogRepos()
  const indexableCatalogRepos = getIndexableCatalogRepos()
  /**
   * `/browse/[page]` paginates every canonical repository, so the sitemap has to span that range.
   * Counting the narrower indexable subset instead left the tail of the pagination — pages that
   * render repositories and answer 200 — out of the sitemap entirely.
   */
  const totalBrowsePages = Math.ceil(canonicalCatalogRepos.length / CATALOG_PAGE_SIZE)

  const indexableRepoSet = new Set(indexableCatalogRepos)
  const repoUrls: MetadataRoute.Sitemap = canonicalCatalogRepos
    .filter((repo) => indexableRepoSet.has(repo))
    .map((repo) => ({
      url: `${BASE_URL}/${getRepoCanonicalPath(repo)}`,
    }))
  const browseUrls: MetadataRoute.Sitemap = Array.from({ length: Math.max(totalBrowsePages - 1, 0) }, (_, index) => ({
    url: `${BASE_URL}/browse/${index + 2}`,
    lastModified: catalogLastModified,
  }))

  return [
    {
      url: `${BASE_URL}/`,
      lastModified: catalogLastModified,
    },
    {
      url: `${BASE_URL}/stats`,
      lastModified: catalogLastModified,
    },
    {
      url: `${BASE_URL}/about`,
    },
    {
      url: `${BASE_URL}/privacy`,
    },
    ...browseUrls,
    ...repoUrls,
  ]
}
