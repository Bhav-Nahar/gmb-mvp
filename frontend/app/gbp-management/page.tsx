import type { Metadata } from 'next'
import PseoHub from '@/components/pseo/PseoHub'
import { listPseoPages, rootHubPath, countryName, PSEO_SEGMENT } from '@/lib/pseo'

// Global market index at bare /gbp-management: every market, each linking to its
// localized hub. Locale-prefixed URLs (/{locale}/gbp-management/...) are handled
// by app/[slug]/gbp-management — this static segment wins only for the exact
// bare path. Cached up to 1 year; publishes bust it on demand via the
// 'pseo-list' tag on listPseoPages.
export const revalidate = 31536000

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

export async function generateMetadata(): Promise<Metadata> {
  return {
    title: 'Google Business Profile Management by Country & Industry | Pinzo',
    description: 'Explore Google Business Profile management guides by country, industry and city.',
    alternates: { canonical: `${SITE_URL}/${PSEO_SEGMENT}` },
  }
}

export default async function GbpManagementGlobalIndexPage() {
  const all = await listPseoPages()
  const countries = new Map<string, number>()
  for (const p of all) countries.set(p.country, (countries.get(p.country) || 0) + 1)
  const cards = Array.from(countries.entries()).map(([cc, count]) => ({
    href: rootHubPath(`en-${cc}`),
    title: countryName(cc),
    subtitle: `${count} ${count === 1 ? 'page' : 'pages'}`,
  }))
  return (
    <PseoHub
      crumbs={[{ label: 'Home', href: '/' }, { label: 'GBP Management' }]}
      title="Google Business Profile management, by market"
      subtitle="Local search works differently in every country. Pick a market to explore industry guides."
      cards={cards}
      emptyText="Guides are coming soon."
    />
  )
}
