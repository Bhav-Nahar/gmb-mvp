import Link from 'next/link'
import {
  Sparkles, Check, MapPin, Building, Star, ArrowRight, RefreshCw, ShieldCheck, BarChart3, Bot, Globe, Compass, Phone,
  MessageSquare, ClipboardCheck, FileText,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import { SectionHeading, makeSafeLink } from '@/components/seo/sections'
import LpseoLeadForm from './LpseoLeadForm'
import {
  buildLpseoJsonLd, lpseoPath, industryHubPath, rootHubPath, isLpseoPillar, citySlugify,
  countryName,
  type LpseoPageData, type LpseoListItem, type LpseoSection,
} from '@/lib/lpseo'

/**
 * Local-SEO managed-service landing page. Server component: pure HTML/CSS, the only
 * client JS is the shared header and the lead form.
 *
 * Renders TWO page families off one template:
 *  - the industry x city LEAF  (/local-seo-services/dentists-in-mumbai)
 *  - the industry PILLAR       (/local-seo-services/dentists), the country-level
 *    parent that routes visitors and internal authority down to its city children.
 *
 * A pillar has no city. Because lpseo_pages requires one, it stores the COUNTRY in
 * city_label, so `city` below reads "India" and every city-shaped heading is swapped
 * for national phrasing rather than left saying "How India customers find dentists".
 *
 * Section order and copy mirror the approved reference templates. Every section the
 * template mandates renders on every page: CMS content fills it when the import
 * supplies it, otherwise the reference default does. Sections carry a
 * data-template-key so per-section internal links can be targeted from the CMS.
 *
 * Editorial guardrail 5.1: no Unicode en or em dash in any visible string here.
 */
export default function LpseoLanding({ page, siblings = [], livePaths = new Set<string>() }: {
  page: LpseoPageData; siblings?: LpseoListItem[]; livePaths?: Set<string>
}) {
  const c = page.content || {}
  const industry = page.industry_label
  const industryLc = industry.toLowerCase()
  const city = page.city_label
  const isPillar = isLpseoPillar(page)
  const jsonLd = buildLpseoJsonLd(page)
  const primaryCta = c.primary_cta || 'Get a Free Local SEO Audit'
  const secondaryCta = c.secondary_cta || 'View the 90-Day Plan'
  const whatsapp = 'https://wa.me/917715845972?text=' + encodeURIComponent(`Hi, I'd like a Pinzo local SEO audit for my ${industryLc} business in ${city}.`)

  // ── Internal linking ────────────────────────────────────────────────────────
  // Site-wide defaults (currently the cannibalisation cross-link to the sibling
  // GBP page when set) merge with per-page content.internal_links, keyed by the
  // section each should render under. Any section key can carry links.
  // Authored URLs carry trailing slashes (the packages specify them) but the router
  // has trailingSlash:false, so every one 308-redirects. Normalise at render so an
  // internal link never costs a redirect hop.
  // Renders an anchor only when the destination exists; otherwise plain text.
  // Guardrail: never link a planned page that 404s.
  const SafeLink = makeSafeLink(livePaths)

  const normaliseHref = (u: string) => (u.length > 1 && u.endsWith('/') && !u.includes('#') ? u.replace(/\/+$/, '') : u)

  const gbp = c.gbp_url
  const defaultLinks: Partial<Record<LpseoSection, { anchor: string; href: string }[]>> = {
    'service-matrix': gbp ? [{ anchor: `Google Business Profile management for ${industryLc}`, href: gbp }] : [],
    'related-links': gbp ? [{ anchor: isPillar ? `GBP management for ${industryLc}` : `GBP management for ${industry} in ${city}`, href: gbp }] : [],
  }
  const RelatedLinks = ({ section }: { section: LpseoSection }) => {
    const cms = (c.internal_links || []).filter((l) => l.section === section).map((l) => ({ anchor: l.anchor, href: l.url }))
    const seen = new Set<string>()
    const links = [...(defaultLinks[section] || []), ...cms].filter((l) => l.href && !seen.has(l.href) && seen.add(l.href))
    if (links.length === 0) return null
    return (
      <p className="text-center text-sm text-muted-foreground">
        Related:{' '}
        {links.map((l, i) => (
          <span key={l.href}>
            {i > 0 && ' · '}
            <SafeLink href={l.href} className="font-semibold text-primary underline-offset-4 hover:underline">{l.anchor}</SafeLink>
          </span>
        ))}
      </p>
    )
  }


  const HeroCtas = () => (
    <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
      <a href="#free-audit" className="flex w-full min-w-[240px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 sm:w-auto">
        {primaryCta} <ArrowRight className="h-4 w-4" />
      </a>
      <a href="#plan" className="flex w-full min-w-[180px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
        {secondaryCta}
      </a>
    </div>
  )

  // Illustrative "dentist near me"-style geo-grid: decorative, clearly labelled.
  const GEO = [
    [11, 12, 8, 7, 10, 15, 18], [10, 9, 5, 4, 7, 12, 16], [8, 6, 3, 2, 5, 9, 13],
    [7, 4, 2, 1, 3, 8, 12], [10, 7, 5, 3, 6, 10, 15], [14, 11, 8, 7, 10, 14, 19], [18, 16, 12, 11, 15, 19, 21],
  ]
  const cellColor = (v: number) => v <= 3 ? '#22c55e' : v <= 6 ? '#84cc16' : v <= 10 ? '#f59e0b' : v <= 15 ? '#fb923c' : '#f43f5e'

  // ── Reference-template defaults ─────────────────────────────────────────────
  // ONE RULE, applied to every list on this page: a section is filled entirely by
  // the import, or entirely by the reference default. Never a blend.
  //
  // Blending was a real bug. The package CSV's `solutions` column is two-part
  // ("SEO area :: what Pinzo manages") while the reference rows carry a third
  // "why it matters" field, so appending one to the other produced a service
  // matrix whose first ten rows had an empty third column and whose last three
  // did not. Same class of breakage hit the sample-audit checklist. Whole-list
  // substitution makes a ragged section structurally impossible.
  const orDefault = <T,>(cms: T[] | undefined, defaults: T[]): T[] =>
    (cms && cms.length > 0 ? cms : defaults)

  const answerHeading = c.answer_heading || `What are local SEO services for ${industryLc} in ${city}?`
  const answerBlock = c.answer_block || `Local SEO services for ${industryLc} in ${city} improve visibility when nearby customers search on Google Maps, Google Search and AI platforms. The work combines Google Business Profile management, service-page SEO, citation consistency, review workflows, local schema, technical SEO, local authority building and neighbourhood-level rank tracking, so more nearby customers discover, trust and contact the business.`

  const trust = ['Single or multiple locations', 'Privacy-conscious review support', 'No ranking guarantees']

  const proofPoints = orDefault(c.proof_points, [
    { title: 'Google Maps visibility', detail: 'Improve local pack presence for relevant nearby searches.' },
    { title: 'Website SEO', detail: 'Strengthen service, business and location-level content.' },
    { title: 'Review and reputation support', detail: 'Build trust with better review coverage and response workflows.' },
    { title: 'AI search visibility', detail: 'Keep business details clear, answer real questions and strengthen supporting sources.' },
  ])

  const journey = orDefault(c.journey_stages, [
    { title: 'Search', detail: 'Local or service-specific query' },
    { title: 'Compare', detail: 'Maps, reviews and business details' },
    { title: 'Evaluate', detail: 'Service page and team credibility' },
    { title: 'Contact', detail: 'Call, WhatsApp or form enquiry' },
    { title: 'Book', detail: 'Appointment, visit or order' },
  ])

  // Guardrail 6.12: the city section must explain travel, proximity, access,
  // branch accuracy and why a real location page is not a doorway page.
  const cityFactors = orDefault(c.city_factors, [
    { title: 'Access and convenience', detail: 'Travel time, transport links, parking and opening hours change which nearby option a customer picks.' },
    { title: 'Service travel radius', detail: 'High-value or specialist work draws customers from further away. Urgent work has a much smaller catchment.' },
    { title: 'Branch-level accuracy', detail: 'Each location needs its own services, staff availability, hours and contact route, not a copy of the main page.' },
    { title: 'Location pages, not doorway pages', detail: 'A page is only published for an area the business can genuinely serve from a real location.' },
  ])

  // City children. A leaf shows them as "other cities"; for the pillar they ARE the
  // routing block, which is the pillar's whole job. Pillars are filtered out first:
  // the parent lives in the same table and would otherwise turn up as a neighbouring
  // city on every one of its own children.
  const cityChildren = siblings.filter((s) => s.slug !== page.slug && s.slug !== s.industry_slug)
  const childByCitySlug = new Map(cityChildren.map((s) => [s.city_slug, s]))
  // Pillar chip row, under the same ONE RULE: the names come entirely from the import
  // or entirely from the live child list. A name is only ever a link when a published
  // child page for that city actually exists (guardrail 12: no links to planned pages).
  const pillarCities = orDefault(c.neighborhoods, cityChildren.map((s) => s.city_label))

  const demandGroups = orDefault(c.value_props, [
    { title: 'Planned high-value services', detail: 'These need deeper education, visible credentials and a wider catchment. Customers research before they contact anyone.' },
    { title: 'Urgent and immediate needs', detail: 'These turn on availability, proximity and an obvious contact route. The decision happens in minutes.' },
    { title: 'Repeat and routine visits', detail: 'These depend on convenient access, opening hours, continuity and trust built at the location level.' },
  ])

  // Guardrail 6.10: the matrix must cover all ten areas, so the fallback does too.
  const services = orDefault(c.services, [
    { channel: 'Google Maps and GBP', work: 'Categories, services, descriptions, photos, posts, booking links, Q and A, attributes and profile completeness.', outcome: 'Improves visibility for nearby searches while giving customers accurate information.' },
    { channel: 'Website SEO', work: 'Metadata, page structure, internal links, location relevance, content quality, conversion elements and structured data.', outcome: 'Wins visibility beyond Google Maps and gives customers a stronger reason to enquire.' },
    { channel: 'Service-page SEO', work: `Search-focused pages for the priority services this ${industryLc} business genuinely offers.`, outcome: 'Captures high-intent demand and answers detailed questions before the enquiry.' },
    { channel: 'Reviews and reputation', work: 'Review-generation workflows, response guidance, theme analysis and location-level monitoring.', outcome: 'Builds trust and helps customers compare with more confidence.' },
    { channel: 'Citations and consistency', work: 'Name, address, phone, hours and branch information across relevant directories and platforms.', outcome: 'Reduces conflicting information and supports local authority.' },
    { channel: 'Local authority and links', work: 'Relevant industry, community, association, media and local business opportunities.', outcome: 'Strengthens third-party validation without relying on low-quality directory volume.' },
    { channel: 'Technical SEO', work: 'Crawlability, indexation, Core Web Vitals, canonical tags, mobile performance, schema and duplicate-content control.', outcome: 'Ensures service and location content can be crawled, understood and used by search systems.' },
    { channel: 'Geo-grid and local rank tracking', work: 'Neighbourhood-level visibility tracking, competitor comparison and location-specific ranking reports.', outcome: 'Shows where the business is visible and where proximity or competition limits coverage.' },
    { channel: 'Conversion tracking', work: 'Calls, forms, WhatsApp clicks, booking actions, UTM attribution and landing-page performance.', outcome: 'Connects visibility work to real enquiries rather than rankings alone.' },
    { channel: 'AI search visibility', work: 'Consistent business details, clear service information, direct answers, supporting sources and visibility checks.', outcome: 'Makes the business easier for AI search tools to understand. It does not guarantee a mention or recommendation.' },
  ])
  // The package CSV supplies "area :: what Pinzo manages" with no third part, so the
  // relevance column appears only when EVERY row can fill it. Half-empty beats ragged:
  // `some` here let a single 3-part row open a column the other nine rendered blank.
  const showRelevance = services.every((s) => s.outcome)
  const cols = showRelevance ? 'grid-cols-[220px_1fr_1fr]' : 'grid-cols-[240px_1fr]'

  // Guardrail 6.14: AI search support, described without promising a mention.
  const aiPillars = [
    { tag: 'Entity consistency', title: 'Keep business, staff, service and location details aligned', detail: 'Names, qualifications, services, addresses and branch details should match across the website, profiles and trusted sources.' },
    { tag: 'Structured answers', title: 'Answer real customer questions clearly', detail: 'Use concise, factual sections for service suitability, process, cost factors, booking steps and availability.' },
    { tag: 'Citation readiness', title: 'Strengthen evidence that search systems can retrieve', detail: 'Build useful pages, relevant third-party mentions, quality reviews and local authority around the business and its team.' },
    { tag: 'Visibility testing', title: 'Track how the business appears across AI search journeys', detail: 'Review target prompts, mentions, citations, factual accuracy and assisted visits, without claiming guaranteed recommendations.' },
  ]
  const aiSurfaces = ['Google AI Overviews', 'ChatGPT', 'Gemini', 'Perplexity', 'Copilot']

  const deliverables = orDefault(c.deliverables, [
    { title: 'Location action plan', detail: 'Prioritised tasks by location, service and local opportunity.' },
    { title: 'GBP optimisation', detail: 'Profile improvements, posts, services, photos and listing health checks.' },
    { title: 'Website and service SEO', detail: 'On-page improvements, content briefs, internal links and technical recommendations.' },
    { title: 'Review and reputation insights', detail: 'Review workflows, sentiment, service themes and response support.' },
    { title: 'Geo-grid and competitor tracking', detail: 'Visibility movement, locality gaps and competitor changes.' },
    { title: 'AI search monitoring', detail: 'Prompt coverage, mentions, citations and factual accuracy checks.' },
    { title: 'Conversion reporting', detail: 'Calls, forms, WhatsApp actions, landing-page activity and lead quality signals.' },
    { title: 'Monthly performance report', detail: 'Clear progress summary with completed work, outcomes and next priorities.' },
    { title: 'Strategy review', detail: 'Review progress, capacity, service priorities and future opportunities.' },
  ])

  const phases = orDefault(c.workflow_phases, [
    { days: 'Days 1 to 30', title: 'Audit and prioritise', steps: ['Review Google Business Profile, website, reviews and citations', `Map ${industryLc} keywords, competitors and customer catchment`, 'Set up tracking, baseline rankings and AI visibility tests'] },
    { days: 'Days 31 to 60', title: 'Build the foundation', steps: ['Improve profiles, service information and conversion actions', 'Optimise priority service and location pages', 'Start review, citation and technical improvement work'] },
    { days: 'Days 61 to 90', title: 'Expand and measure', steps: ['Track locality and service-level visibility', 'Improve internal links, authority and AI search coverage', 'Review lead quality and prioritise the next growth cycle'] },
  ])

  // Guardrail 6.17: the six mandated comparison dimensions, kept fair to the
  // agency-only and software-only models.
  const comparison = orDefault(c.comparison, [
    { point: 'Strategy', agency: 'Usually included', software: 'Internal team required', pinzo: 'Included' },
    { point: 'Execution', agency: 'Usually included', software: 'Internal team required', pinzo: 'Included' },
    { point: 'Location-level visibility', agency: 'Varies', software: 'Available in the platform', pinzo: 'Available with managed execution' },
    { point: 'Multi-location governance', agency: 'Depends on agency capability', software: 'Possible with internal ownership', pinzo: 'Central control with branch-level reporting' },
    { point: 'AI search monitoring', agency: 'Varies', software: 'Depends on tool capability', pinzo: 'Integrated into the strategy' },
    { point: 'Reporting transparency', agency: 'Varies', software: 'High if the team uses the tool consistently', pinzo: 'Platform visibility plus service reporting' },
    { point: 'Conversion tracking', agency: 'Varies by reporting setup', software: 'Requires manual integration', pinzo: 'Integrated call, form and lead tracking' },
    { point: 'Review management', agency: 'Usually manual', software: 'Tool provided, team executes', pinzo: 'Workflows with response support' },
  ])

  const plans = orDefault(c.plans, [
    { tag: 'Software', name: 'Pinzo Platform', desc: `For in-house teams or agencies that want the tools and will execute internally.`, features: ['GBP management and audit workflows', 'Reviews, posts and local rank tracking', 'AI visibility recommendations'], cta_label: 'Start Free Trial', cta_href: '/#pricing' },
    { tag: 'Managed service', name: 'Pinzo Managed Local SEO', desc: 'For businesses that want strategy, execution and reporting handled with platform visibility.', features: ['Maps, website, reviews and AI search work', 'Monthly implementation and reporting', 'Lead and visibility measurement'], cta_label: 'Request Proposal', cta_href: '#free-audit', featured: true },
    { tag: 'Multi-location', name: `Pinzo for ${industry} Groups`, desc: 'For brands that need central governance, branch-level execution and scalable reporting.', features: ['Location dashboards and performance comparison', 'Review, content and listing governance', 'Structured rollout across branches'], cta_label: 'Book Consultation', cta_href: '#free-audit' },
  ])

  const auditChecklist = orDefault(c.audit_checklist, [
    { title: 'Google Business Profile completeness', detail: 'Needs work' },
    { title: 'Service-page coverage', detail: 'Gap found' },
    { title: 'Review-theme visibility', detail: 'Tracked' },
    { title: 'Geo-grid baseline', detail: 'Available' },
    { title: 'AI prompt coverage', detail: 'Limited' },
  ])


  // ── Method summary (leaf only) ──────────────────────────────────────────────
  // The 90-day plan, deliverables, AI approach, buying-model comparison and
  // engagement models are COMPANY-level: identical word for word on the pillar and
  // on every city leaf, because how Pinzo works does not change by city. Measured
  // at 100% overlap on four of the five. Rendering them in full on 36 city pages
  // would publish 36 copies of one page.
  //
  // The leaf therefore shows a derived one-line summary of each and links up to the
  // pillar for the detail. Derived, not hand-written: the text is generated from
  // the very arrays the pillar renders, so it stays true and cannot drift.
  const pillarHref = industryHubPath(page.locale, page.industry_slug)
  const methodSummary = [
    phases.length > 0 && {
      title: 'The first 90 days', href: `${pillarHref}#plan`,
      detail: `${phases.length} phases: ${phases.map((x) => x.title).join(', ')}.`,
    },
    deliverables.length > 0 && {
      title: 'What you receive each month', href: `${pillarHref}#deliverables`,
      detail: `${deliverables.length} recurring deliverables, from ${deliverables[0].title.toLowerCase()} to ${deliverables[deliverables.length - 1].title.toLowerCase()}.`,
    },
    {
      title: 'AI search visibility', href: `${pillarHref}#ai-search`,
      detail: `Entity consistency, direct answers and citation readiness across ${aiSurfaces.length} AI search surfaces. No mention is ever guaranteed.`,
    },
    comparison.length > 0 && {
      title: 'Agency, software or managed', href: `${pillarHref}#compare`,
      detail: `${comparison.length} dimensions compared, from ${comparison[0].point.toLowerCase()} to ${comparison[comparison.length - 1].point.toLowerCase()}.`,
    },
    plans.length > 0 && {
      title: 'Engagement models', href: `${pillarHref}#plans`,
      detail: `${plans.map((x) => x.name).join(', ')}.`,
    },
    demandGroups.length > 0 && {
      title: `${industry} content strategy`, href: `${pillarHref}#strategy`,
      detail: `${demandGroups.map((x) => x.title.toLowerCase()).join(', ')}.`,
    },
  ].filter(Boolean) as { title: string; href: string; detail: string }[]

  const sampleAssets = [
    { title: 'Sample monthly visibility report', detail: 'A sample reporting view for local rankings, service-page coverage, reviews and conversion actions.' },
    { title: 'Sample local SEO audit', detail: 'An illustrative audit format showing the checks used to prioritise local visibility work.' },
    { title: 'Example geo-grid analysis', detail: `A sample catchment view showing how rankings can vary across the areas around a ${industryLc} location.` },
    { title: 'Sample review theme analysis', detail: 'A sample analysis of service, trust, convenience and customer-experience themes found in public reviews.' },
    { title: 'Pinzo platform walkthrough', detail: 'A guided overview of the audit, location dashboard, AI visibility and reporting workflow.' },
  ]

  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />

      <MarketingHeader />

      {/* Breadcrumb (matches BreadcrumbList schema) */}
      <nav aria-label="Breadcrumb" className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 lg:px-8">
        <ol className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
          <li><Link href="/" className="hover:text-foreground">Home</Link></li>
          <li aria-hidden>/</li>
          {/* "Local SEO Services" is the GLOBAL pillar and the country node is named
              after the country. Previously this anchor pointed at the country pillar
              here but at the global pillar on the country and city pages: one label,
              two destinations. */}
          <li><Link href="/local-seo-services" className="hover:text-foreground">Local SEO Services</Link></li>
          <li aria-hidden>/</li>
          <li><Link href={rootHubPath(page.locale)} className="hover:text-foreground">{countryName(page.country)}</Link></li>
          <li aria-hidden>/</li>
          {/* The pillar IS the industry node, so its trail stops there. */}
          {isPillar ? (
            <li className="text-foreground">{industry}</li>
          ) : (
            <>
              <li><Link href={industryHubPath(page.locale, page.industry_slug)} className="hover:text-foreground">{industry}</Link></li>
              <li aria-hidden>/</li>
              <li className="text-foreground">{city}</li>
            </>
          )}
        </ol>
      </nav>

      {/* 1. HERO */}
      <section data-template-key="hero" className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <div className="space-y-6">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            <span>{c.badge || `Managed Local SEO + Pinzo Platform`}</span>
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{page.h1}</h1>
          <p className="max-w-xl text-base text-muted-foreground sm:text-lg">
            {c.hero_sub || `Help nearby customers discover, trust and contact your ${industryLc} business across Google Maps, local organic search and AI recommendations. Pinzo combines specialist execution with location-level rank tracking, reviews, profile management and reporting.`}
          </p>
          <HeroCtas />
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 text-[11px] font-semibold text-muted-foreground">
            {trust.map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
            ))}
          </div>
          <RelatedLinks section="hero" />
        </div>

        {/* Illustrative visibility dashboard */}
        <div
          className="rounded-3xl border border-border bg-card p-4 shadow-xl"
          role="img"
          aria-label={`Illustrative Pinzo dashboard showing ${industryLc} local visibility${city ? ` in ${city}` : ''}. Sample data, not a client result.`}
        >
          <div className="flex items-center justify-between px-1 pb-3">
            <div className="flex items-center gap-2 text-xs font-bold text-foreground"><BarChart3 className="h-4 w-4 text-primary" /> Visibility Command Center</div>
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Illustrative</span>
          </div>
          <div className="mb-3 flex items-center justify-between rounded-2xl border border-border bg-background p-4">
            <div>
              <p className="text-[11px] text-muted-foreground">Local SEO opportunity score</p>
              <p className="mt-0.5 text-sm font-bold text-foreground">High-impact fixes identified</p>
            </div>
            <div className="flex h-14 w-14 items-center justify-center rounded-full border-4 border-primary/25 text-lg font-extrabold text-foreground">72</div>
          </div>
          <div className="rounded-2xl border border-border bg-background p-4">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-bold text-foreground">&ldquo;{industryLc} near me&rdquo; visibility</span>
              <span className="text-[10px] text-muted-foreground">7×7 grid</span>
            </div>
            <div className="grid grid-cols-7 gap-1.5" aria-hidden>
              {GEO.flatMap((r, ri) => r.map((v, ci) => (
                <span key={`${ri}-${ci}`} className="flex aspect-square items-center justify-center rounded-md text-[10px] font-extrabold text-slate-900" style={{ backgroundColor: cellColor(v) }}>{v > 20 ? '20+' : v}</span>
              )))}
            </div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            {[['GBP health', 'Needs action'], ['Local pages', 'Gap found'], ['Review themes', 'Analysed']].map(([k, v]) => (
              <div key={k} className="rounded-xl border border-border bg-background p-3">
                <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{k}</p>
                <p className="text-xs font-bold text-foreground">{v}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 2. PROOF STRIP */}
      <section className="pb-10">
        <div className="mx-auto grid max-w-6xl grid-cols-1 gap-3 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
          {proofPoints.map((p) => (
            <div key={p.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
              <p className="text-sm font-bold text-foreground">{p.title}</p>
              {p.detail && <p className="mt-1 text-xs text-muted-foreground">{p.detail}</p>}
            </div>
          ))}
        </div>
      </section>

      {/* 3. DIRECT ANSWER (AEO) */}
      <section className="pb-6">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-primary">Direct answer</p>
            <h2 className="mb-3 text-lg font-bold text-foreground">{answerHeading}</h2>
            <p className="leading-relaxed text-muted-foreground">{answerBlock}</p>
          </div>
        </div>
      </section>

      {/* 4. SEARCH INTENT */}
      {(c.search_intents || []).length > 0 && (
        <section data-template-key="search-intent" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading
              eyebrow="Search behaviour"
              title={isPillar ? `How customers find ${industryLc} through local search in ${city}` : `How ${city} customers find ${industryLc} through local search`}
              sub={c.intent_body || 'A useful page must reflect the decision behind the query, not just repeat the keyword. Pinzo maps every high-value search to the right local asset and conversion action.'}
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {(c.search_intents || []).map((it, i) => (
                <article key={it.title} className="flex h-full flex-col rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <span className="mb-3 flex h-8 w-8 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-xs font-extrabold text-primary">{i + 1}</span>
                  <h3 className="text-sm font-bold text-foreground">{it.title}</h3>
                  {it.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{it.detail}</p>}
                </article>
              ))}
            </div>
            <RelatedLinks section="search-intent" />
          </div>
        </section>
      )}

      {/* 5. CUSTOMER JOURNEY */}
      <section data-template-key="customer-journey" className="py-12">
        <div className="mx-auto max-w-6xl space-y-6 px-4 sm:px-6 lg:px-8">
          <p className="text-center text-[11px] font-bold uppercase tracking-wider text-primary">Customer journey</p>
          <ol className="grid grid-cols-1 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {journey.map((s, i) => (
              <li key={s.title} className="rounded-2xl border border-border bg-card p-5 text-center shadow-sm">
                <span className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{String(i + 1).padStart(2, '0')}</span>
                <p className="mt-1 text-sm font-bold text-foreground">{s.title}</p>
                {s.detail && <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{s.detail}</p>}
              </li>
            ))}
          </ol>
          <RelatedLinks section="customer-journey" />
        </div>
      </section>

      {/* 6. SERVICE MATRIX */}
      <section data-template-key="service-matrix" className="border-y border-border/40 bg-muted/10 py-16">
        <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
          <SectionHeading eyebrow="Complete service matrix" title={`What is included in our local SEO services for ${industryLc}`} sub="One connected system across Google Maps, the website, reviews, local rankings and AI search. One set of priorities, one operating rhythm and one clear report." />
          <div className="overflow-x-auto">
          <div className="min-w-[720px] overflow-hidden rounded-3xl border border-border shadow-sm">
            <div className={`grid border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground ${cols}`}>
              <div className="p-3.5">SEO area</div>
              <div className="p-3.5">What Pinzo manages</div>
              {showRelevance && <div className="p-3.5">Why it matters</div>}
            </div>
            {services.map((s, i) => (
              <div key={s.channel} className={`grid items-start border-b border-border last:border-0 ${cols} ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                <div className="flex items-center gap-2.5 p-3.5 text-sm font-bold text-foreground">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Globe className="h-4 w-4 text-primary" /></span>
                  {s.channel}
                </div>
                <p className="p-3.5 text-xs leading-relaxed text-muted-foreground">{s.work}</p>
                {showRelevance && <p className="p-3.5 text-xs leading-relaxed text-foreground">{s.outcome}</p>}
              </div>
            ))}
          </div>
          </div>
          <RelatedLinks section="service-matrix" />
        </div>
      </section>

      {/* 7. INDUSTRY STRATEGY (pillar only: the demand groups are industry-level,
          identical on every city leaf. Leaves get the summary link instead.) */}
      {isPillar && (
      <section data-template-key="industry-strategy" id="strategy" className="py-16">
        <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow="Service strategy"
            title={c.strategy_heading || `Content strategy for high-intent ${industryLc} searches`}
            sub={c.strategy_body || `Each service page should answer the real decision question, show who delivers the work and make the next step easy. Group the pages by how customers actually choose.`}
          />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {demandGroups.map((v, i) => (
              <article key={v.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-xs font-extrabold text-primary">{String.fromCharCode(65 + i)}</span>
                <h3 className="mt-3 text-sm font-bold text-foreground">{v.title}</h3>
                {v.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{v.detail}</p>}
              </article>
            ))}
          </div>
          {(c.topics || []).length > 0 && (
            <div className="flex flex-wrap items-center justify-center gap-2">
              {(c.topics || []).map((t) => (
                <span key={t} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-semibold text-foreground shadow-sm">{t}</span>
              ))}
            </div>
          )}
          {/* secondary_keywords stays out of the visible page on purpose: a chip
              wall of near-duplicate phrases reads as stuffing (guardrail 5.2). */}
          <RelatedLinks section="industry-strategy" />
        </div>
      </section>
      )}

      {/* 8. CITY AND CATCHMENT STRATEGY */}
      <section data-template-key="city-strategy" className="py-16">
        <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
          <SectionHeading
            eyebrow={isPillar ? `${city} market strategy` : `${city} relevance`}
            title={isPillar ? `City and catchment strategy for ${industryLc} in ${city}` : `Locality and catchment strategy for ${city} ${industryLc}`}
            sub={c.city_body || (isPillar
              ? `Search behaviour changes across ${city} because competition, transport, local demand and travel patterns differ by market. Pinzo builds a city page only where the business can genuinely serve customers from a real location.`
              : `${city} searches can change by neighbourhood because distance, traffic and convenience affect choice. Pinzo maps visibility around the genuine service area and only creates location content where the business can serve customers meaningfully.`)}
          />
          {isPillar ? (
            pillarCities.length > 0 && (
              <div className="space-y-3 text-center">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Priority cities in {city}</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {pillarCities.map((n) => {
                    const child = childByCitySlug.get(citySlugify(n))
                    const chip = 'flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm'
                    return child ? (
                      <Link key={n} href={lpseoPath(child.locale, child.slug)} className={`${chip} transition-colors hover:border-primary/40 hover:text-primary`}>
                        <MapPin className="h-3.5 w-3.5 text-primary" />{n}
                      </Link>
                    ) : (
                      <span key={n} className={chip}><MapPin className="h-3.5 w-3.5 text-primary" />{n}</span>
                    )
                  })}
                </div>
                <p className="mx-auto max-w-2xl text-xs text-muted-foreground">A city is linked only once a substantial page exists for that market. Pinzo does not publish thin city pages that imply a presence the business does not have.</p>
              </div>
            )
          ) : (
            (c.neighborhoods || []).length > 0 && (
              <div className="space-y-3 text-center">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Areas customers search in {city}</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {(c.neighborhoods || []).map((n) => (
                    <span key={n} className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm"><MapPin className="h-3.5 w-3.5 text-primary" />{n}</span>
                  ))}
                </div>
                <p className="mx-auto max-w-2xl text-xs text-muted-foreground">Area names are only useful when the business can genuinely serve them. Pinzo does not publish suburb pages for locations that do not exist.</p>
              </div>
            )
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {cityFactors.map((f) => (
              <article key={f.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <Compass className="mb-2.5 h-[18px] w-[18px] text-primary" />
                <h3 className="text-sm font-bold text-foreground">{f.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{f.detail}</p>
              </article>
            ))}
          </div>
          {/* The pillar already links every child above, so it skips this block. */}
          {!isPillar && cityChildren.length > 0 && (
            <div className="space-y-3 text-center">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{industry} in other cities</p>
              <div className="flex flex-wrap items-center justify-center gap-2">
                {cityChildren.map((s) => (
                  <Link key={s.slug} href={lpseoPath(s.locale, s.slug)} className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary"><MapPin className="h-3.5 w-3.5 text-primary" />{s.city_label}</Link>
                ))}
              </div>
            </div>
          )}
          <RelatedLinks section="city-strategy" />
        </div>
      </section>

      {/* 9. SINGLE VS MULTI LOCATION */}
      <section data-template-key="single-multi" className="border-y border-border/40 bg-muted/10 py-16">
        <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
          <SectionHeading eyebrow="Operating models" title={`Local SEO for single and multi-location ${industryLc}`} sub="One location and a branch network need different governance, different pages and different reporting." />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              <div className="mb-4 flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><MapPin className="h-[18px] w-[18px] text-primary" /></div>
                <h3 className="text-sm font-bold text-foreground">Single location</h3>
              </div>
              <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                {orDefault(c.single_points, [
                  'One primary Google Business Profile and one realistic catchment',
                  'Service pages that match what the business actually offers',
                  'Local review growth, photos and booking actions',
                  'Clear reporting on calls, forms and visibility trends',
                ]).map((p) => (
                  <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{p}</li>
                ))}
              </ul>
            </div>
            <div className="rounded-2xl border-2 border-primary/40 bg-card p-6 shadow-md">
              <div className="mb-4 flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Building className="h-[18px] w-[18px] text-primary" /></div>
                <h3 className="text-sm font-bold text-foreground">Multi-location &amp; groups</h3>
              </div>
              <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                {orDefault(c.multi_points, [
                  'Central governance with location-level execution',
                  'Unique branch pages with real staff and service availability',
                  'Branch-level reviews, photos, booking links and local competitors',
                  'Location dashboards, rankings and performance comparisons',
                ]).map((p) => (
                  <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />{p}</li>
                ))}
              </ul>
            </div>
          </div>
          <RelatedLinks section="single-multi" />
        </div>
      </section>

      {/* 10-14. COMPANY-LEVEL SECTIONS
          Rendered in full on the industry pillar. On a city leaf they collapse to a
          derived summary that links up, because the copy is identical on every leaf
          and would otherwise duplicate the pillar 36 times over. */}
      {isPillar ? (
        <>
        {/* 10. AI SEARCH VISIBILITY */}
        <section data-template-key="ai-search" id="ai-search" className="py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="AI search optimisation" title={`How Pinzo supports AI search visibility for ${industryLc}`} sub="AI search does not replace local SEO. It makes accurate business details, useful service content, structured data and trustworthy outside references even more important." />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {aiPillars.map((p) => (
                <article key={p.tag} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <span className="text-[10px] font-extrabold uppercase tracking-widest text-primary">{p.tag}</span>
                  <h3 className="mt-1.5 text-sm font-bold text-foreground">{p.title}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{p.detail}</p>
                </article>
              ))}
            </div>
            <div className="mx-auto max-w-3xl space-y-3 rounded-2xl border border-border bg-card p-6 text-center shadow-sm">
              <h3 className="text-sm font-bold text-foreground">AI search surfaces to monitor</h3>
              <p className="text-xs leading-relaxed text-muted-foreground">Pinzo tests relevant customer discovery journeys across major AI-powered search environments while keeping Google Maps and local organic search as the foundation.</p>
              <div className="flex flex-wrap items-center justify-center gap-2">
                {aiSurfaces.map((s) => (
                  <span key={s} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs font-bold text-foreground"><Bot className="h-3.5 w-3.5 text-primary" />{s}</span>
                ))}
              </div>
              <p className="text-[11px] text-muted-foreground">There is no special AI schema. Strong SEO foundations, appropriate structured data, reliable entities, useful content and third-party validation support visibility. A mention or recommendation cannot be guaranteed.</p>
            </div>
            <RelatedLinks section="ai-search" />
          </div>
        </section>

        {/* 11. MONTHLY DELIVERABLES */}
        <section data-template-key="deliverables" id="deliverables" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Monthly deliverables" title="What you receive each month" sub="Each month you see what was completed, what changed and what should happen next. Managed service should mean clear execution, not a generic ranking PDF." />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {deliverables.map((d) => (
                <article key={d.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><RefreshCw className="h-[18px] w-[18px] text-primary" /></div>
                  <h3 className="text-sm font-bold text-foreground">{d.title}</h3>
                  {d.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{d.detail}</p>}
                </article>
              ))}
            </div>
            {(c.workflow_weeks || []).length > 0 && (
              <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <h3 className="mb-4 text-sm font-bold text-foreground">Monthly operating rhythm</h3>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  {(c.workflow_weeks || []).map((w) => (
                    <div key={w.title}>
                      <p className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{w.title}</p>
                      <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{w.detail}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <RelatedLinks section="deliverables" />
          </div>
        </section>

        {/* 12. FIRST 90 DAYS */}
        <section data-template-key="workflow" id="plan" className="py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Implementation process" title={`Our 90-day local SEO plan for ${industryLc}`} sub="The first 90 days are used to fix the basics, strengthen priority pages and set up reliable measurement. Timelines depend on the current website, competition and approvals." />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {phases.map((ph, i) => (
                <article key={ph.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <span className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{String(i + 1).padStart(2, '0')}</span>
                  {ph.days && <p className="mt-1 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{ph.days}</p>}
                  <h3 className="mt-2 text-sm font-bold text-foreground">{ph.title}</h3>
                  {ph.steps.length > 0 && (
                    <ul className="mt-3 space-y-2">
                      {ph.steps.map((s) => (
                        <li key={s} className="flex items-start gap-2 text-xs text-muted-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{s}</li>
                      ))}
                    </ul>
                  )}
                </article>
              ))}
            </div>
            <RelatedLinks section="workflow" />
          </div>
        </section>

        {/* 13. COMPARISON */}
        <section data-template-key="comparison-content" id="compare" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Decision support" title="Agency, software or the managed Pinzo model?" sub="The right model depends on who will own the strategy, complete the work and review performance at each location." />
            <div className="overflow-x-auto">
              <div className="min-w-[640px] overflow-hidden rounded-2xl border border-border shadow-sm">
                <div className="grid grid-cols-4 border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                  <div className="p-3.5">Requirement</div>
                  <div className="p-3.5 text-center">Agency only</div>
                  <div className="p-3.5 text-center">Software only</div>
                  <div className="p-3.5 text-center text-primary">Pinzo managed model</div>
                </div>
                {comparison.map((row, i) => (
                  <div key={row.point} className={`grid grid-cols-4 items-start text-xs ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                    <div className="p-3.5 font-bold text-foreground">{row.point}</div>
                    <div className="p-3.5 text-muted-foreground">{row.agency}</div>
                    <div className="p-3.5 text-muted-foreground">{row.software}</div>
                    <div className="flex items-start gap-1.5 p-3.5 font-medium text-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{row.pinzo}</div>
                  </div>
                ))}
              </div>
            </div>
            <RelatedLinks section="comparison-content" />
          </div>
        </section>

        {/* 14. ENGAGEMENT MODELS */}
        <section data-template-key="engagement-model" id="plans" className="py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Engagement models" title="Choose the setup that fits your team" sub="Choose the platform if your team will do the work, managed local SEO if you want Pinzo to execute, or the group setup for several branches." />
            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              {plans.map((pl) => (
                <article key={pl.name} className={`flex flex-col rounded-2xl border p-7 shadow-sm ${pl.featured ? 'border-primary/40 bg-primary/[0.04] shadow-md' : 'border-border bg-card'}`}>
                  {pl.tag && <span className="mb-1 text-[10px] font-extrabold uppercase tracking-widest text-primary">{pl.tag}</span>}
                  <h3 className="text-lg font-extrabold text-foreground">{pl.name}</h3>
                  {pl.desc && <p className="mt-2 min-h-[3rem] text-xs leading-relaxed text-muted-foreground">{pl.desc}</p>}
                  <ul className="mt-4 space-y-2.5">
                    {pl.features.map((f) => (
                      <li key={f} className="flex items-start gap-2 text-xs text-muted-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{f}</li>
                    ))}
                  </ul>
                  <a href={pl.cta_href || '#free-audit'} className={`mt-6 flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-xs font-bold ${pl.featured ? 'bg-primary text-primary-foreground' : 'border border-border text-foreground hover:bg-muted/40'}`}>{pl.cta_label || 'Request proposal'}</a>
                </article>
              ))}
            </div>
            <p className="text-center text-[11px] text-muted-foreground">Pricing depends on locations, website condition, service scope and competition. See the <Link href="/#pricing" className="font-semibold text-primary underline-offset-4 hover:underline">live pricing page</Link> for current plans.</p>
            <RelatedLinks section="engagement-model" />
          </div>
        </section>

        </>
      ) : (
        <section data-template-key="method-summary" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading
              eyebrow="How we work"
              title={`How Pinzo delivers local SEO for ${industryLc}`}
              sub={`The method is the same in every city. Here is the short version, with the detail on the ${industryLc} page.`}
            />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {methodSummary.map((m) => (
                <Link key={m.title} href={m.href} className="flex items-start justify-between gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary/40">
                  <span>
                    <span className="block text-sm font-bold text-foreground">{m.title}</span>
                    <span className="mt-1 block text-xs leading-relaxed text-muted-foreground">{m.detail}</span>
                  </span>
                  <ArrowRight className="mt-0.5 h-4 w-4 shrink-0 text-primary opacity-70" />
                </Link>
              ))}
            </div>
            <p className="text-center text-sm text-muted-foreground">
              <Link href={pillarHref} className="font-semibold text-primary underline-offset-4 hover:underline">
                Full method, deliverables and pricing for {industryLc}
              </Link>
            </p>
          </div>
        </section>
      )}

      {/* 15. PROOF AND REPORTS */}
      <section data-template-key="proof" className="border-y border-border/40 bg-muted/10 py-16">
        <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
          <SectionHeading eyebrow="Proof and transparency" title="See what Pinzo measures and reports" sub="These sample views show how Pinzo reviews local rankings, service coverage, public review themes and location performance. They are illustrative formats, not customer results." />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.8fr_1.2fr]">
            <div className="rounded-2xl border border-border bg-card p-7 shadow-sm">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/5 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-600">Sample, not a real score</span>
              <p className="mt-4 text-5xl font-extrabold tracking-tight text-foreground">{c.audit_summary_title || '62'}<span className="text-lg text-muted-foreground">/100</span></p>
              <h3 className="mt-3 text-sm font-bold text-foreground">Visibility foundation needs work</h3>
              <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{c.audit_summary_body || 'An illustrative audit format showing the checks Pinzo uses to prioritise local visibility improvements.'}</p>
              <a href="#free-audit" className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-xs font-bold text-primary-foreground">Request my audit <ArrowRight className="h-3.5 w-3.5" /></a>
            </div>
            <div className="space-y-4 rounded-2xl border border-border bg-card p-7 shadow-sm">
              <h3 className="flex items-center gap-2 text-sm font-bold text-foreground"><ClipboardCheck className="h-4 w-4 text-primary" /> Sample Pinzo local SEO audit</h3>
              <ul className="space-y-2.5">
                {auditChecklist.map((r) => (
                  <li key={r.title} className="grid gap-1 border-b border-border pb-2.5 text-xs last:border-0 last:pb-0 sm:grid-cols-[40%_1fr] sm:gap-4">
                    <span className="font-semibold text-foreground">{r.title}</span>
                    <span className="text-muted-foreground">{r.detail}</span>
                  </li>
                ))}
              </ul>
              <p className="text-[11px] text-muted-foreground">Scores shown are illustrative and must not be presented as measured results.</p>
            </div>
          </div>

          {/* Review workflow sample (guardrail 5.4: every sample is labelled) */}
          {(c.reviews_body || c.example_review || (c.review_themes || []).length > 0) && (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <h3 className="flex items-center gap-2 text-sm font-bold text-foreground"><MessageSquare className="h-4 w-4 text-primary" /> Sample review theme analysis</h3>
                {c.reviews_body && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{c.reviews_body}</p>}
                {(c.review_themes || []).length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {(c.review_themes || []).map((t) => (
                      <span key={t} className="rounded-full border border-border bg-background px-3 py-1 text-[11px] font-semibold text-foreground">{t}</span>
                    ))}
                  </div>
                )}
              </div>
              {(c.example_review || c.example_reply) && (
                <div className="space-y-3 rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <h3 className="text-sm font-bold text-foreground">Illustrative review and reply</h3>
                  {c.example_review && <p className="rounded-xl border border-border bg-background p-3.5 text-xs leading-relaxed text-muted-foreground">{c.example_review}</p>}
                  {c.example_reply && <p className="rounded-xl border border-primary/20 bg-primary/5 p-3.5 text-xs leading-relaxed text-foreground">{c.example_reply}</p>}
                  <p className="text-[11px] text-muted-foreground">Sample copy for workflow guidance only. Never confirm private customer information in a public reply.</p>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {sampleAssets.map((a) => (
              <div key={a.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <FileText className="mb-2 h-[18px] w-[18px] text-primary" />
                <p className="text-sm font-bold text-foreground">{a.title}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{a.detail}</p>
              </div>
            ))}
          </div>
          <RelatedLinks section="proof" />
        </div>
      </section>


      {/* 16. FAQS (visible copy is the exact source of the FAQPage schema) */}
      {(c.faqs || []).length > 0 && (
        <section data-template-key="faqs" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Frequently asked questions" title={`Common questions about local SEO for ${industryLc}`} sub={`Practical answers for owners and marketing teams comparing local SEO options for ${industryLc}.`} />
            <div className="space-y-3">
              {(c.faqs || []).map((f) => (
                <details key={f.q} className="group overflow-hidden rounded-xl border border-border bg-card">
                  <summary className="flex cursor-pointer select-none items-center justify-between p-5 text-sm font-bold text-foreground [&::-webkit-details-marker]:hidden">
                    {f.q}
                    <span className="ml-4 text-muted-foreground transition-transform group-open:rotate-45">+</span>
                  </summary>
                  <div className="border-t border-border px-5 pb-5 pt-3.5 text-xs leading-relaxed text-muted-foreground">{f.a}</div>
                </details>
              ))}
            </div>
            <RelatedLinks section="faqs" />
          </div>
        </section>
      )}

      {/* 17. LEAD FORM */}
      <section id="free-audit" className="py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 rounded-3xl border border-primary/20 bg-primary/[0.04] p-8 sm:p-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary"><ShieldCheck className="h-3.5 w-3.5" /> Free visibility review</div>
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground">{c.lead_heading || `Find what is limiting your local visibility in ${city}`}</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">{c.lead_sub || 'Share your website or Google Maps link. Pinzo can review your profile, service pages, reviews, local rankings, technical gaps, conversion tracking and AI search readiness. No ranking promises, just prioritised opportunities.'}</p>
              <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1 text-xs font-semibold text-muted-foreground">
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />Single or multi-location</span>
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />No password sharing</span>
              </div>
              <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-xs font-bold text-primary hover:underline"><Phone className="h-3.5 w-3.5" /> Prefer WhatsApp? Message us</a>
            </div>
            <LpseoLeadForm page={lpseoPath(page.locale, page.slug)} submitLabel={c.final_button} />
          </div>
        </div>
      </section>

      {/* 18. RELATED LINKS + FINAL CTA */}
      <section data-template-key="related-links" className="mx-auto max-w-5xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-primary/5 p-8 text-center sm:p-12">
          <div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl" />
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{c.final_heading || `Grow your ${industryLc} visibility in ${city}`}</h2>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">{c.final_sub || 'Get a prioritised review of your Google profile, website, local rankings and conversion foundation. No ranking promises.'}</p>
          <div className="pt-6"><HeroCtas /></div>
        </div>

        <div className="mt-12 space-y-2 text-center">
          <p className="text-[11px] font-bold uppercase tracking-wider text-primary">Explore related services</p>
          <h2 className="text-xl font-extrabold tracking-tight text-foreground">Explore related Pinzo tools and services</h2>
          <p className="text-xs text-muted-foreground">Compare GBP management, local rank tracking, industry use cases and Pinzo plans.</p>
        </div>
        {(c.related_pages || []).length > 0 && (
          <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(c.related_pages || []).map((r) => (
              <SafeLink key={r.url} href={normaliseHref(r.url)} className="rounded-2xl border border-border bg-card p-5 text-sm font-semibold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary">{r.anchor}</SafeLink>
            ))}
          </div>
        )}

        {/* Crawl-depth spokes back up to the hubs */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs font-semibold text-muted-foreground">
          {/* On the pillar this spoke would point at the page itself. */}
          {!isPillar && <Link href={industryHubPath(page.locale, page.industry_slug)} className="inline-flex items-center gap-1.5 hover:text-foreground"><MapPin className="h-3.5 w-3.5" />{industry} in other cities</Link>}
          <Link href={rootHubPath(page.locale)} className="inline-flex items-center gap-1.5 hover:text-foreground"><Building className="h-3.5 w-3.5" />All industries</Link>
          <Link href="/" className="inline-flex items-center gap-1.5 hover:text-foreground"><Bot className="h-3.5 w-3.5" />AI Visibility platform</Link>
          {gbp && <a href={gbp} className="inline-flex items-center gap-1.5 hover:text-foreground"><Star className="h-3.5 w-3.5" />GBP management for {industryLc}</a>}
        </div>
        <div className="mt-6"><RelatedLinks section="related-links" /></div>
      </section>

      <MarketingFooter />
    </div>
  )
}
