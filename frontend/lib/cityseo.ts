// City pillar for the Local SEO universe, served at
// /{locale}/local-seo-services/{city-slug} (for example /en-in/local-seo-services/mumbai).
//
// It shares STORAGE with the industry x city leaf (both are rows in lpseo_pages, both
// come back from /public/lpseo/{slug}) but not its content schema: the city package
// ships catchments, an operating-model table, a 90 day plan and partner questions that
// have no counterpart on a leaf. So the shape lives here and the page is rendered by
// components/cityseo/CityPillar.tsx, discriminated on content.page_type.

export interface CityLink { anchor: string; url: string }
export interface CityQa { q: string; a: string }
export interface CityArea { name: string; detail: string }
export interface CityPair { title: string; detail: string }
export interface CityService { title: string; detail: string; num?: string }
export interface CityOperatingRow { area: string; single: string; multi: string }
export interface CityPhase { days: string; title: string; steps: string[] }
export interface CityMetric { label: string; detail: string }
export interface CityLinkGroup { title: string; links: CityLink[] }

export type CitySectionKey =
  | 'answer' | 'catchments' | 'scope' | 'ranking' | 'operating_model' | 'roadmap'
  | 'proof' | 'ai' | 'industry_links' | 'partner' | 'faq'

export interface CityContent {
  // Discriminator stamped by the importer. Everything else is optional because a
  // section renders only when the import filled it.
  page_type?: string

  page_id?: string
  primary_keyword?: string
  section_eyebrows?: Partial<Record<CitySectionKey, string>>

  // Hero
  hero_eyebrow?: string
  hero_copy?: string
  hero_image_alt?: string
  hero_image_caption?: string
  hero_trust_points?: string[]
  primary_cta?: string
  secondary_cta?: string

  // Direct answer
  direct_question?: string
  direct_answer?: string
  direct_answer_support?: string

  // Catchments
  catchment_heading?: string
  catchment_intro?: string
  catchment_areas?: CityArea[]

  // Service scope. `service_matrix` is the package's flat title list; `service_scope`
  // is the same nine areas WITH the descriptions recovered from the reference HTML.
  service_scope_heading?: string
  service_scope?: CityService[]
  service_matrix?: string[]

  // Relevance / distance / prominence
  ranking_heading?: string
  ranking_intro?: string[]
  ranking_factors?: CityPair[]

  // One location vs many
  operating_model_heading?: string
  operating_model_columns?: string[]
  operating_model_rows?: CityOperatingRow[]

  // 90 day plan
  roadmap_heading?: string
  roadmap_phases?: CityPhase[]
  roadmap_note?: string

  // Evidence and reporting
  proof_heading?: string
  proof_intro?: string
  proof_image_alt?: string
  proof_metrics?: CityMetric[]
  proof_asset_type?: string[]
  proof_asset_url?: string

  // AI search readiness
  ai_heading?: string
  ai_intro?: string[]
  ai_signals_heading?: string
  ai_entity_signals?: string[]
  ai_entity_plan?: string

  // Industry child pages
  industry_links_heading?: string
  industry_links_intro?: string
  industry_link_groups?: CityLinkGroup[]
  internal_links?: CityLink[]

  // Partner selection
  partner_heading?: string
  partner_questions?: CityPair[]

  // FAQs. Visible copy AND the only source of the FAQPage schema.
  faq_heading?: string
  faqs?: CityQa[]

  // Lead capture
  lead_eyebrow?: string
  lead_heading?: string
  lead_intro?: string
  lead_points?: string[]
  lead_consent_note?: string

  // Search-strategy context (kept from the package, not rendered as body copy).
  // `city_context` belongs here, not in the catchment section: it is the package's
  // one-paragraph summary of the catchment thesis, and its first sentence is
  // verbatim the catchment_heading, so rendering it echoes the H2 immediately below
  // it. The reference HTML never shows it either.
  city_context?: string
  secondary_keywords?: string[]
  industry_search_journeys?: string[]
  industry_entities?: string[]

  // Meta
  og_title?: string
  og_description?: string
  og_image?: string
  og_image_alt?: string
  hreflang_x_default?: string
  country_label?: string
  state_region?: string
  parent_url?: string
}

// Identity fields, all of which an LpseoPageData already carries.
export interface CityPageBase {
  slug: string
  country: string
  locale: string
  city_label: string
  city_slug: string
  meta_title: string
  meta_description: string
  h1: string
  canonical_url: string | null
  index_status: string
  quality_score: number | null
  published_at: string | null
  updated_at: string | null
}

