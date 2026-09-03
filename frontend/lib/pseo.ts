import { marketName } from '@/lib/markets'
import { SHOW_PRICES } from '@/lib/pricingDisplay'
// pSEO (industry x city) landing pages: fetch + metadata + JSON-LD helpers.
// Rendered by components/pseo/PseoLanding.tsx via the [slug] route fallback.

export interface PseoPair { title: string; detail: string }
export interface PseoFaq { q: string; a: string }
export interface PseoCompareRow { point: string; manual: string; pinzo: string }

export interface PseoContent {
  badge?: string
  hero_sub?: string
  primary_cta?: string
  secondary_cta?: string
  // Audit-added sections. All optional — sensible defaults render when absent.
  answer_block?: string                                 // AEO direct answer under the hero
  comparison?: PseoCompareRow[]                          // Manual-vs-Pinzo table
  audit_checklist?: string[]                             // "free audit includes" checks
  review_examples?: { review: string; reply: string }[] // multiple review/reply pairs
  why_matters_body?: string
  why_matters_points?: string[]
  problems?: PseoPair[]
  solutions?: PseoPair[]
  gbp_categories?: string[]
  gbp_services?: string[]
  gbp_attributes?: string[]
  reviews_body?: string
  review_themes?: string[]
  example_review?: string
  example_reply?: string
  post_ideas?: string[]
  photo_checklist?: string[]
  city_visibility_body?: string
  neighborhoods?: string[]
  single_points?: string[]
  multi_points?: string[]
  monthly_workflow?: PseoPair[]
  faqs?: PseoFaq[]
  final_heading?: string
  final_sub?: string
  final_button?: string
  // Softer SEO fields (backend stores these in content JSON).
  primary_keyword?: string
  secondary_keywords?: string[]
  related_pages?: { anchor: string; url: string }[]
  // Optional per-page overrides. Contextual section links default from a static map
  // in PseoLanding (same on every page); set `section` here to add an extra link to
  // that block (reviews/posts/city/multi/solutions). No section -> footer link row only.
  internal_links?: { anchor: string; url: string; section?: string }[]
  og_image?: string
  region?: string
  last_updated?: string
}

