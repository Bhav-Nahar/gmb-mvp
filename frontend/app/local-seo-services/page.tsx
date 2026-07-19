import type { Metadata } from 'next'
import PseoHub from '@/components/pseo/PseoHub'
import { listLpseoPages, rootHubPath, countryName, LPSEO_SEGMENT } from '@/lib/lpseo'

// Global market index at bare /local-seo-services: every market, each linking to
// its localized hub. Locale-prefixed URLs (/{locale}/local-seo-services/...) are
// handled by app/[slug]/local-seo-services — this static segment wins only for the
// exact bare path. Cached up to 1 year; publishes bust it on demand via the
// 'lpseo-list' tag on listLpseoPages.
export const revalidate = 31536000

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: 'Local SEO Services by Country & Industry | Pinzo',
    description: 'Explore managed local SEO services by country, industry and city.',
    alternates: { canonical: `${SITE_URL}/${LPSEO_SEGMENT}` },
  }
}

export default async function LocalSeoGlobalIndexPage() {
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
