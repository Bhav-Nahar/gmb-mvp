import type { MetadataRoute } from 'next'
import { listPseoPages, pseoPath, industryHubPath, rootHubPath } from '@/lib/pseo'
import {
  listLpseoPages, lpseoPath, isLpseoPillar,
  industryHubPath as lpseoIndustryHubPath, rootHubPath as lpseoRootHubPath,
} from '@/lib/lpseo'
import { getCseoPillar } from '@/lib/cseo'
import { FEATURES } from '@/lib/features'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

// Rendered per request: must include every published pSEO page, and the backend
// isn't reachable at image-build time (a static prerender would bake in an empty
// sitemap). Search engines fetch this only periodically, so cost is negligible.
export const dynamic = 'force-dynamic'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/` },
    { url: `${SITE_URL}/pricing` },
    { url: `${SITE_URL}/google-business-profile-management` },
    { url: `${SITE_URL}/features` },
    ...FEATURES.map((f) => ({ url: `${SITE_URL}/features/${f.slug}` })),
    { url: `${SITE_URL}/contact` },
    { url: `${SITE_URL}/privacy` },
    { url: `${SITE_URL}/terms` },
    { url: `${SITE_URL}/refund` },
  ]

  const pseo = await listPseoPages() // published + indexable only

  // Per-locale root hub + per-(locale, industry) hub + every leaf, all locale-prefixed.
  // A hub's lastmod is the newest child it lists. Google only trusts lastmod when it
  // is accurate, and an inaccurate one makes it ignore the field site-wide, so it is
  // derived from real child timestamps or omitted entirely. Static pages get none.
  const newest = (a: Date | undefined, iso: string | null) => {
    if (!iso) return a
    const d = new Date(iso)
    return !a || d > a ? d : a
  }
  const rootHubs = new Map<string, Date | undefined>()          // locale
  const industryHubs = new Map<string, Date | undefined>()      // `${locale}|${industrySlug}`
  for (const p of pseo) {
    rootHubs.set(p.locale, newest(rootHubs.get(p.locale), p.updated_at))
    const k = `${p.locale}|${p.industry_slug}`
    industryHubs.set(k, newest(industryHubs.get(k), p.updated_at))
  }

  const hubRoutes: MetadataRoute.Sitemap = [
    ...Array.from(rootHubs).map(([locale, lastModified]) => ({
      url: `${SITE_URL}${rootHubPath(locale)}`, lastModified,
    })),
    ...Array.from(industryHubs).map(([key, lastModified]) => {
      const [locale, industry] = key.split('|')
      return { url: `${SITE_URL}${industryHubPath(locale, industry)}`, lastModified }
    }),
  ]

  const leafRoutes: MetadataRoute.Sitemap = pseo.map((p) => ({
    url: `${SITE_URL}${pseoPath(p.locale, p.slug)}`,
    lastModified: p.updated_at ? new Date(p.updated_at) : undefined,
  }))

  // Local-SEO pages (/local-seo-services) — same hub + leaf shape as pSEO.
  const lpseo = await listLpseoPages() // published + indexable only
  // Only an INDEXABLE pillar belongs here. A sitemap entry for a noindex page is a
  // contradictory signal: it asks Google to crawl a URL that then refuses indexing.
  const gp = await getCseoPillar('global')
  const globalPillar = gp && gp.index_status === 'index' ? gp : null
  const lpRootHubs = new Map<string, Date | undefined>()
  const lpIndustryHubs = new Map<string, Date | undefined>()
  for (const p of lpseo) {
    lpRootHubs.set(p.locale, newest(lpRootHubs.get(p.locale), p.updated_at))
    const k = `${p.locale}|${p.industry_slug}`
    lpIndustryHubs.set(k, newest(lpIndustryHubs.get(k), p.updated_at))
  }
  const lpseoHubRoutes: MetadataRoute.Sitemap = [
    ...Array.from(lpRootHubs).map(([locale, lastModified]) => ({
      url: `${SITE_URL}${lpseoRootHubPath(locale)}`, lastModified,
    })),
    ...Array.from(lpIndustryHubs).map(([key, lastModified]) => {
      const [locale, industry] = key.split('|')
      return { url: `${SITE_URL}${lpseoIndustryHubPath(locale, industry)}`, lastModified }
    }),
  ]
  // Pillars are excluded here: an industry pillar's URL is the industry hub path,
  // which lpseoHubRoutes already emits. Listing both put the same URL in the
  // sitemap twice, with two different lastModified values.
  const lpseoLeafRoutes: MetadataRoute.Sitemap = lpseo.filter((p) => !isLpseoPillar(p)).map((p) => ({
    url: `${SITE_URL}${lpseoPath(p.locale, p.slug)}`,
    lastModified: p.updated_at ? new Date(p.updated_at) : undefined,
  }))

  // Bare global market indexes (/gbp-management, /local-seo-services) — only listed
  // once the respective type has published pages, so an empty hub never enters the map.
  const globalIndexRoutes: MetadataRoute.Sitemap = [
    ...(pseo.length > 0 ? [{ url: `${SITE_URL}/gbp-management` }] : []),
    // The bare /local-seo-services is the global pillar when one is published; it
    // no longer depends on there being indexable leaves. Trailing slash matches the
    // pillar's canonical.
    ...(globalPillar
      ? [{ url: `${SITE_URL}/local-seo-services/`, lastModified: globalPillar.updated_at ? new Date(globalPillar.updated_at) : undefined }]
      : lpseo.length > 0
        ? [{ url: `${SITE_URL}/local-seo-services` }]
        : []),
  ]

  return [...staticRoutes, ...globalIndexRoutes, ...hubRoutes, ...leafRoutes, ...lpseoHubRoutes, ...lpseoLeafRoutes]
}
