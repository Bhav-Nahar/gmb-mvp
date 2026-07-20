import type { MetadataRoute } from 'next'
import { listPseoPages, pseoPath, industryHubPath, rootHubPath } from '@/lib/pseo'
import {
  listLpseoPages, lpseoPath,
  industryHubPath as lpseoIndustryHubPath, rootHubPath as lpseoRootHubPath,
} from '@/lib/lpseo'
import { FEATURES } from '@/lib/features'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

// Rendered per request: must include every published pSEO page, and the backend
// isn't reachable at image-build time (a static prerender would bake in an empty
// sitemap). Search engines fetch this only periodically, so cost is negligible.
export const dynamic = 'force-dynamic'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/pricing`, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${SITE_URL}/google-business-profile-management`, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${SITE_URL}/features`, changeFrequency: 'weekly', priority: 0.7 },
    ...FEATURES.map((f) => ({ url: `${SITE_URL}/features/${f.slug}`, changeFrequency: 'monthly' as const, priority: 0.7 })),
    { url: `${SITE_URL}/contact`, changeFrequency: 'monthly', priority: 0.3 },
    { url: `${SITE_URL}/privacy`, changeFrequency: 'yearly', priority: 0.1 },
    { url: `${SITE_URL}/terms`, changeFrequency: 'yearly', priority: 0.1 },
    { url: `${SITE_URL}/refund`, changeFrequency: 'yearly', priority: 0.1 },
  ]

  const pseo = await listPseoPages() // published + indexable only

  // Per-locale root hub + per-(locale, industry) hub + every leaf, all locale-prefixed.
  const rootHubs = new Set<string>()          // locale
  const industryHubs = new Set<string>()      // `${locale}|${industrySlug}`
  for (const p of pseo) {
    rootHubs.add(p.locale)
    industryHubs.add(`${p.locale}|${p.industry_slug}`)
  }

  const hubRoutes: MetadataRoute.Sitemap = [
    ...Array.from(rootHubs).map((locale) => ({
      url: `${SITE_URL}${rootHubPath(locale)}`, changeFrequency: 'weekly' as const, priority: 0.6,
    })),
    ...Array.from(industryHubs).map((key) => {
      const [locale, industry] = key.split('|')
      return { url: `${SITE_URL}${industryHubPath(locale, industry)}`, changeFrequency: 'weekly' as const, priority: 0.6 }
    }),
  ]

  const leafRoutes: MetadataRoute.Sitemap = pseo.map((p) => ({
    url: `${SITE_URL}${pseoPath(p.locale, p.slug)}`,
    lastModified: p.updated_at ? new Date(p.updated_at) : undefined,
    changeFrequency: 'monthly',
    priority: 0.7,
  }))

  // Local-SEO pages (/local-seo-services) — same hub + leaf shape as pSEO.
  const lpseo = await listLpseoPages() // published + indexable only
  const lpRootHubs = new Set<string>()
  const lpIndustryHubs = new Set<string>()
  for (const p of lpseo) {
    lpRootHubs.add(p.locale)
    lpIndustryHubs.add(`${p.locale}|${p.industry_slug}`)
  }
  const lpseoHubRoutes: MetadataRoute.Sitemap = [
    ...Array.from(lpRootHubs).map((locale) => ({
      url: `${SITE_URL}${lpseoRootHubPath(locale)}`, changeFrequency: 'weekly' as const, priority: 0.6,
    })),
    ...Array.from(lpIndustryHubs).map((key) => {
      const [locale, industry] = key.split('|')
      return { url: `${SITE_URL}${lpseoIndustryHubPath(locale, industry)}`, changeFrequency: 'weekly' as const, priority: 0.6 }
    }),
  ]
  const lpseoLeafRoutes: MetadataRoute.Sitemap = lpseo.map((p) => ({
    url: `${SITE_URL}${lpseoPath(p.locale, p.slug)}`,
    lastModified: p.updated_at ? new Date(p.updated_at) : undefined,
    changeFrequency: 'monthly',
    priority: 0.7,
  }))

  // Bare global market indexes (/gbp-management, /local-seo-services) — only listed
  // once the respective type has published pages, so an empty hub never enters the map.
  const globalIndexRoutes: MetadataRoute.Sitemap = [
    ...(pseo.length > 0 ? [{ url: `${SITE_URL}/gbp-management`, changeFrequency: 'weekly' as const, priority: 0.6 }] : []),
    ...(lpseo.length > 0 ? [{ url: `${SITE_URL}/local-seo-services`, changeFrequency: 'weekly' as const, priority: 0.6 }] : []),
  ]

  return [...staticRoutes, ...globalIndexRoutes, ...hubRoutes, ...leafRoutes, ...lpseoHubRoutes, ...lpseoLeafRoutes]
}
