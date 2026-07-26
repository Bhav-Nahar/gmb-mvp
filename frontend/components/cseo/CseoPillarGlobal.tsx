import Link from 'next/link'
import {
  Sparkles, Check, ArrowRight, ShieldCheck, Globe, Bot, MapPin,
  Building2, Users, ClipboardCheck, ExternalLink, AlertTriangle, BookOpen,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import LpseoLeadForm from '@/components/lpseo/LpseoLeadForm'
import type { CseoPageData, CseoQa, CseoPair, CseoLink, CseoChecklistRow } from '@/lib/cseo'

/**
 * Global pillar (LSEO-GLOBAL-001), served locale-free at the bare
 * /local-seo-services. Same page family and same table as the country pillars, but
 * a wider scope and a different section set, so it gets its own component rather
 * than a pile of branches inside CseoPillar.
 *
 * Section order follows the approved package
 * (pinzo-global-local-seo-services-pillar-template-and-guardrails.md, "Complete
 * page architecture").
 *
 * TEMPLATE RULE: every section is filled ENTIRELY by imported content or is not
 * rendered at all. There is no fallback copy anywhere below, so a gap in the import
 * shows up as a missing section in QA instead of as plausible-looking filler. The
 * only hardcoded strings are the structural column labels of the two tables, which
 * matches how CseoPillar labels its buyer-checklist columns.
 *
 * Guardrail: no U+2013, U+2014, U+2011 or U+2212 in any visible string here.
 */

// The global sections the importer adds on top of the shared CseoContent. Declared
// here rather than in lib/cseo.ts because only this component reads them.
interface SectionHeader { eyebrow: string; heading: string; intro: string }
interface JourneyStage { stage: string; label: string; detail: string }
interface Workstream { code: string; title: string; points: string[] }
interface TitledList { title: string; detail: string; points: string[] }
interface DeliverableRow { workstream: string; output: string; decision: string; measure: string }
interface ProofCase { region: string; name: string; detail: string; focus: string; url: string }
interface EngagementModel {
  tag: string; name: string; detail: string
  features: string[]; cta_label: string; cta_url: string
}
interface MarketPathway { country: string; detail: string; status: string; url: string }
interface RelatedCard { anchor: string; url: string; detail: string }

export interface CseoGlobalContent {
  badge?: string
  hero_sub?: string
  hero_trust?: string[]
  primary_cta?: string
  secondary_cta?: string
  answer_block?: string
  answer_note?: string
  answer_links?: CseoLink[]
  why_matters_body?: string
  journey_stages?: JourneyStage[]
  why_pillars?: CseoPair[]
  service_workstreams?: Workstream[]
  ai_signals?: string[]
  ai_surfaces?: CseoPair[]
  ai_approach?: CseoPair[]
  business_models?: TitledList[]
  roadmap_phases?: TitledList[]
  deliverables_table?: DeliverableRow[]
  proof_cases?: ProofCase[]
  proof_note?: string
  engagement_models?: EngagementModel[]
  cost_drivers?: { title: string; detail: string }
  buyer_checklist?: CseoChecklistRow[]
  city_visibility_body?: string
  market_pathways?: MarketPathway[]
  faqs?: CseoQa[]
  policy?: { title: string; detail: string }
  policy_links?: CseoLink[]
  final_heading?: string
  final_sub?: string
  final_button?: string
  audit_points?: string[]
  audit_note?: string
  related_cards?: RelatedCard[]
  sec_answer?: SectionHeader
  sec_why?: SectionHeader
  sec_services?: SectionHeader
  sec_ai?: SectionHeader
  sec_models?: SectionHeader
  sec_process?: SectionHeader
  sec_deliverables?: SectionHeader
  sec_proof?: SectionHeader
  sec_pricing?: SectionHeader
  sec_comparison?: SectionHeader
  sec_markets?: SectionHeader
  sec_faq?: SectionHeader
  sec_audit?: SectionHeader
  sec_related?: SectionHeader
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

export const GLOBAL_PILLAR_PATH = '/local-seo-services'

// A same-site absolute URL navigates better as a relative path; anything else is
// left exactly as authored.
const href = (url: string) =>
  url.replace(/^https?:\/\/(www\.)?pinzo\.io/, '') || '/'
const isExternal = (url: string) => /^https?:\/\//.test(href(url))

// Guardrails "Global market pathways": "Until a country pillar is published and
// returns a successful response, show it as text with `Coming soon`. Do not create
// a crawlable broken link." So `Coming soon` is the sentinel the approved copy uses
// for an unpublished market, and every other status means the pillar is in
// production. Matching on 'live' instead would have been unreachable: no row in the
// package ships that word, so India (published at /en-in/local-seo-services/, and
// badged "Country pillar in production") rendered as dead text and the global pillar
// linked to no country at all, against internal-linking rule 1.
const NOT_PUBLISHED = /^coming soon$/i
const isLiveMarket = (m: MarketPathway) =>
  Boolean(m.url) && !NOT_PUBLISHED.test(m.status.trim())

/**
 * Approved types (guardrails, "Structured data rules"): Organization, WebSite,
 * WebPage, Service, SoftwareApplication, BreadcrumbList, FAQPage. No LocalBusiness,
 * no AggregateRating, no Review, no Offer. The FAQPage entries are generated from
 * the same objects the visible FAQ renders, so the two cannot drift.
 */
export function buildCseoGlobalJsonLd(page: CseoPageData) {
  const c = (page.content || {}) as CseoGlobalContent
  const url = page.canonical_url || `${SITE_URL}${GLOBAL_PILLAR_PATH}/`
  const orgId = `${SITE_URL}/#organization`
  const graph: Record<string, unknown>[] = [
    { '@type': 'Organization', '@id': orgId, name: 'Pinzo', url: SITE_URL, logo: `${SITE_URL}/logo-horizontal-3.png` },
    { '@type': 'WebSite', '@id': `${SITE_URL}/#website`, url: SITE_URL, name: 'Pinzo', publisher: { '@id': orgId } },
    {
      '@type': 'Service',
      '@id': `${url}#service`,
      name: 'Local SEO Services',
      serviceType: 'Managed local SEO services',
      provider: { '@id': orgId },
      // The global pillar sells worldwide, so areaServed is not a Country here.
      areaServed: { '@type': 'Place', name: 'Worldwide' },
      description: page.meta_description,
    },
    {
      '@type': 'SoftwareApplication',
      '@id': `${SITE_URL}/#software`,
      name: 'Pinzo',
      applicationCategory: 'BusinessApplication',
      operatingSystem: 'Web',
      url: SITE_URL,
      publisher: { '@id': orgId },
    },
    {
      '@type': 'WebPage',
      '@id': `${url}#webpage`,
      url,
      name: page.meta_title,
      description: page.meta_description,
      inLanguage: 'en',
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
        { '@type': 'ListItem', position: 2, name: 'Local SEO Services', item: url },
      ],
    },
  ]
  const faqs = c.faqs || []
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

export default function CseoPillarGlobal({ page }: { page: CseoPageData }) {
  const c = (page.content || {}) as CseoGlobalContent
  const jsonLd = buildCseoGlobalJsonLd(page)

  const Header = ({ h }: { h?: SectionHeader }) =>
    h && (h.eyebrow || h.heading || h.intro) ? (
      <div className="mx-auto max-w-3xl space-y-3 text-center">
        {h.eyebrow && (
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
            {h.eyebrow}
          </div>
        )}
        {h.heading && <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{h.heading}</h2>}
        {h.intro && <p className="text-muted-foreground">{h.intro}</p>}
      </div>
    ) : null

  const Section = ({ id, header, children, alt }: {
    id?: string; header?: SectionHeader; children?: React.ReactNode; alt?: boolean
  }) => (
    <section id={id} className={alt ? 'border-y border-border/40 bg-muted/10 py-16' : 'py-16'}>
      <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
        <Header h={header} />
        {children}
      </div>
    </section>
  )

  const Bullets = ({ items, tone = 'emerald' }: { items: string[]; tone?: 'emerald' | 'primary' }) => (
    <ul className="space-y-2.5 text-xs text-muted-foreground">
      {items.map((p) => (
        <li key={p} className="flex items-start gap-2">
          <Check className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${tone === 'primary' ? 'text-primary' : 'text-emerald-500'}`} />
          {p}
        </li>
      ))}
    </ul>
  )

  const PairCards = ({ rows, cols }: { rows: CseoPair[]; cols: string }) => (
    <div className={`grid grid-cols-1 gap-4 ${cols}`}>
      {rows.map((r) => (
        <article key={r.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground">{r.title}</h3>
          {r.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{r.detail}</p>}
        </article>
      ))}
    </div>
  )

  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />

      <MarketingHeader />

      <nav aria-label="Breadcrumb" className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 lg:px-8">
        <ol className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
          <li><Link href="/" className="hover:text-foreground">Home</Link></li>
          <li aria-hidden>/</li>
          <li className="text-foreground">Local SEO Services</li>
        </ol>
      </nav>

      {/* 1. HERO */}
      <section className="mx-auto max-w-4xl space-y-6 px-4 pb-14 pt-10 text-center sm:px-6 lg:px-8">
        {c.badge && (
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" />{c.badge}
          </div>
        )}
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{page.h1}</h1>
        {c.hero_sub && <p className="mx-auto max-w-3xl text-base text-muted-foreground sm:text-lg">{c.hero_sub}</p>}
        {(c.primary_cta || c.secondary_cta) && (
          <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
            {c.primary_cta && (
              <a href="#audit" className="flex w-full min-w-[240px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 sm:w-auto">
                {c.primary_cta} <ArrowRight className="h-4 w-4" />
              </a>
            )}
            {c.secondary_cta && (
              <Link href="/pricing" className="flex w-full min-w-[180px] items-center justify-center rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
                {c.secondary_cta}
              </Link>
            )}
          </div>
        )}
        {(c.hero_trust || []).length > 0 && (
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2.5 text-[11px] font-semibold text-muted-foreground">
            {c.hero_trust!.map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
            ))}
          </div>
        )}
      </section>

      {/* 2. DIRECT ANSWER */}
      {c.answer_block && (
        <section className="pb-12">
          <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
              {c.sec_answer?.eyebrow && <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-primary">{c.sec_answer.eyebrow}</p>}
              {c.sec_answer?.heading && <h2 className="mb-3 text-lg font-bold text-foreground">{c.sec_answer.heading}</h2>}
              <p className="leading-relaxed text-muted-foreground">{c.answer_block}</p>
              {c.answer_note && <p className="mt-3 leading-relaxed text-muted-foreground">{c.answer_note}</p>}
              {(c.answer_links || []).length > 0 && (
                <div className="mt-5 flex flex-wrap gap-2">
                  {c.answer_links!.map((l) => (
                    <a key={l.url} href={l.url} className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/30 px-3 py-1.5 text-[11px] font-semibold text-foreground transition-colors hover:border-primary/40 hover:text-primary">
                      {l.anchor} <ArrowRight className="h-3 w-3 opacity-60" />
                    </a>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* 3. LOCAL SEARCH JOURNEY */}
      {((c.journey_stages || []).length > 0 || (c.why_pillars || []).length > 0) && (
        <Section alt id="why-local-seo" header={c.sec_why}>
          {c.why_matters_body && <p className="mx-auto max-w-3xl text-center leading-relaxed text-muted-foreground">{c.why_matters_body}</p>}
          {(c.journey_stages || []).length > 0 && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {c.journey_stages!.map((s, i) => (
                <article key={s.stage} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <span className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{String(i + 1).padStart(2, '0')}</span>
                  <h3 className="mt-1 text-sm font-bold text-foreground">{s.stage}</h3>
                  {s.label && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{s.label}</p>}
                  {s.detail && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{s.detail}</p>}
                </article>
              ))}
            </div>
          )}
          {(c.why_pillars || []).length > 0 && <PairCards rows={c.why_pillars!} cols="lg:grid-cols-3" />}
        </Section>
      )}

      {/* 4. COMPLETE SERVICE SCOPE */}
      {(c.service_workstreams || []).length > 0 && (
        <Section id="services" header={c.sec_services}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {c.service_workstreams!.map((w) => (
              <article key={w.code || w.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <div className="mb-3 flex items-center gap-2.5">
                  {w.code && (
                    <span className="flex h-8 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 px-2 text-[10px] font-extrabold tracking-wider text-primary">
                      {w.code}
                    </span>
                  )}
                  <h3 className="text-sm font-bold text-foreground">{w.title}</h3>
                </div>
                <Bullets items={w.points} />
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 5. GOOGLE AND AI DISCOVERY */}
      {((c.ai_surfaces || []).length > 0 || (c.ai_approach || []).length > 0) && (
        <Section alt id="ai-discovery" header={c.sec_ai}>
          {(c.ai_signals || []).length > 0 && (
            <div className="flex flex-wrap justify-center gap-2">
              {c.ai_signals!.map((s) => (
                <span key={s} className="rounded-full border border-border bg-card px-3 py-1.5 text-[11px] font-semibold text-muted-foreground">{s}</span>
              ))}
            </div>
          )}
          {(c.ai_surfaces || []).length > 0 && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {c.ai_surfaces!.map((s) => (
                <div key={s.title} className="rounded-2xl border border-border bg-card p-4 shadow-sm">
                  <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                    <Bot className="h-4 w-4 shrink-0 text-primary" />{s.title}
                  </div>
                  {s.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{s.detail}</p>}
                </div>
              ))}
            </div>
          )}
          {(c.ai_approach || []).length > 0 && <PairCards rows={c.ai_approach!} cols="lg:grid-cols-3" />}
        </Section>
      )}

      {/* 6. BUSINESS MODELS */}
      {(c.business_models || []).length > 0 && (
        <Section id="business-models" header={c.sec_models}>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            {c.business_models!.map((m, i) => (
              <article key={m.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <div className="mb-3 flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                    {[<MapPin key="a" className="h-[18px] w-[18px] text-primary" />,
                      <Building2 key="b" className="h-[18px] w-[18px] text-primary" />,
                      <Users key="c" className="h-[18px] w-[18px] text-primary" />][i] ?? <Globe className="h-[18px] w-[18px] text-primary" />}
                  </div>
                  <h3 className="text-sm font-bold text-foreground">{m.title}</h3>
                </div>
                {m.detail && <p className="mb-4 text-xs leading-relaxed text-muted-foreground">{m.detail}</p>}
                <Bullets items={m.points} tone="primary" />
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 7. FIRST 90 DAYS */}
      {(c.roadmap_phases || []).length > 0 && (
        <Section alt id="process" header={c.sec_process}>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            {c.roadmap_phases!.map((p, i) => (
              <article key={p.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <span className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="mt-1 text-sm font-bold text-foreground">{p.title}</h3>
                {p.detail && <p className="mb-4 mt-1.5 text-xs leading-relaxed text-muted-foreground">{p.detail}</p>}
                <Bullets items={p.points} />
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 8. MONTHLY DELIVERABLES (four-column table, per the approved reference) */}
      {(c.deliverables_table || []).length > 0 && (
        <Section id="deliverables" header={c.sec_deliverables}>
          <div className="overflow-x-auto">
            <div className="min-w-[860px] overflow-hidden rounded-3xl border border-border shadow-sm">
              <div className="grid grid-cols-[180px_1fr_1fr_220px] border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                <div className="p-3.5">Workstream</div>
                <div className="p-3.5">Monthly output</div>
                <div className="p-3.5">Decision it supports</div>
                <div className="p-3.5">Primary measure</div>
              </div>
              {c.deliverables_table!.map((r, i) => (
                <div key={r.workstream} className={`grid grid-cols-[180px_1fr_1fr_220px] items-start border-b border-border text-xs last:border-0 ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                  <div className="p-3.5 font-bold text-foreground">{r.workstream}</div>
                  <p className="p-3.5 leading-relaxed text-muted-foreground">{r.output}</p>
                  <p className="p-3.5 leading-relaxed text-foreground">{r.decision}</p>
                  <p className="p-3.5 leading-relaxed text-muted-foreground">{r.measure}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* 9. SELECTED WORK */}
      {(c.proof_cases || []).length > 0 && (
        <Section alt id="proof" header={c.sec_proof}>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            {c.proof_cases!.map((p) => (
              <article key={p.name} className="flex flex-col rounded-2xl border border-border bg-card p-6 shadow-sm">
                {p.region && <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{p.region}</p>}
                <h3 className="mt-1 text-sm font-bold text-foreground">{p.name}</h3>
                {p.detail && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{p.detail}</p>}
                {p.focus && (
                  <p className="mt-3 text-xs leading-relaxed text-foreground">
                    <span className="font-bold">Visibility focus:</span> {p.focus}
                  </p>
                )}
                {p.url && (
                  <a href={p.url} target="_blank" rel="noopener noreferrer"
                     className="mt-4 inline-flex items-center gap-1.5 text-xs font-bold text-primary hover:underline">
                    Visit client website <ExternalLink className="h-3 w-3" />
                  </a>
                )}
              </article>
            ))}
          </div>
          {c.proof_note && <p className="mx-auto max-w-3xl text-center text-[11px] leading-relaxed text-muted-foreground">{c.proof_note}</p>}
        </Section>
      )}

      {/* 10. ENGAGEMENT AND PRICING */}
      {(c.engagement_models || []).length > 0 && (
        <Section id="pricing" header={c.sec_pricing}>
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
            {c.engagement_models!.map((m) => (
              <article key={m.name} className="flex flex-col rounded-2xl border border-border bg-card p-7 shadow-sm">
                {m.tag && <span className="self-start rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-primary">{m.tag}</span>}
                <h3 className="mt-3 text-lg font-extrabold text-foreground">{m.name}</h3>
                {m.detail && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{m.detail}</p>}
                <div className="mt-4 flex-1"><Bullets items={m.features} /></div>
                {m.cta_label && m.cta_url && (
                  isExternal(m.cta_url) ? (
                    <a href={m.cta_url} target="_blank" rel="noopener noreferrer"
                       className="mt-6 flex items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-4 py-2.5 text-xs font-bold text-foreground transition-colors hover:border-primary/40 hover:text-primary">
                      {m.cta_label}
                    </a>
                  ) : (
                    <Link href={href(m.cta_url)}
                          className="mt-6 flex items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-4 py-2.5 text-xs font-bold text-foreground transition-colors hover:border-primary/40 hover:text-primary">
                      {m.cta_label}
                    </Link>
                  )
                )}
              </article>
            ))}
          </div>
          {/* Guardrail: no Offer schema and no embedded managed-service price. */}
          {c.cost_drivers?.detail && (
            <div className="mx-auto max-w-3xl rounded-2xl border border-border bg-card p-6 shadow-sm">
              {c.cost_drivers.title && <h3 className="text-sm font-bold text-foreground">{c.cost_drivers.title}</h3>}
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{c.cost_drivers.detail}</p>
            </div>
          )}
        </Section>
      )}

      {/* 11. BUYER GUIDE */}
      {(c.buyer_checklist || []).length > 0 && (
        <Section alt id="comparison" header={c.sec_comparison}>
          <div className="overflow-x-auto">
            <div className="min-w-[760px] overflow-hidden rounded-2xl border border-border shadow-sm">
              <div className="grid grid-cols-[280px_1fr_1fr] border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                <div className="p-3.5">Question to ask</div>
                <div className="p-3.5">Strong answer</div>
                <div className="p-3.5">Warning sign</div>
              </div>
              {c.buyer_checklist!.map((r, i) => (
                <div key={r.ask} className={`grid grid-cols-[280px_1fr_1fr] items-start text-xs ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                  <div className="p-3.5 font-bold text-foreground">{r.ask}</div>
                  <div className="flex items-start gap-1.5 p-3.5 text-muted-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{r.good}</div>
                  <div className="flex items-start gap-1.5 p-3.5 text-muted-foreground"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />{r.warning}</div>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* 12. GLOBAL MARKET PATHWAYS */}
      {(c.market_pathways || []).length > 0 && (
        <Section id="markets" header={c.sec_markets}>
          {c.city_visibility_body && <p className="mx-auto max-w-3xl text-center leading-relaxed text-muted-foreground">{c.city_visibility_body}</p>}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {c.market_pathways!.map((m) => {
              const body = (
                <>
                  <div className="flex items-center gap-2 text-sm font-bold text-foreground">
                    <Globe className="h-4 w-4 shrink-0 text-primary" />{m.country}
                  </div>
                  {m.detail && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{m.detail}</p>}
                  {m.status && (
                    <span className="mt-3 inline-block rounded-full border border-border bg-muted/40 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                      {m.status}
                    </span>
                  )}
                </>
              )
              return isLiveMarket(m) ? (
                <Link key={m.country} href={m.url} className="rounded-2xl border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary/40">
                  {body}
                </Link>
              ) : (
                <div key={m.country} className="rounded-2xl border border-border bg-card p-5 shadow-sm">{body}</div>
              )
            })}
          </div>
        </Section>
      )}

      {/* 13. FAQ (the visible copy is the exact source of the FAQPage schema) */}
      {(c.faqs || []).length > 0 && (
        <Section alt id="faq" header={c.sec_faq}>
          <div className="mx-auto max-w-4xl space-y-3">
            {c.faqs!.map((f) => (
              <details key={f.q} className="group overflow-hidden rounded-xl border border-border bg-card">
                <summary className="flex cursor-pointer select-none items-center justify-between p-5 text-sm font-bold text-foreground [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <span className="ml-4 text-muted-foreground transition-transform group-open:rotate-45">+</span>
                </summary>
                <div className="border-t border-border px-5 pb-5 pt-3.5 text-xs leading-relaxed text-muted-foreground">{f.a}</div>
              </details>
            ))}
          </div>
          {c.policy?.detail && (
            <div className="mx-auto max-w-4xl rounded-2xl border border-border bg-card p-6 shadow-sm">
              <h3 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <BookOpen className="h-4 w-4 text-primary" />{c.policy.title}
              </h3>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{c.policy.detail}</p>
              {(c.policy_links || []).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
                  {c.policy_links!.map((l) => (
                    <a key={l.url} href={l.url} target="_blank" rel="noopener noreferrer"
                       className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary hover:underline">
                      {l.anchor} <ExternalLink className="h-3 w-3" />
                    </a>
                  ))}
                </div>
              )}
            </div>
          )}
        </Section>
      )}

      {/* 14. AUDIT FORM */}
      <section id="audit" className="py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 rounded-3xl border border-primary/20 bg-primary/[0.04] p-8 sm:p-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="space-y-4">
              {c.sec_audit?.eyebrow && (
                <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                  <ShieldCheck className="h-3.5 w-3.5" /> {c.sec_audit.eyebrow}
                </div>
              )}
              {c.final_heading && <h2 className="text-3xl font-extrabold tracking-tight text-foreground">{c.final_heading}</h2>}
              {c.final_sub && <p className="text-sm leading-relaxed text-muted-foreground">{c.final_sub}</p>}
              {(c.audit_points || []).length > 0 && (
                <ul className="space-y-2 text-xs font-semibold text-muted-foreground">
                  {c.audit_points!.map((p) => (
                    <li key={p} className="flex items-start gap-2"><ClipboardCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />{p}</li>
                  ))}
                </ul>
              )}
              {c.audit_note && <p className="text-[11px] leading-relaxed text-muted-foreground">{c.audit_note}</p>}
            </div>
            {/* Shared with the leaf and country pages: stores the lead before emailing,
                and carries the consent, UTM, GCLID and landing-page capture the
                guardrails require. The package's formsubmit.co destination is ignored
                because it cannot confirm storage before showing success. */}
            <LpseoLeadForm page={`${GLOBAL_PILLAR_PATH}/`} submitLabel={c.final_button || c.primary_cta} />
          </div>
        </div>
      </section>

      {/* 15. RELATED LINKS */}
      {(c.related_cards || []).length > 0 && (
        <section id="related-links" className="mx-auto max-w-6xl space-y-8 px-4 pb-16 sm:px-6 lg:px-8">
          <Header h={c.sec_related} />
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {c.related_cards!.map((l) => (
              <Link key={l.url} href={href(l.url)} className="rounded-2xl border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary/40">
                <div className="flex items-center justify-between gap-2 text-sm font-bold text-foreground">
                  {l.anchor} <ArrowRight className="h-4 w-4 shrink-0 opacity-60" />
                </div>
                {l.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{l.detail}</p>}
              </Link>
            ))}
          </div>
        </section>
      )}

      <MarketingFooter />
    </div>
  )
}
