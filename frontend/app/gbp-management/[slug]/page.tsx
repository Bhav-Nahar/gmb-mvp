import type { Metadata } from 'next'
import { notFound, redirect } from 'next/navigation'
import { headers } from 'next/headers'
import PseoLanding from '@/components/pseo/PseoLanding'
import PseoHub from '@/components/pseo/PseoHub'
import {
  getPseoPage, listPseoPages, pseoPath, industryHubPath, rootHubPath,
  localeToCountry, PSEO_SEGMENT,
} from '@/lib/pseo'

export const dynamic = 'force-dynamic' // locale comes from a request header (middleware)

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

// Served under /{locale}/gbp-management/{slug} — the middleware rewrites that to this
// internal route and sets x-pseo-locale. The single segment is either a leaf page
// ({industry}-in-{city}) or an industry hub ({industry}).

function requestedLocale(): string | null {
  return headers().get('x-pseo-locale')
}

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  const locale = requestedLocale()
  const page = await getPseoPage(params.slug)

  if (page) {
    const canonical = page.canonical_url || `${SITE_URL}${pseoPath(page.locale, page.slug)}`
    const noindex = page.index_status === 'noindex'
    return {
      title: page.meta_title,
      description: page.meta_description,
      robots: { index: !noindex, follow: true },
      alternates: {
        canonical,
        // Self-referential hreflang + x-default (city pages are single-locale; this
        // stays correct and future-proofs cross-market variants).
        languages: { [page.locale]: canonical, 'x-default': canonical },
      },
      openGraph: { title: page.meta_title, description: page.meta_description, url: canonical, siteName: 'Pinzo', type: 'website' },
      twitter: { card: 'summary_large_image', title: page.meta_title, description: page.meta_description },
    }
  }

  if (locale) {
    const cities = await listPseoPages({ industry: params.slug, country: localeToCountry(locale) })
    if (cities.length > 0) {
      const label = cities[0].industry_label
      const canonical = `${SITE_URL}${industryHubPath(locale, params.slug)}`
      return {
        title: `Google Business Profile Management for ${label} | Pinzo`,
        description: `Grow ${label.toLowerCase()} visibility on Google Search, Maps and AI search. Pick your city.`,
        robots: { index: true, follow: true },
        alternates: { canonical },
      }
    }
  }
  return { title: 'Not Found', description: 'The requested page could not be found.' }
}

export default async function GbpManagementSlugPage({ params }: { params: { slug: string } }) {
  const locale = requestedLocale()
  const page = await getPseoPage(params.slug)

  if (page) {
    // Direct hit on the bare /gbp-management/{slug} (no locale prefix) → send to the
    // canonical locale URL. Wrong-locale prefix (e.g. /en-us/…/restaurants-in-mumbai,
    // which is an India page) → 404 so the two markets never serve duplicate content.
    if (!locale) redirect(pseoPath(page.locale, page.slug))
    if (locale !== page.locale) notFound()
    return <PseoLanding page={page} />
  }

  // Industry hub — needs a locale to scope to a market.
  if (!locale) redirect(`/${PSEO_SEGMENT}`) // bare industry access → global market index
  const country = localeToCountry(locale)
  const cities = await listPseoPages({ industry: params.slug, country })
  if (cities.length > 0) {
    const label = cities[0].industry_label
    return (
      <PseoHub
        crumbs={[{ label: 'Home', href: '/' }, { label: 'GBP Management', href: rootHubPath(locale) }, { label }]}
        title={`Google Business Profile management for ${label.toLowerCase()}`}
        subtitle={`Choose your city to see how Pinzo helps ${label.toLowerCase()} rank on Google Maps, answer reviews with AI, and get recommended by AI search.`}
        cards={cities.map((c) => ({
          href: pseoPath(locale, c.slug),
          title: `${label} in ${c.city_label}`,
          subtitle: c.city_label,
        }))}
      />
    )
  }

  notFound()
}
