import { marketName } from '@/lib/markets'
// Local-SEO pSEO (industry x city) managed-service landing pages.
// Sibling of lib/pseo.ts — served under /{locale}/local-seo-services/, a SEPARATE
// backend table (lpseo_pages). Rendered by components/lpseo/LpseoLanding.tsx.

export interface LpseoPair { title: string; detail: string }
export interface LpseoQa { q: string; a: string }
export interface LpseoService { channel: string; work: string; outcome: string }
export interface LpseoCompareRow { point: string; agency: string; software: string; pinzo: string }
export interface LpseoPhase { days: string; title: string; steps: string[] }
export interface LpseoPlan {
  tag?: string; name: string; desc?: string; features: string[]
  cta_label?: string; cta_href?: string; featured?: boolean
}
export interface LpseoLink { anchor: string; url: string; section?: string }

// The link-capable section keys (mirror data-template-key in the template).
export type LpseoSection =
  | 'hero' | 'search-intent' | 'customer-journey' | 'service-matrix' | 'industry-strategy'
  | 'city-strategy' | 'single-multi' | 'ai-search' | 'deliverables' | 'workflow'
  | 'comparison-content' | 'engagement-model' | 'proof' | 'faqs' | 'related-links'

export interface LpseoContent {
  badge?: string
  hero_sub?: string
  primary_cta?: string
  secondary_cta?: string
  answer_heading?: string
  answer_block?: string
  intent_body?: string
  strategy_heading?: string
  strategy_body?: string
  city_body?: string
  reviews_body?: string
  example_review?: string
  example_reply?: string
  audit_summary_title?: string
  audit_summary_body?: string
  lead_heading?: string
  lead_sub?: string
  final_heading?: string
  final_sub?: string
  final_button?: string
  gbp_url?: string // cross-link to the sibling GBP-management page (cannibalisation split)
  // Lists
  topics?: string[]
  neighborhoods?: string[]
  single_points?: string[]
  multi_points?: string[]
  secondary_keywords?: string[]
  review_themes?: string[]
  // Structured
  search_intents?: LpseoPair[]
  value_props?: LpseoPair[]
  city_factors?: LpseoPair[]
  proof_points?: LpseoPair[]
  deliverables?: LpseoPair[]
  workflow_weeks?: LpseoPair[]
  audit_checklist?: LpseoPair[]
  journey_stages?: LpseoPair[]
  faqs?: LpseoQa[]
  services?: LpseoService[]
  comparison?: LpseoCompareRow[]
  workflow_phases?: LpseoPhase[]
  plans?: LpseoPlan[]
  related_pages?: { anchor: string; url: string }[]
  internal_links?: LpseoLink[]
  // Softer SEO/meta
  primary_keyword?: string
  region?: string
  last_updated?: string
  og_image?: string
  // 'industry_pillar' marks the country-level parent of an industry's city pages.
  page_type?: string
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

// The router runs with trailingSlash:false, so every slashed URL 308-redirects.
// The content packages author canonicals WITH a slash, which made three tiers
// self-canonicalise to a redirect. The router wins: strip it at the edge so the
// canonical, og:url, hreflang and every JSON-LD @id agree with what actually serves.
export const noSlash = (u: string) => (u.length > 1 && u.endsWith('/') ? u.replace(/\/+$/, '') : u)

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

export const LPSEO_SEGMENT = 'local-seo-services'
export const lpseoPath = (locale: string, slug: string) => `/${locale}/${LPSEO_SEGMENT}/${slug}`
export const industryHubPath = (locale: string, industrySlug: string) => `/${locale}/${LPSEO_SEGMENT}/${industrySlug}`
export const rootHubPath = (locale: string) => `/${locale}/${LPSEO_SEGMENT}`
export const lpseoUrl = (locale: string, slug: string) => `${SITE_URL}${lpseoPath(locale, slug)}`
export const industryHubUrl = (locale: string, industrySlug: string) => `${SITE_URL}${industryHubPath(locale, industrySlug)}`

export const localeToCountry = (locale: string) => (locale.split('-')[1] || 'in').toLowerCase()

export const INDUSTRY_PILLAR = 'industry_pillar'

/**
 * The industry pillar is the country-level parent of an industry's city pages, and
 * it lives in the SAME table on the SAME slug space: its slug IS the industry slug
 * (`dentists`, not `dentists-in-mumbai`). Because lpseo_pages requires a city, the
 * pillar stores the COUNTRY in city_label ("India"), so no page-type column exists
 * on the slim list payload. Slug identity is the discriminator that works for both
 * a full page and a list row; content.page_type confirms it when available.
 *
 * Every caller that treats a row as "a city" must exclude pillars, or a leaf page
 * ends up advertising its own parent as a neighbouring city.
 */
export const isLpseoPillar = (p: { slug: string; industry_slug: string; content?: LpseoContent }) =>
  (p.content?.page_type || '').trim().toLowerCase() === INDUSTRY_PILLAR || p.slug === p.industry_slug

// Match an imported city NAME ("Bengaluru") to a child page's city_slug.
export const citySlugify = (name: string) =>
  name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

// Single source of truth in lib/markets.ts; see the note there on why.
export const countryName = marketName

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
    // Industry-scoped list tag: a single page edit busts only that industry's leaves
    // (every leaf embeds this for siblings), not the whole corpus. Global 'lpseo-list'
    // stays for corpus-wide callers (sitemap, root/country hubs). Keep in sync with
    // the backend revalidate payload.
    const listTag = opts?.industry ? `lpseo-list:${opts.country ?? 'in'}:${opts.industry}` : 'lpseo-list'
    const res = await fetch(`${apiBase()}/public/lpseo${qs}`, { next: { revalidate: 31536000, tags: [listTag] }, signal: AbortSignal.timeout(10000) })
    if (!res.ok) return []
    const data = await res.json()
    return data.pages || []
  } catch {
    return []
  }
}

