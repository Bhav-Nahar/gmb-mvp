// Local-SEO pSEO (industry x city) managed-service landing pages.
// Sibling of lib/pseo.ts — served under /{locale}/local-seo-services/, a SEPARATE
// backend table (lpseo_pages). Rendered by components/lpseo/LpseoLanding.tsx.

export interface LpseoPair { title: string; detail: string }
export interface LpseoQa { q: string; a: string }
export interface LpseoIntent { title: string; detail: string; example?: string }
export interface LpseoService { channel: string; work: string; outcome: string }
export interface LpseoCompareRow { point: string; agency: string; software: string; pinzo: string }
export interface LpseoPhase { days: string; title: string; steps: string[] }
export interface LpseoBar { label: string; percent: number }
export interface LpseoPlan {
  tag?: string; name: string; desc?: string; features: string[]
  cta_label?: string; cta_href?: string; featured?: boolean
}
export interface LpseoLink { anchor: string; url: string; section?: string }

// The 15 link-capable section keys (mirror data-template-key in the template).
export type LpseoSection =
  | 'hero' | 'search-intent' | 'service-matrix' | 'industry-strategy'
  | 'maps-seo' | 'city-strategy' | 'aeo-coverage' | 'comparison-content'
  | 'workflow' | 'single-multi' | 'deliverables' | 'sample-audit'
  | 'engagement-model' | 'faqs' | 'related-links'

export interface LpseoContent {
  badge?: string
  hero_sub?: string
  primary_cta?: string
  secondary_cta?: string
  answer_heading?: string
  answer_block?: string
  strategy_heading?: string
  strategy_body?: string
  maps_body?: string
  city_body?: string
  audit_summary_title?: string
  audit_summary_body?: string
  lead_heading?: string
  lead_sub?: string
  final_heading?: string
  final_sub?: string
  final_button?: string
  gbp_url?: string // cross-link to the sibling GBP-management page (cannibalisation split)
  // Lists
  strategy_points?: string[]
  topics?: string[]
  maps_signals?: string[]
  neighborhoods?: string[]
  city_requirements?: string[]
  single_points?: string[]
  multi_points?: string[]
  secondary_keywords?: string[]
  // Structured
  value_props?: LpseoPair[]
  proof_points?: LpseoPair[]
  deliverables?: LpseoPair[]
  faqs?: LpseoQa[]
  answer_units?: LpseoQa[]
  search_intents?: LpseoIntent[]
  services?: LpseoService[]
  comparison?: LpseoCompareRow[]
  workflow_phases?: LpseoPhase[]
  audit_bars?: LpseoBar[]
  plans?: LpseoPlan[]
  related_pages?: { anchor: string; url: string }[]
  internal_links?: LpseoLink[]
  // Softer SEO/meta
  primary_keyword?: string
  region?: string
  last_updated?: string
  og_image?: string
}

export interface LpseoPageData {
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
  content: LpseoContent
  published_at: string | null
  updated_at: string | null
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

export const LPSEO_SEGMENT = 'local-seo-services'
export const lpseoPath = (locale: string, slug: string) => `/${locale}/${LPSEO_SEGMENT}/${slug}`
export const industryHubPath = (locale: string, industrySlug: string) => `/${locale}/${LPSEO_SEGMENT}/${industrySlug}`
export const rootHubPath = (locale: string) => `/${locale}/${LPSEO_SEGMENT}`
export const lpseoUrl = (locale: string, slug: string) => `${SITE_URL}${lpseoPath(locale, slug)}`
export const industryHubUrl = (locale: string, industrySlug: string) => `${SITE_URL}${industryHubPath(locale, industrySlug)}`

export const localeToCountry = (locale: string) => (locale.split('-')[1] || 'in').toLowerCase()

const COUNTRY_NAMES: Record<string, string> = {
  in: 'India', us: 'United States', gb: 'United Kingdom', ca: 'Canada',
  au: 'Australia', ae: 'UAE', sg: 'Singapore', za: 'South Africa', ie: 'Ireland', nz: 'New Zealand',
}
export const countryName = (code: string) => COUNTRY_NAMES[code] || code.toUpperCase()

function apiBase(): string {
  let base = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000/api/v1'
  if (base.includes('localhost')) base = base.replace('localhost', 'backend')
  return base
}

export async function getLpseoPage(slug: string): Promise<LpseoPageData | null> {
  try {
    // 1-year ISR (on-demand tag busting is the real refresh). Tagged per-page only
    // ('lpseo:{slug}') so a single-page or batched flush busts just this page, never
    // every other lpSEO page. Hubs/sitemap use the separate 'lpseo-list' tag.
    // Abort after 10s: a hung backend must degrade this page, not kill the whole
    // `next build` (60s static-gen timeout SIGTERMs the worker).
    const res = await fetch(`${apiBase()}/public/lpseo/${slug}`, { next: { revalidate: 31536000, tags: [`lpseo:${slug}`] }, signal: AbortSignal.timeout(10000) })
    if (!res.ok) return null
    return res.json()
  } catch (err) {
    console.error('Failed to fetch lpSEO page:', err)
    return null
  }
}

export interface LpseoListItem {
  slug: string
  country: string
  locale: string
  industry_label: string
  industry_slug: string
  city_label: string
  city_slug: string
  updated_at: string | null
}

export async function listLpseoPages(opts?: { industry?: string; country?: string }): Promise<LpseoListItem[]> {
  try {
    const params = new URLSearchParams()
    if (opts?.industry) params.set('industry', opts.industry)
    if (opts?.country) params.set('country', opts.country)
    const qs = params.toString() ? `?${params}` : ''
    const res = await fetch(`${apiBase()}/public/lpseo${qs}`, { next: { revalidate: 31536000, tags: ['lpseo-list'] }, signal: AbortSignal.timeout(10000) })
    if (!res.ok) return []
    const data = await res.json()
    return data.pages || []
  } catch {
    return []
  }
}

// Combined @graph: Organization, Service, WebPage, BreadcrumbList (+ FAQPage when
// the page has FAQs). Local-SEO managed service (not the software app itself).
export function buildLpseoJsonLd(page: LpseoPageData) {
  const url = lpseoUrl(page.locale, page.slug)
  const orgId = `${SITE_URL}/#organization`
  const graph: any[] = [
    {
      '@type': 'Organization',
      '@id': orgId,
      name: 'Pinzo',
      url: SITE_URL,
      logo: `${SITE_URL}/logo-horizontal-3.png`,
    },
    {
      '@type': 'Service',
      '@id': `${url}#service`,
      name: `Local SEO Services for ${page.industry_label} in ${page.city_label}`,
      serviceType: 'Managed local SEO services',
      provider: { '@id': orgId },
      areaServed: { '@type': 'City', name: page.city_label },
      audience: { '@type': 'BusinessAudience', audienceType: page.industry_label },
      description: page.meta_description,
    },
    {
      '@type': 'WebPage',
      '@id': `${url}#webpage`,
      url,
      name: page.meta_title,
      description: page.meta_description,
      inLanguage: page.locale,
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
        { '@type': 'ListItem', position: 2, name: 'Local SEO Services', item: `${SITE_URL}${rootHubPath(page.locale)}` },
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
