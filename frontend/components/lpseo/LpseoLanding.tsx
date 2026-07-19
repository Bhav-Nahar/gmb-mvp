import Link from 'next/link'
import {
  Sparkles, Check, X, MapPin, TrendingUp, Building, Star, ArrowRight, Search,
  ListChecks, RefreshCw, Calendar, ShieldCheck, BarChart3, Bot, Globe, Compass, Phone,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import LpseoLeadForm from './LpseoLeadForm'
import {
  buildLpseoJsonLd, lpseoPath, industryHubPath, rootHubPath,
  type LpseoPageData, type LpseoListItem, type LpseoSection,
} from '@/lib/lpseo'

/**
 * Local-SEO managed-service landing page (industry x city). Server component —
 * pure HTML/CSS; the only client JS is the shared header + the lead form.
 * Every section below carries a data-template-key matching one of the 15
 * link-capable section keys and is skipped entirely when its content is absent.
 */
export default function LpseoLanding({ page, siblings = [] }: { page: LpseoPageData; siblings?: LpseoListItem[] }) {
  const c = page.content || {}
  const industry = page.industry_label
  const industryLc = industry.toLowerCase()
  const city = page.city_label
  const jsonLd = buildLpseoJsonLd(page)
  const primaryCta = c.primary_cta || 'Get a Free Local SEO Audit'
  const secondaryCta = c.secondary_cta || 'View the 90-Day Plan'
  const whatsapp = 'https://wa.me/917021052482?text=' + encodeURIComponent(`Hi, I'd like a Pinzo local SEO audit for my ${industryLc} business in ${city}.`)

  // ── Internal linking ────────────────────────────────────────────────────────
  // Site-wide defaults (currently the cannibalisation cross-link to the sibling
  // GBP page when set) merge with per-page content.internal_links, keyed by the
  // section each should render under. Any of the 15 sections can carry links.
  const gbp = c.gbp_url
  const defaultLinks: Partial<Record<LpseoSection, { anchor: string; href: string }[]>> = {
    'service-matrix': gbp ? [{ anchor: `Google Business Profile management for ${industryLc}`, href: gbp }] : [],
    'related-links': gbp ? [{ anchor: `GBP management for ${industry} in ${city}`, href: gbp }] : [],
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
            <Link href={l.href} className="font-semibold text-primary underline-offset-4 hover:underline">{l.anchor}</Link>
          </span>
        ))}
      </p>
    )
  }

  const SectionHeading = ({ eyebrow, title, sub }: { eyebrow?: string; title: string; sub?: string }) => (
    <div className="mx-auto max-w-3xl space-y-3 text-center">
      {eyebrow && <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">{eyebrow}</div>}
      <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{title}</h2>
      {sub && <p className="text-muted-foreground">{sub}</p>}
    </div>
  )

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

  // Illustrative "dentist near me"-style geo-grid — decorative, clearly labelled.
  const GEO = [
    [11, 12, 8, 7, 10, 15, 18], [10, 9, 5, 4, 7, 12, 16], [8, 6, 3, 2, 5, 9, 13],
    [7, 4, 2, 1, 3, 8, 12], [10, 7, 5, 3, 6, 10, 15], [14, 11, 8, 7, 10, 14, 19], [18, 16, 12, 11, 15, 19, 21],
  ]
  const cellColor = (v: number) => v <= 3 ? '#22c55e' : v <= 6 ? '#84cc16' : v <= 10 ? '#f59e0b' : v <= 15 ? '#fb923c' : '#f43f5e'

  const answerHeading = c.answer_heading || `What are local SEO services for ${industryLc} in ${city}?`
  const answerBlock = c.answer_block || `Local SEO services for ${industryLc} in ${city} improve visibility when nearby customers search on Google Maps, Google Search and AI platforms. It combines Google Business Profile management, treatment- and service-page SEO, citation consistency, review workflows, local schema, technical SEO, local authority building and neighbourhood-level rank tracking — so more nearby customers discover, trust and contact the business.`

  const trust = ['Single or multiple locations', 'Privacy-conscious review support', 'No ranking guarantees']

  const cmsServices = c.services || []
  const missingServices = [
    {
      channel: 'Multi-location governance',
      work: 'Central control, branch-level profiles, unique location pages, and location dashboards.',
      outcome: `Ensures consistent brand experience while targeting specific suburban catchments for ${industryLc} groups.`
    },
    {
      channel: 'Auditing and strategy',
      work: 'Initial and ongoing reviews of GBP health, local visibility, and competitor gaps.',
      outcome: 'Focuses resources on treatments and locations with the highest patient demand and lowest competition.'
    },
    {
      channel: 'Monthly reporting',
      work: 'Clear progress summaries including completed work, outcomes, and strategy reviews.',
      outcome: 'Provides transparency so you know exactly what was done and the impact on enquiries.'
    }
  ]
  const finalServices = [
    ...cmsServices,
    ...missingServices.filter(ms => !cmsServices.some(cs => cs.channel.toLowerCase() === ms.channel.toLowerCase()))
  ]

  const cmsComparison = c.comparison || []
  const missingComparison = [
    { point: 'Conversion tracking', agency: 'Varies by reporting setup', software: 'Requires manual integration', pinzo: 'Integrated call, form and lead tracking' },
    { point: 'Review management', agency: 'Usually manual', software: 'Tool provided, team executes', pinzo: 'Workflows with response support' },
    { point: 'Pricing model', agency: 'High monthly retainer', software: 'SaaS subscription', pinzo: 'Transparent tiered pricing' }
  ]
  const finalComparison = [
    ...cmsComparison,
    ...missingComparison.filter(mc => !cmsComparison.some(cc => cc.point.toLowerCase() === mc.point.toLowerCase()))
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
          <li><Link href={rootHubPath(page.locale)} className="hover:text-foreground">Local SEO Services</Link></li>
          <li aria-hidden>/</li>
          <li><Link href={industryHubPath(page.locale, page.industry_slug)} className="hover:text-foreground">{industry}</Link></li>
          <li aria-hidden>/</li>
          <li className="text-foreground">{city}</li>
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
        <div className="rounded-3xl border border-border bg-card p-4 shadow-xl">
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

      {/* 1b. DIRECT ANSWER (AEO) */}
      <section className="pb-6">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <h2 className="mb-3 text-lg font-bold text-foreground">{answerHeading}</h2>
            <p className="leading-relaxed text-muted-foreground">{answerBlock}</p>
          </div>
        </div>
      </section>

      {/* 2. SEARCH INTENT */}
      {(c.search_intents || []).length > 0 && (
        <section data-template-key="search-intent" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="How customers search" title={`How ${city} customers find ${industryLc} through local search`} sub="A useful page must reflect the decision behind the query — not just repeat the keyword. Pinzo maps every high-value search to the right local asset and conversion action." />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {(c.search_intents || []).map((it) => (
                <article key={it.title} className="flex h-full flex-col rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <Search className="mb-3 h-6 w-6 text-primary" />
                  <h3 className="text-sm font-bold text-foreground">{it.title}</h3>
                  {it.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{it.detail}</p>}
                  {it.example && <p className="mt-auto pt-4 text-xs text-foreground"><span className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-muted-foreground">Example search</span>{it.example}</p>}
                </article>
              ))}
            </div>
            <RelatedLinks section="search-intent" />
          </div>
        </section>
      )}

      {/* 3. SERVICE MATRIX */}
      {finalServices.length > 0 && (
        <section data-template-key="service-matrix" className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="The Pinzo visibility system" title={`What's included in our local SEO services for ${industryLc}`} sub="One connected system across Google Maps, local organic results and AI answers — not a single thin page." />
            <div className="overflow-hidden rounded-3xl border border-border shadow-sm">
              {finalServices.map((s, i) => (
                <div key={s.channel} className={`grid gap-4 border-b border-border p-6 last:border-0 md:grid-cols-[200px_1fr_240px] ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                  <div className="flex items-center gap-2.5 font-bold text-foreground">
                    <span className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Globe className="h-[18px] w-[18px] text-primary" /></span>
                    {s.channel}
                  </div>
                  <p className="text-sm leading-relaxed text-muted-foreground">{s.work}</p>
                  {s.outcome && (
                    <div className="rounded-xl border border-border bg-background p-3.5">
                      <p className="text-[10px] font-bold uppercase tracking-wide text-primary">Outcome</p>
                      <p className="mt-1 text-xs font-medium text-foreground">{s.outcome}</p>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <RelatedLinks section="service-matrix" />
          </div>
        </section>
      )}

      {/* 4. INDUSTRY STRATEGY */}
      {(c.strategy_body || (c.strategy_points || []).length > 0 || (c.topics || []).length > 0 || (c.value_props || []).length > 0) && (
        <section data-template-key="industry-strategy" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto grid max-w-6xl gap-8 px-4 sm:px-6 lg:grid-cols-2 lg:px-8">
            <div className="space-y-5 rounded-3xl border border-border bg-card p-7 shadow-sm">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Industry-specific content</div>
              <h2 className="text-2xl font-extrabold tracking-tight text-foreground">{c.strategy_heading || `${industry} content strategy for high-intent local searches`}</h2>
              {c.strategy_body && <p className="text-sm leading-relaxed text-muted-foreground">{c.strategy_body}</p>}
              {(c.topics || []).length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {(c.topics || []).map((t) => (
                    <span key={t} className="rounded-full border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground">{t}</span>
                  ))}
                </div>
              )}
              {(c.strategy_points || []).length > 0 && (
                <ul className="space-y-2.5">
                  {(c.strategy_points || []).map((p) => (
                    <li key={p} className="flex items-start gap-2.5 text-sm text-muted-foreground"><Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />{p}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="space-y-5">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Conversion relevance</div>
              <h2 className="text-2xl font-extrabold tracking-tight text-foreground">Visibility only helps when the page reduces uncertainty.</h2>
              {(c.value_props || []).length > 0 ? (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  {(c.value_props || []).map((v) => (
                    <div key={v.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                      <h3 className="text-sm font-bold text-foreground">{v.title}</h3>
                      {v.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{v.detail}</p>}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Trust, convenience, reassurance and a clear action path turn local searches into booked customers.</p>
              )}
            </div>
          </div>
          <div className="mx-auto mt-8 max-w-6xl px-4 sm:px-6 lg:px-8"><RelatedLinks section="industry-strategy" /></div>
        </section>
      )}

      {/* 5. MAPS SEO */}
      {(c.maps_body || (c.maps_signals || []).length > 0) && (
        <section data-template-key="maps-seo" id="maps-seo" className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Google Maps SEO" title={`How do ${industryLc} improve visibility in the Google Maps 3-pack?`} sub={c.maps_body || 'Maps visibility comes from how clearly Google understands the business, how relevant it is to the query, how prominent it is across the web and how close it is to the searcher. Pinzo improves the controllable signals — without promising fixed rankings.'} />
            {(c.maps_signals || []).length > 0 && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {(c.maps_signals || []).map((s) => (
                  <div key={s} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
                    <Compass className="mt-0.5 h-[18px] w-[18px] shrink-0 text-primary" />
                    <span className="text-sm font-medium text-foreground">{s}</span>
                  </div>
                ))}
              </div>
            )}
            <RelatedLinks section="maps-seo" />
          </div>
        </section>
      )}

      {/* 6. CITY STRATEGY */}
      {(c.city_body || (c.neighborhoods || []).length > 0 || (c.city_requirements || []).length > 0 || siblings.length > 0) && (
        <section data-template-key="city-strategy" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow={`${city} relevance`} title={`Local SEO strategy for ${city} ${industryLc} catchment areas`} sub={c.city_body || `${city} searches can change by neighbourhood because distance, traffic and convenience affect choice. Pinzo maps visibility around the genuine service area and only creates location content where the business can serve customers meaningfully.`} />
            {(c.neighborhoods || []).length > 0 && (
              <div className="space-y-3 text-center">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Areas customers search in {city}</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {(c.neighborhoods || []).map((n) => (
                    <span key={n} className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm"><MapPin className="h-3.5 w-3.5 text-primary" />{n}</span>
                  ))}
                </div>
              </div>
            )}
            {(c.city_requirements || []).length > 0 && (
              <div className="mx-auto max-w-3xl rounded-2xl border border-border bg-card p-6 shadow-sm">
                <h3 className="mb-4 text-sm font-bold text-foreground">Local data required before publishing</h3>
                <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {(c.city_requirements || []).map((r) => (
                    <li key={r} className="flex items-start gap-2 text-xs text-muted-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{r}</li>
                  ))}
                </ul>
              </div>
            )}
            {siblings.length > 0 && (
              <div className="space-y-3 text-center">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{industry} in other cities</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {siblings.map((s) => (
                    <Link key={s.slug} href={lpseoPath(s.locale, s.slug)} className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary"><MapPin className="h-3.5 w-3.5 text-primary" />{s.city_label}</Link>
                  ))}
                </div>
              </div>
            )}
            <RelatedLinks section="city-strategy" />
          </div>
        </section>
      )}

      {/* 6b. PROOF STRIP */}
      {(c.proof_points || []).length > 0 && (
        <section className="py-14">
          <div className="mx-auto grid max-w-6xl grid-cols-1 gap-3 px-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-4 lg:px-8">
            {(c.proof_points || []).map((p) => (
              <div key={p.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <p className="text-sm font-bold text-foreground">{p.title}</p>
                {p.detail && <p className="mt-1 text-xs text-muted-foreground">{p.detail}</p>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* 7. AEO COVERAGE */}
      {(c.answer_units || []).length > 0 && (
        <section data-template-key="aeo-coverage" className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Answer engine coverage" title={`Local SEO questions this page answers for ${industryLc}`} sub="Concise answer units across commercial, informational, comparison and implementation intent." />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {(c.answer_units || []).map((a) => (
                <article key={a.q} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <h3 className="text-sm font-bold text-foreground">{a.q}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{a.a}</p>
                </article>
              ))}
            </div>
            <RelatedLinks section="aeo-coverage" />
          </div>
        </section>
      )}

      {/* 8. COMPARISON */}
      {finalComparison.length > 0 && (
        <section data-template-key="comparison-content" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Decision support" title="Agency, software or the managed Pinzo model?" />
            <div className="overflow-x-auto">
              <div className="min-w-[640px] overflow-hidden rounded-2xl border border-border shadow-sm">
                <div className="grid grid-cols-4 border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                  <div className="p-3.5">Requirement</div>
                  <div className="p-3.5 text-center">Agency only</div>
                  <div className="p-3.5 text-center">Software only</div>
                  <div className="p-3.5 text-center text-primary">Pinzo managed</div>
                </div>
                {finalComparison.map((row, i) => (
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
      )}

      {/* 9. WORKFLOW / 90-DAY PLAN */}
      {(c.workflow_phases || []).length > 0 && (
        <section data-template-key="workflow" id="plan" className="py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Execution model" title={`Our 90-day local SEO process for ${industryLc}`} sub="Foundational issues first, then treatment/service visibility and local authority. Timelines depend on the current website, competition and approvals." />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {(c.workflow_phases || []).map((ph, i) => (
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
      )}

      {/* 10. SINGLE VS MULTI */}
      {((c.single_points || []).length > 0 || (c.multi_points || []).length > 0) && (
        <section data-template-key="single-multi" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Local SEO for single and multi-location ${industryLc}`} />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {(c.single_points || []).length > 0 && (
                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><MapPin className="h-[18px] w-[18px] text-primary" /></div>
                    <h3 className="text-sm font-bold text-foreground">Single location</h3>
                  </div>
                  <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                    {(c.single_points || []).map((p) => (
                      <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{p}</li>
                    ))}
                  </ul>
                </div>
              )}
              {(c.multi_points || []).length > 0 && (
                <div className="rounded-2xl border-2 border-primary/40 bg-card p-6 shadow-md">
                  <div className="mb-4 flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Building className="h-[18px] w-[18px] text-primary" /></div>
                    <h3 className="text-sm font-bold text-foreground">Multi-location &amp; groups</h3>
                  </div>
                  <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                    {(c.multi_points || []).map((p) => (
                      <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />{p}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
            <RelatedLinks section="single-multi" />
          </div>
        </section>
      )}

      {/* 11. DELIVERABLES */}
      {(c.deliverables || []).length > 0 && (
        <section data-template-key="deliverables" className="py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Monthly deliverables" title={`Monthly local SEO deliverables for ${industryLc}`} sub="Managed service should mean clear execution, not a generic ranking PDF." />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(c.deliverables || []).map((d) => (
                <article key={d.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><RefreshCw className="h-[18px] w-[18px] text-primary" /></div>
                  <h3 className="text-sm font-bold text-foreground">{d.title}</h3>
                  {d.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{d.detail}</p>}
                </article>
              ))}
            </div>
            <RelatedLinks section="deliverables" />
          </div>
        </section>
      )}

      {/* 12. SAMPLE AUDIT */}
      {(c.audit_bars || []).length > 0 && (
        <section data-template-key="sample-audit" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Illustrative audit preview" title={`Free local SEO audit for ${industryLc}`} sub="The live audit uses verified profile, website and ranking data. The example below shows the output format only." />
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[0.8fr_1.2fr]">
              <div className="rounded-2xl border border-border bg-card p-7 shadow-sm">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/5 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-amber-600">Sample — not a real score</span>
                <p className="mt-4 text-5xl font-extrabold tracking-tight text-foreground">{c.audit_summary_title || '62'}<span className="text-lg text-muted-foreground">/100</span></p>
                <h3 className="mt-3 text-sm font-bold text-foreground">Visibility foundation needs work</h3>
                {c.audit_summary_body && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{c.audit_summary_body}</p>}
                <a href="#free-audit" className="mt-5 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-xs font-bold text-primary-foreground">Audit my {industryLc} business <ArrowRight className="h-3.5 w-3.5" /></a>
              </div>
              <div className="space-y-4 rounded-2xl border border-border bg-card p-7 shadow-sm">
                {(c.audit_bars || []).map((b) => (
                  <div key={b.label}>
                    <div className="mb-1.5 flex items-center justify-between text-xs"><span className="text-muted-foreground">{b.label}</span><span className="font-bold text-foreground">{b.percent}%</span></div>
                    <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${b.percent}%` }} /></div>
                  </div>
                ))}
                <p className="text-[11px] text-muted-foreground">Scores shown are illustrative and must not be presented as measured results.</p>
              </div>
            </div>
            <RelatedLinks section="sample-audit" />
          </div>
        </section>
      )}

      {/* 13. ENGAGEMENT MODEL / PLANS */}
      {(c.plans || []).length > 0 && (
        <section data-template-key="engagement-model" className="py-16">
          <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Choose your operating model" title={`Local SEO packages for ${industryLc}`} />
            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              {(c.plans || []).map((pl) => (
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
            <RelatedLinks section="engagement-model" />
          </div>
        </section>
      )}

      {/* 14. LEAD FORM */}
      <section id="free-audit" className="py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 rounded-3xl border border-primary/20 bg-primary/[0.04] p-8 sm:p-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary"><ShieldCheck className="h-3.5 w-3.5" /> Free visibility review</div>
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground">{c.lead_heading || `Find what's limiting your ${industryLc} local visibility in ${city}`}</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">{c.lead_sub || 'Get a practical review of your Google profile, website, service coverage, local rankings and conversion foundation. No ranking promises — just prioritised opportunities.'}</p>
              <div className="flex flex-wrap gap-x-5 gap-y-2 pt-1 text-xs font-semibold text-muted-foreground">
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />Single or multi-location</span>
                <span className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />No password sharing</span>
              </div>
              <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-xs font-bold text-primary hover:underline"><Phone className="h-3.5 w-3.5" /> Prefer WhatsApp? Message us</a>
            </div>
            <LpseoLeadForm page={lpseoPath(page.locale, page.slug)} />
          </div>
        </div>
      </section>

      {/* 15. FAQS */}
      {(c.faqs || []).length > 0 && (
        <section data-template-key="faqs" className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Frequently asked questions about local SEO for ${industryLc}`} />
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

      {/* 16. RELATED LINKS + FINAL CTA */}
      <section data-template-key="related-links" className="mx-auto max-w-5xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-primary/5 p-8 text-center sm:p-12">
          <div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl" />
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{c.final_heading || `Grow your ${industryLc} visibility in ${city}`}</h2>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">{c.final_sub || 'Get a prioritised review of your Google profile, website, local rankings and conversion foundation. No ranking promises.'}</p>
          <div className="pt-6"><HeroCtas /></div>
        </div>

        {(c.related_pages || []).length > 0 && (
          <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(c.related_pages || []).map((r) => (
              <a key={r.url} href={r.url} className="rounded-2xl border border-border bg-card p-5 text-sm font-semibold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary">{r.anchor}</a>
            ))}
          </div>
        )}

        {/* Crawl-depth spokes back up to the hubs */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs font-semibold text-muted-foreground">
          <Link href={industryHubPath(page.locale, page.industry_slug)} className="inline-flex items-center gap-1.5 hover:text-foreground"><MapPin className="h-3.5 w-3.5" />{industry} in other cities</Link>
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
