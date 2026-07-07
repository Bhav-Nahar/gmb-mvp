import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import PseoHub from '@/components/pseo/PseoHub'
import {
  listPseoPages, pseoPath, rootHubPath, localeToCountry, countryName,
} from '@/lib/pseo'

// Market hub at /{locale}/gbp-management: the industries available in that
// country. The [slug] segment is the locale (see [pseoSlug]/page.tsx for why).
// True ISR, 24h fallback; publish flow busts it earlier via the 'pseo' tag.
export const revalidate = 86400

// Required for ISR — see [pseoSlug]/page.tsx.
export function generateStaticParams(): Params[] {
  return []
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

const LOCALE_RE = /^en-[a-z]{2}$/

type Params = { slug: string }

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) return { title: 'Not Found' }
  const cc = localeToCountry(locale)
  const canonical = `${SITE_URL}${rootHubPath(locale)}`
  return {
    title: `Google Business Profile Management in ${countryName(cc)} | Pinzo`,
    description: `Explore GBP management guides by industry across ${countryName(cc)}. Rank on Google Maps, manage reviews, and get recommended by AI search.`,
    alternates: { canonical },
  }
}

export default async function GbpManagementMarketHubPage({ params }: { params: Params }) {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) notFound()

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
