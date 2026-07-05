import type { MetadataRoute } from 'next'
import { listPseoPages, pseoPath, industryHubPath, rootHubPath } from '@/lib/pseo'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

// Rendered per request: must include every published pSEO page, and the backend
// isn't reachable at image-build time (a static prerender would bake in an empty
// sitemap). Search engines fetch this only periodically, so cost is negligible.
export const dynamic = 'force-dynamic'

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE_URL}/pricing`, changeFrequency: 'weekly', priority: 0.8 },
    { url: `${SITE_URL}/google-business-profile-management`, changeFrequency: 'weekly', priority: 0.8 },
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

  return [...staticRoutes, ...hubRoutes, ...leafRoutes]
}
