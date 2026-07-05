import type { Metadata } from 'next'
import { headers } from 'next/headers'
import PseoHub from '@/components/pseo/PseoHub'
import {
  listPseoPages, pseoPath, rootHubPath, localeToCountry, countryName, PSEO_SEGMENT,
} from '@/lib/pseo'

export const dynamic = 'force-dynamic'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

// Two modes, same file:
//  - /{locale}/gbp-management (via middleware, x-pseo-locale set) → market hub:
//    the industries available in that country.
//  - /gbp-management (bare, no locale) → global index: every market, each linking
//    to its localized hub.

function requestedLocale(): string | null {
  return headers().get('x-pseo-locale')
}

export async function generateMetadata(): Promise<Metadata> {
  const locale = requestedLocale()
  if (locale) {
    const cc = localeToCountry(locale)
    const canonical = `${SITE_URL}${rootHubPath(locale)}`
    return {
      title: `Google Business Profile Management in ${countryName(cc)} | Pinzo`,
      description: `Explore GBP management guides by industry across ${countryName(cc)}. Rank on Google Maps, manage reviews, and get recommended by AI search.`,
      alternates: { canonical },
    }
  }
  return {
    title: 'Google Business Profile Management by Country & Industry | Pinzo',
    description: 'Explore Google Business Profile management guides by country, industry and city.',
    alternates: { canonical: `${SITE_URL}/${PSEO_SEGMENT}` },
  }
}

export default async function GbpManagementHubPage() {
  const locale = requestedLocale()

  // Global index: list markets.
  if (!locale) {
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

  // Market hub: industries in this country.
  const cc = localeToCountry(locale)
  const pages = await listPseoPages({ country: cc })
  const byIndustry = new Map<string, { label: string; count: number }>()
  for (const p of pages) {
    const cur = byIndustry.get(p.industry_slug)
    if (cur) cur.count++
    else byIndustry.set(p.industry_slug, { label: p.industry_label, count: 1 })
  }
  const cards = Array.from(byIndustry.entries()).map(([slug, v]) => ({
    href: pseoPath(locale, slug),
    title: v.label,
    subtitle: `${v.count} ${v.count === 1 ? 'city' : 'cities'}`,
  }))

  return (
    <PseoHub
      crumbs={[{ label: 'Home', href: '/' }, { label: 'GBP Management' }]}
      title={`Google Business Profile management in ${countryName(cc)}`}
      subtitle="Pick your industry to see how Pinzo helps you get found on Google, Maps and AI search — city by city."
      cards={cards}
      emptyText="Industry guides for this market are coming soon."
    />
  )
}
