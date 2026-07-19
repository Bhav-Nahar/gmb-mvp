import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import PseoHub from '@/components/pseo/PseoHub'
import {
  listLpseoPages, lpseoPath, rootHubPath, localeToCountry, countryName,
} from '@/lib/lpseo'

// Market hub at /{locale}/local-seo-services: the industries available in that country.
// Cached up to 1 year; publishes bust it on demand via the 'lpseo-list' tag.
export const revalidate = 31536000

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
    title: `Local SEO Services in ${countryName(cc)} | Pinzo`,
    description: `Managed local SEO by industry across ${countryName(cc)} — rank on Google Maps, win local organic search and get recommended by AI search.`,
    alternates: { canonical },
  }
}

export default async function LocalSeoMarketHubPage({ params }: { params: Params }) {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) notFound()

  const cc = localeToCountry(locale)
  const pages = await listLpseoPages({ country: cc })
  const byIndustry = new Map<string, { label: string; count: number }>()
  for (const p of pages) {
    const cur = byIndustry.get(p.industry_slug)
    if (cur) cur.count++
    else byIndustry.set(p.industry_slug, { label: p.industry_label, count: 1 })
  }
  const cards = Array.from(byIndustry.entries()).map(([slug, v]) => ({
    href: lpseoPath(locale, slug),
    title: v.label,
    subtitle: `${v.count} ${v.count === 1 ? 'city' : 'cities'}`,
  }))

  // No pages in this market -> 404 rather than an indexable, empty "coming soon"
  // hub (thin content Google would flag). The route reappears once pages exist.
  if (cards.length === 0) notFound()

  return (
    <PseoHub
      crumbs={[{ label: 'Home', href: '/' }, { label: 'Local SEO Services' }]}
      title={`Local SEO services in ${countryName(cc)}`}
      subtitle="Pick your industry to see how Pinzo grows local visibility across Google, Maps and AI search — city by city."
      cards={cards}
    />
  )
}
