import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import PseoLanding from '@/components/pseo/PseoLanding'
import PseoHub from '@/components/pseo/PseoHub'
import {
  getPseoPage, listPseoPages, pseoPath, industryHubPath, rootHubPath,
  localeToCountry,
} from '@/lib/pseo'

// Served at /{locale}/gbp-management/{pseoSlug}. The [slug] segment is the locale
// (reusing the microsite route's segment name — Next.js forbids two different
// dynamic names at the same level). The pseoSlug is either a leaf page
// ({industry}-in-{city}) or an industry hub ({industry}).
//
// True ISR: HTML is cached 24h per page and served from the CDN. The admin
// publish flow and per-page flush bust it early via revalidateTag/revalidatePath
// (see app/api/revalidate/route.ts) — so 24h is only the *fallback* staleness.
export const revalidate = 86400

// Empty list = nothing prerendered at image build (backend may be unreachable
// there); REQUIRED even so — without generateStaticParams a dynamic segment is
// SSR'd on every request and revalidate above is ignored. With it, each visited
// path is rendered once, cached, and served as ISR.
export function generateStaticParams(): Params[] {
  return []
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

const LOCALE_RE = /^en-[a-z]{2}$/

type Params = { slug: string; pseoSlug: string }

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) return { title: 'Not Found' }
  const page = await getPseoPage(params.pseoSlug)

  if (page && page.locale === locale) {
    const canonical = page.canonical_url || `${SITE_URL}${pseoPath(page.locale, page.slug)}`
    // Backend already folds the quality-score gate into index_status (noindex when
    // score < 80), so this stays a single check.
    const noindex = page.index_status === 'noindex'
    // Per-page social image when the CMS sets one; brand logo otherwise.
    // ponytail: logo isn't 1200x630 — swap for a real OG image per industry when we have one.
    const ogImage = page.content?.og_image || `${SITE_URL}/logo-horizontal-3.png`
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
      openGraph: { title: page.meta_title, description: page.meta_description, url: canonical, siteName: 'Pinzo', type: 'website', images: [{ url: ogImage }] },
      twitter: { card: 'summary_large_image', title: page.meta_title, description: page.meta_description, images: [ogImage] },
    }
  }

  if (!page) {
    const cities = await listPseoPages({ industry: params.pseoSlug, country: localeToCountry(locale) })
    if (cities.length > 0) {
      const label = cities[0].industry_label
      const canonical = `${SITE_URL}${industryHubPath(locale, params.pseoSlug)}`
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

export default async function GbpManagementSlugPage({ params }: { params: Params }) {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) notFound()
  const page = await getPseoPage(params.pseoSlug)

  if (page) {
    // Wrong-locale prefix (e.g. /en-us/…/restaurants-in-mumbai, which is an India
    // page) → 404 so the two markets never serve duplicate content.
    if (locale !== page.locale) notFound()
    // Sibling city pages (same industry + market) for contextual internal links.
    // Link the next few after this one (wrapping) so every city gets an even share
    // of inbound links; the hub still reaches the full set. Capped to keep it tidy.
    const all = await listPseoPages({ industry: page.industry_slug, country: page.country })
    const idx = all.findIndex((p) => p.slug === page.slug)
    const siblings = idx === -1 ? [] : [...all.slice(idx + 1), ...all.slice(0, idx)].slice(0, 6)
    return <PseoLanding page={page} siblings={siblings} />
  }

  // Industry hub — scoped to this locale's market.
  const country = localeToCountry(locale)
  const cities = await listPseoPages({ industry: params.pseoSlug, country })
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