export interface CityPageData extends CityPageBase {
  content: CityContent
}

// The router runs with trailingSlash:false, so every slashed URL 308-redirects.
// The content packages author canonicals WITH a slash, which made three tiers
// self-canonicalise to a redirect. The router wins: strip it at the edge so the
// canonical, og:url, hreflang and every JSON-LD @id agree with what actually serves.
export const noSlash = (u: string) => (u.length > 1 && u.endsWith('/') ? u.replace(/\/+$/, '') : u)

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

export const CITY_SEGMENT = 'local-seo-services'
export const cityPath = (locale: string, slug: string) => `/${locale}/${CITY_SEGMENT}/${slug}`
export const cityUrl = (locale: string, slug: string) => `${SITE_URL}${cityPath(locale, slug)}`
export const countryHubPath = (locale: string) => `/${locale}/${CITY_SEGMENT}`

// Same vocabulary as lpseo_pages.page_type ("leaf" / "industry_pillar" / "city_pillar").
// The public payload serialises `content` but not the column, so the discriminator
// the browser sees is content.page_type.
const CITY_PILLAR = 'city_pillar'

/** True when a page fetched from /public/lpseo/{slug} is a city pillar rather than an
 *  industry x city leaf. Both live in the same table; this is the discriminator. */
export function isCityPillar(page: { content?: unknown } | null | undefined): boolean {
  const t = (page?.content as { page_type?: string } | undefined)?.page_type
  return (t || '').trim().toLowerCase() === CITY_PILLAR
}

/** Narrow an lpSEO payload to the city-pillar shape. One cast, in one place, guarded
 *  by isCityPillar at the call site. */
export function asCityPage(page: CityPageBase & { content?: unknown }): CityPageData {
  return { ...page, content: (page.content || {}) as CityContent }
}

// Combined @graph: Organization, Service, WebPage, BreadcrumbList, and FAQPage when
// the page has FAQs.
//
// The FAQPage block is built FROM `content.faqs`, the exact array the component
// renders, so the visible answer and the structured answer are the same string by
// construction. The package's own `schema_json` column is never imported and never
// read here; a hand-written schema block is precisely how visible copy and markup
// drift apart.
export function buildCityJsonLd(page: CityPageData) {
  const url = noSlash(page.canonical_url || cityUrl(page.locale, page.slug))
  const orgId = `${SITE_URL}/#organization`
  const c = page.content || {}
  const region = c.state_region
  const country = c.country_label

  const graph: Record<string, unknown>[] = [
    {
      '@type': 'Organization',
      '@id': orgId,
      name: 'Pinzo',
      url: SITE_URL,
      logo: `${SITE_URL}/logo-horizontal-3.png`,
    },
    {
      // Kept in step with the rest of the family's schema baseline.
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      url: SITE_URL,
      name: 'Pinzo',
      publisher: { '@id': orgId },
    },
    {
      '@type': 'Service',
      '@id': `${url}#service`,
      name: `Local SEO Services in ${page.city_label}`,
      serviceType: 'Local search engine optimisation',
      provider: { '@id': orgId },
      // Truthful service area: the city, plus its region when the import states one.
      // No LocalBusiness and no address: Pinzo has no eligible location in this city.
      areaServed: [
        { '@type': 'City', name: page.city_label },
        ...(region ? [{ '@type': 'AdministrativeArea', name: region }] : []),
      ],
      audience: { '@type': 'BusinessAudience', audienceType: 'Local and multi location businesses' },
      description: page.meta_description,
      url,
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
      // Must mirror the visible trail exactly, node for node and URL for URL:
      // Home > Local SEO Services (global) > Country > City. The global node has NO
      // trailing slash, matching both the visible <Link href="/local-seo-services">
      // and the same node in cseo.ts / lpseo.ts; a trailing slash here would be a
      // different URL from the one the visitor can click.
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Home', item: SITE_URL },
        { '@type': 'ListItem', position: 2, name: 'Local SEO Services', item: `${SITE_URL}/${CITY_SEGMENT}` },
        ...(country
          ? [{ '@type': 'ListItem', position: 3, name: country, item: `${SITE_URL}${countryHubPath(page.locale)}` }]
          : []),
        { '@type': 'ListItem', position: country ? 4 : 3, name: page.city_label, item: url },
      ],
    },
  ]

  const faqs = c.faqs || []
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