// ── Link-safety gate ─────────────────────────────────────────────────────────
// Guardrail, stated in every package: "do not link to a planned page that returns
// an error." The authored CSVs link the FULL planned set (every city, every
// industry) long before those pages exist, so 25 links were 404ing across the
// family. Content review will not catch this at scale: page 37 will link page 38.
//
// So the templates gate on data instead. `buildLiveFamilyPaths` returns the set of
// /{locale}/local-seo-services/* paths that are actually published and indexable;
// `isFamilyPath` marks the ones this gate governs. Anything outside the family
// (/pricing, /features, /gbp-management) is left alone — it is not ours to judge.
export interface LivePaths { slugs: string[]; industries: string[] }

/** Slugs of everything published+indexable in a market, for the link gate.
 *  Hits /paths, not the full list endpoint: the gate needs strings, and the list
 *  payload is ~190 KB for a market the size of India. */
async function fetchPaths(segment: 'pseo' | 'lpseo', country: string): Promise<LivePaths> {
  try {
    const res = await fetch(`${apiBase()}/public/${segment}/paths?country=${country}`, {
      next: { revalidate: 31536000, tags: [`${segment}-list`] },
      signal: AbortSignal.timeout(10000),
    })
    if (!res.ok) return { slugs: [], industries: [] }
    return await res.json()
  } catch {
    return { slugs: [], industries: [] }
  }
}

/** The set of family paths that actually resolve, for both page families. */
export async function getLiveFamilyPaths(country: string, locale: string): Promise<Set<string>> {
  const [lp, pp] = await Promise.all([fetchPaths('lpseo', country), fetchPaths('pseo', country)])
  const live = new Set<string>([rootHubPath(locale)])
  for (const s of lp.slugs) live.add(lpseoPath(locale, s))
  for (const i of lp.industries) live.add(industryHubPath(locale, i))
  for (const s of pp.slugs) live.add(`/${locale}/gbp-management/${s}`)
  for (const i of pp.industries) live.add(`/${locale}/gbp-management/${i}`)
  return live
}

export const isFamilyPath = (href: string) =>
  /^\/en-[a-z]{2}\/(local-seo-services|gbp-management)(\/|$)/.test(href)

/** True when a link may be rendered as an anchor: either it is outside the page
 *  family, or it points at something published. */
export function canLink(href: string, live: Set<string>): boolean {
  const clean = href.split('#')[0].replace(/\/+$/, '') || href
  if (!isFamilyPath(clean)) return true
  return live.has(clean)
}

// Combined @graph: Organization, Service, WebPage, BreadcrumbList (+ FAQPage when
// the page has FAQs). Local-SEO managed service (not the software app itself).
export function buildLpseoJsonLd(page: LpseoPageData) {
  const url = noSlash(lpseoUrl(page.locale, page.slug))
  const orgId = `${SITE_URL}/#organization`
  // Guardrail 7: areaServed is Country on an industry pillar and City only on a
  // city child, and the pillar's breadcrumb stops at the industry (it IS the
  // industry node, so a fourth "industry in city" level would be a self-link).
  const pillar = isLpseoPillar(page)
  const graph: any[] = [
    {
      '@type': 'Organization',
      '@id': orgId,
      name: 'Pinzo',
      url: SITE_URL,
      logo: `${SITE_URL}/logo-horizontal-3.png`,
    },
    {
      // Required by the schema baseline in every guardrails file in this family.
      // It was missing from this builder, so every leaf and the industry pillar
      // shipped a @graph one node short of spec.
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      url: SITE_URL,
      name: 'Pinzo',
      publisher: { '@id': orgId },
    },
    {
      '@type': 'Service',
      '@id': `${url}#service`,
      name: `Local SEO Services for ${page.industry_label} in ${page.city_label}`,
      serviceType: 'Managed local SEO services',
      provider: { '@id': orgId },
      areaServed: { '@type': pillar ? 'Country' : 'City', name: page.city_label },
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
      isPartOf: { '@id': `${SITE_URL}/#website` },
      about: { '@id': `${url}#service` },
      ...(page.published_at ? { datePublished: page.published_at } : {}),
      ...(page.updated_at ? { dateModified: page.updated_at } : {}),
    },
    {
      '@type': 'BreadcrumbList',
      '@id': `${url}#breadcrumb`,
      // Must mirror the visible trail exactly (schema/visible parity), which is
      // Home > Local SEO Services (global) > Country > Industry > leaf.
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        { '@type': 'ListItem', position: 2, name: 'Local SEO Services', item: `${SITE_URL}/local-seo-services` },
        { '@type': 'ListItem', position: 3, name: countryName(page.country), item: `${SITE_URL}${rootHubPath(page.locale)}` },
        { '@type': 'ListItem', position: 4, name: page.industry_label, item: pillar ? url : industryHubUrl(page.locale, page.industry_slug) },
        ...(pillar ? [] : [{ '@type': 'ListItem', position: 5, name: page.city_label, item: url }]),
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
