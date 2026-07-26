// Country pillar for the Local SEO universe, served at /{locale}/local-seo-services/.
// Third sibling of lib/pseo.ts and lib/lpseo.ts, backed by its own table (cseo_pages).
// Rendered by components/cseo/CseoPillar.tsx.

export interface CseoPair { title: string; detail: string }
// `detail` is the optional third part of a link cell ("anchor::url::detail"). The
// city and industry cards carry a descriptor; the plain link lists do not.
export interface CseoLink { anchor: string; url: string; detail?: string }
export interface CseoQa { q: string; a: string }
export interface CseoService { area: string; work: string; why: string }
export interface CseoChecklistRow { ask: string; good: string; warning: string }
// Same shape as the global pillar's engagement models: it is the same card.
export interface CseoPackage {
  tag: string; name: string; detail: string
  features: string[]; cta_label: string; cta_url: string
}

export interface CseoContent {
  page_id?: string
  page_type?: string
  template_version?: string
  primary_keyword?: string
  badge?: string
  hero_copy?: string
  primary_cta?: string
  secondary_cta?: string
  direct_question?: string
  direct_answer?: string
  package_copy?: string
  package_note?: string
  proof_asset_url?: string
  form_destination?: string
  last_updated?: string
  // Lists
  secondary_keywords?: string[]
  single_location_points?: string[]
  multi_location_points?: string[]
  monthly_deliverables?: string[]
  launch_blockers?: string[]
  proof_asset_type?: string[]
  // Pairs
  search_behaviour?: CseoPair[]
  ranking_factors?: CseoPair[]
  ai_entity_plan?: CseoPair[]
  safeguards?: CseoPair[]
  roadmap_90_days?: CseoPair[]
  proof_assets?: CseoPair[]
  audit_checklist?: CseoPair[]
  // Links
  city_hubs?: CseoLink[]
  industry_hubs?: CseoLink[]
  internal_links?: CseoLink[]
  // Structured
  service_matrix?: CseoService[]
  buyer_checklist?: CseoChecklistRow[]
  packages?: CseoPackage[]
  faqs?: CseoQa[]
}

export interface CseoPageData {
  country: string
  country_label: string
  locale: string
  meta_title: string
  meta_description: string
  h1: string
  canonical_url: string | null
  index_status: string
  quality_score: number | null
  content: CseoContent
  published_at: string | null
  updated_at: string | null
}

// The router runs with trailingSlash:false, so every slashed URL 308-redirects.
// The content packages author canonicals WITH a slash, which made three tiers
// self-canonicalise to a redirect. The router wins: strip it at the edge so the
// canonical, og:url, hreflang and every JSON-LD @id agree with what actually serves.
export const noSlash = (u: string) => (u.length > 1 && u.endsWith('/') ? u.replace(/\/+$/, '') : u)

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

export const cseoPath = (locale: string) => `/${locale}/local-seo-services`
export const cseoUrl = (locale: string) => `${SITE_URL}${cseoPath(locale)}/`

function apiBase(): string {
  let base = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000/api/v1'
  if (base.includes('localhost')) base = base.replace('localhost', 'backend')
  return base
}

export async function getCseoPillar(country: string): Promise<CseoPageData | null> {
  try {
    // Tagged 'cseo:{country}' only. The pillar owns one path, so an edit must never
    // ride the 'lpseo-list' tag and re-render the whole leaf corpus.
    const res = await fetch(`${apiBase()}/public/cseo/${country}`, {
      next: { revalidate: 31536000, tags: [`cseo:${country}`] },
      signal: AbortSignal.timeout(10000),
    })
    if (!res.ok) return null
    return res.json()
  } catch (err) {
    console.error('Failed to fetch country pillar:', err)
    return null
  }
}

// Guardrail 11: Organization, WebSite, WebPage, Service, BreadcrumbList, FAQPage.
// areaServed must be the country; no Review/AggregateRating/LocalBusiness without
// verified visible evidence, and no Offer (pricing is linked, not embedded).
export function buildCseoJsonLd(page: CseoPageData) {
  const url = noSlash(page.canonical_url || cseoUrl(page.locale))
  const orgId = `${SITE_URL}/#organization`
  const graph: any[] = [
    { '@type': 'Organization', '@id': orgId, name: 'Pinzo', url: SITE_URL, logo: `${SITE_URL}/logo-horizontal-3.png` },
    { '@type': 'WebSite', '@id': `${SITE_URL}/#website`, url: SITE_URL, name: 'Pinzo', publisher: { '@id': orgId } },
    {
      '@type': 'Service',
      '@id': `${url}#service`,
      name: `Local SEO Services in ${page.country_label}`,
      serviceType: 'Managed local SEO services',
      provider: { '@id': orgId },
      areaServed: { '@type': 'Country', name: page.country_label },
      description: page.meta_description,
    },
    {
      '@type': 'WebPage',
      '@id': `${url}#webpage`,
      url,
      name: page.meta_title,
      description: page.meta_description,
      inLanguage: page.locale,
      isPartOf: { '@id': `${SITE_URL}/#website` },
      about: { '@id': `${url}#service` },
      ...(page.published_at ? { datePublished: page.published_at } : {}),
      ...(page.updated_at ? { dateModified: page.updated_at } : {}),
    },
    {
      '@type': 'BreadcrumbList',
      '@id': `${url}#breadcrumb`,
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        { '@type': 'ListItem', position: 2, name: 'Local SEO Services', item: `${SITE_URL}/local-seo-services` },
        { '@type': 'ListItem', position: 3, name: page.country_label, item: url },
      ],
    },
  ]
  const faqs = page.content?.faqs || []
  if (faqs.length > 0) {
    graph.push({
      '@type': 'FAQPage',
      '@id': `${url}#faq`,
      mainEntity: faqs.map((f) => ({
        '@type': 'Question', name: f.q,
        acceptedAnswer: { '@type': 'Answer', text: f.a },
      })),
    })
  }
  return { '@context': 'https://schema.org', '@graph': graph }
}
