import type { Metadata } from 'next'
import PseoHub from '@/components/pseo/PseoHub'
import CseoPillarGlobal from '@/components/cseo/CseoPillarGlobal'
import { listLpseoPages, rootHubPath, countryName, LPSEO_SEGMENT } from '@/lib/lpseo'
import { getCseoPillar, noSlash } from '@/lib/cseo'

// The bare /local-seo-services is the GLOBAL pillar: the x-default, locale-free head
// of the Local SEO universe. It is stored as the cseo_pages row with country
// 'global', the same table and the same page family as the country pillars at
// /{locale}/local-seo-services/.
//
// When that row is not published the path keeps its previous behaviour exactly: an
// auto-generated index of every market that has indexable leaf pages.
//
// Locale-prefixed URLs are handled by app/[slug]/local-seo-services; this static
// segment wins only for the exact bare path. Cached up to 1 year; a pillar edit busts
// the 'cseo:global' tag and a leaf publish busts 'lpseo-list'.
// Rendered on demand, NOT prerendered at build.
//
// This is the only page in the family with no dynamic segment, so Next would
// statically prerender it during `next build` — at which point the backend is
// unreachable and getCseoPillar() returns null, freezing the market-grid fallback
// into the image. That is exactly what happened, and a TTL only bounds how long the
// wrong page serves. Forcing dynamic makes it behave like every locale-prefixed
// tier: fetched per request, with the backend's own Redis cache doing the work.
export const dynamic = 'force-dynamic'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'
const GLOBAL = 'global'

export async function generateMetadata(): Promise<Metadata> {
  const pillar = await getCseoPillar(GLOBAL)
  if (pillar) {
    const noindex = pillar.index_status === 'noindex'
    // The package authors this with a trailing slash but the router 308s that form.
    const url = noSlash(pillar.canonical_url || `${SITE_URL}/${LPSEO_SEGMENT}`)
    return {
      title: pillar.meta_title,
      description: pillar.meta_description,
      // follow stays true while staged so crawlers can still reach the markets.
      robots: { index: !noindex, follow: true },
      // This page IS the x-default. Published markets are listed as reciprocal
      // alternates so the hreflang cluster is two-way rather than self-referential.
      alternates: {
        canonical: url,
        languages: { 'x-default': url, 'en-in': `${SITE_URL}/en-in/${LPSEO_SEGMENT}` },
      },
      openGraph: { title: pillar.meta_title, description: pillar.meta_description, url, siteName: 'Pinzo', type: 'website' },
      twitter: { card: 'summary_large_image', title: pillar.meta_title, description: pillar.meta_description },
    }
  }

  return {
    title: 'Local SEO Services by Country & Industry | Pinzo',
    description: 'Explore managed local SEO services by country, industry and city.',
    // This branch only renders when the curated pillar is missing or unreachable.
    // That is precisely when a thin auto-generated grid must NOT be indexable, so
    // the directive is explicit rather than inherited.
    robots: { index: false, follow: true },
    alternates: {
      canonical: `${SITE_URL}/${LPSEO_SEGMENT}`,
      languages: { 'x-default': `${SITE_URL}/${LPSEO_SEGMENT}` },
    },
  }
}

export default async function LocalSeoGlobalIndexPage() {
  // Curated pillar wins over the generated index once it is published.
  const pillar = await getCseoPillar(GLOBAL)
  if (pillar) return <CseoPillarGlobal page={pillar} />

  const all = await listLpseoPages()
  const countries = new Map<string, number>()
  for (const p of all) countries.set(p.country, (countries.get(p.country) || 0) + 1)
  const cards = Array.from(countries.entries()).map(([cc, count]) => ({
    href: rootHubPath(`en-${cc}`),
    title: countryName(cc),
    subtitle: `${count} ${count === 1 ? 'page' : 'pages'}`,
  }))
  return (
    <PseoHub
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Local SEO Services' }]}
      title="Local SEO services, by market"
      subtitle="Local search works differently in every country. Pick a market to explore industry guides."
      cards={cards}
      emptyText="Guides are coming soon."
    />
  )
}