export interface PseoPageData {
  slug: string
  country: string
  locale: string
  industry_label: string
  industry_slug: string
  city_label: string
  city_slug: string
  meta_title: string
  meta_description: string
  h1: string
  canonical_url: string | null
  index_status: string
  quality_score: number | null
  content: PseoContent
  published_at: string | null
  updated_at: string | null
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

// pSEO pages live under /{locale}/gbp-management/, separate from the microsite root
// namespace. A path-scoped middleware rewrites the locale prefix to the internal
// /gbp-management route. Leaf = /{locale}/gbp-management/{industry}-in-{city}; hubs above.
export const PSEO_SEGMENT = 'gbp-management'
export const pseoPath = (locale: string, slug: string) => `/${locale}/${PSEO_SEGMENT}/${slug}`
export const industryHubPath = (locale: string, industrySlug: string) => `/${locale}/${PSEO_SEGMENT}/${industrySlug}`
export const rootHubPath = (locale: string) => `/${locale}/${PSEO_SEGMENT}`
export const pseoUrl = (locale: string, slug: string) => `${SITE_URL}${pseoPath(locale, slug)}`
export const industryHubUrl = (locale: string, industrySlug: string) => `${SITE_URL}${industryHubPath(locale, industrySlug)}`

export const localeToCountry = (locale: string) => (locale.split('-')[1] || 'in').toLowerCase()

// Single source of truth in lib/markets.ts; see the note there on why.
export const countryName = marketName

function apiBase(): string {
  // Same internal-routing dance as microsites: SSR inside docker-compose talks
  // to the backend service directly.
  let base = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000/api/v1'
  if (base.includes('localhost')) base = base.replace('localhost', 'backend')
  return base
}

export async function getPseoPage(slug: string): Promise<PseoPageData | null> {
  try {
    // 1-year ISR (on-demand tag busting is the real refresh). Tagged per-page only
    // ('pseo:{slug}') so a single-page or batched flush busts just this page, never
    // every other pSEO page. Hubs/sitemap use the separate 'pseo-list' tag.
    // Abort after 10s: a hung backend must degrade this page, not kill the whole
    // `next build` (60s static-gen timeout SIGTERMs the worker).
    const res = await fetch(`${apiBase()}/public/pseo/${slug}`, { next: { revalidate: 31536000, tags: [`pseo:${slug}`] }, signal: AbortSignal.timeout(10000) })
    if (!res.ok) return null
    return res.json()
  } catch (err) {
    console.error('Failed to fetch pSEO page:', err)
    return null
  }
}

export interface PseoListItem {
  slug: string
  country: string
  locale: string
  industry_label: string
  industry_slug: string
  city_label: string
  city_slug: string
  updated_at: string | null
}

// List published, indexable pages. Filter by industry (hub) and/or country (market).
export async function listPseoPages(opts?: { industry?: string; country?: string }): Promise<PseoListItem[]> {
  try {
    const params = new URLSearchParams()
    if (opts?.industry) params.set('industry', opts.industry)
    if (opts?.country) params.set('country', opts.country)
    const qs = params.toString() ? `?${params}` : ''
    // Industry-scoped list tag so a single page edit busts only that industry's
    // leaves (every leaf embeds this fetch for siblings) — NOT the whole corpus.
    // Global 'pseo-list' stays for corpus-wide callers (sitemap, root/country hubs).
    // Both tags are busted by the backend revalidate payload; keep the strings in sync.
    const listTag = opts?.industry ? `pseo-list:${opts.country ?? 'in'}:${opts.industry}` : 'pseo-list'
    const res = await fetch(`${apiBase()}/public/pseo${qs}`, { next: { revalidate: 31536000, tags: [listTag] }, signal: AbortSignal.timeout(10000) })
    if (!res.ok) return []
    const data = await res.json()
    return data.pages || []
  } catch {
    return []
  }
}

// Self-canonical (or admin override) for a page.
export const pseoCanonical = (page: PseoPageData) => page.canonical_url || pseoUrl(page.locale, page.slug)

// Combined @graph per the pSEO template's required schema stack:
// Organization, SoftwareApplication, Service, WebPage, BreadcrumbList (+FAQPage when visible).
export function buildPseoJsonLd(page: PseoPageData) {
  const url = pseoUrl(page.locale, page.slug)
  const orgId = `${SITE_URL}/#organization`
  const softwareId = `${SITE_URL}/#software`
  const graph: any[] = [
    {
      '@type': 'Organization',
      '@id': orgId,
      name: 'Pinzo',
      url: SITE_URL,
      logo: `${SITE_URL}/logo-horizontal-3.png`,
    },
    {
      '@type': 'SoftwareApplication',
      '@id': softwareId,
      name: 'Pinzo',
      url: SITE_URL,
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      publisher: { '@id': orgId },
      // Must match what the page shows. Prices are hidden on-page (SHOW_PRICES), so the
      // Offer carries no amount — structured data contradicting on-page pricing is a Google flag.
      offers: SHOW_PRICES
        ? (page.country === 'in'
          ? { '@type': 'Offer', price: '799', priceCurrency: 'INR', description: 'Plans from ₹799/month (incl. GST) after a 7-day free trial. Free audit, no card required.' }
          : { '@type': 'Offer', price: '8', priceCurrency: 'USD', description: 'Plans from $8/month after a 7-day free trial. Free audit, no card required.' })
        : { '@type': 'Offer', availability: 'https://schema.org/InStock', description: 'Custom pricing on request. Free audit, no card required, then a 7-day free trial.' },
    },
    {
      '@type': 'Service',
      '@id': `${url}#service`,
      name: `Google Business Profile Management for ${page.industry_label} in ${page.city_label}`,
      serviceType: 'Google Business Profile management',
      provider: { '@id': orgId },
      areaServed: { '@type': 'City', name: page.city_label },
      audience: { '@type': 'Audience', audienceType: page.industry_label },
    },
    {
      '@type': 'WebPage',
      '@id': `${url}#webpage`,
      url,
      name: page.meta_title,
      description: page.meta_description,
      isPartOf: { '@type': 'WebSite', url: SITE_URL, name: 'Pinzo' },
      about: { '@id': `${url}#service` },
      ...(page.published_at ? { datePublished: page.published_at } : {}),
      ...(page.updated_at ? { dateModified: page.updated_at } : {}),
    },
    {
      '@type': 'BreadcrumbList',
      '@id': `${url}#breadcrumb`,
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        { '@type': 'ListItem', position: 2, name: 'GBP Management', item: `${SITE_URL}${rootHubPath(page.locale)}` },
        { '@type': 'ListItem', position: 3, name: page.industry_label, item: industryHubUrl(page.locale, page.industry_slug) },
        { '@type': 'ListItem', position: 4, name: `${page.industry_label} in ${page.city_label}`, item: url },
      ],
    },
  ]
  const faqs = page.content?.faqs || []
  if (faqs.length > 0) {
    graph.push({
      '@type': 'FAQPage',
      '@id': `${url}#faq`,
      mainEntity: faqs.map((f) => ({
        '@type': 'Question',
        name: f.q,
        acceptedAnswer: { '@type': 'Answer', text: f.a },
      })),
    })
  }
  return { '@context': 'https://schema.org', '@graph': graph }
}
