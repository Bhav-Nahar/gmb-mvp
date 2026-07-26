import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import PseoHub from '@/components/pseo/PseoHub'
import CseoPillar from '@/components/cseo/CseoPillar'
import {
  listLpseoPages, lpseoPath, rootHubPath, localeToCountry, countryName, isLpseoPillar,
  buildLiveFamilyPaths,
} from '@/lib/lpseo'
import { getCseoPillar, noSlash } from '@/lib/cseo'
import { listPseoPages, pseoPath } from '@/lib/pseo'

// /{locale}/local-seo-services serves the country pillar when one is published for
// that market, and otherwise falls back to the auto-generated industry hub. The
// pillar is the curated, editorially-owned version of the same URL, so it wins;
// markets without one keep exactly the behaviour they had before.
// Cached up to 1 year; publishes bust it via the 'cseo:{cc}' or 'lpseo-list' tag.
export const revalidate = 31536000

export function generateStaticParams(): Params[] {
  return []
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'
const LOCALE_RE = /^en-[a-z]{2}$/

type Params = { slug: string }

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) return { title: 'Not Found' }
  const cc = localeToCountry(locale)
  const canonical = `${SITE_URL}${rootHubPath(locale)}`

  const pillar = await getCseoPillar(cc)
  if (pillar) {
    const noindex = pillar.index_status === 'noindex'
    const url = noSlash(pillar.canonical_url || canonical)
    return {
      title: pillar.meta_title,
      description: pillar.meta_description,
      // follow stays true even while noindex: a staged pillar should still let
      // crawlers reach its children. nofollow here severed the whole family's
      // discovery chain at the country tier.
      robots: { index: !noindex, follow: true },
      alternates: { canonical: url, languages: { [pillar.locale]: url, 'x-default': `${SITE_URL}/local-seo-services` } },
      openGraph: { title: pillar.meta_title, description: pillar.meta_description, url, siteName: 'Pinzo', type: 'website' },
      twitter: { card: 'summary_large_image', title: pillar.meta_title, description: pillar.meta_description },
    }
  }

  return {
    title: `Local SEO Services in ${countryName(cc)} | Pinzo`,
    description: `Managed local SEO by industry across ${countryName(cc)}. Rank on Google Maps, win local organic search and get recommended by AI search.`,
    alternates: { canonical },
  }
}

export default async function LocalSeoMarketHubPage({ params }: { params: Params }) {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) notFound()

  const cc = localeToCountry(locale)

  // Curated pillar wins over the generated hub when the market has one.
  const pillar = await getCseoPillar(cc)
  if (pillar) {
    // Both families' published sets, so a link to an unbuilt city, industry or GBP
    // page degrades to plain text instead of shipping a 404.
    const [lp, pp] = await Promise.all([listLpseoPages({ country: cc }), listPseoPages({ country: cc })])
    const livePaths = buildLiveFamilyPaths(lp, locale, pp.map((p) => pseoPath(p.locale, p.slug)))
    return <CseoPillar page={pillar} livePaths={livePaths} />
  }

  // Pillars share the leaf table but are not cities, so they must not inflate the
  // per-industry city count on the cards.
  const pages = (await listLpseoPages({ country: cc })).filter((p) => !isLpseoPillar(p))
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
      subtitle="Pick your industry to see how Pinzo grows local visibility across Google, Maps and AI search, city by city."
      cards={cards}
    />
  )
}
