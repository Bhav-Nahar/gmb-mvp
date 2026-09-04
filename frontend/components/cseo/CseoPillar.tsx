import Link from 'next/link'
import {
  Sparkles, Check, MapPin, Building, ArrowRight, RefreshCw, ShieldCheck,
  BarChart3, Bot, Globe, Compass, Phone, ClipboardCheck, FileText, Search, Scale,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import LpseoLeadForm from '@/components/lpseo/LpseoLeadForm'
import { buildCseoJsonLd, type CseoPageData, type CseoLink } from '@/lib/cseo'
import { Section, makeSafeLink } from '@/components/seo/sections'

/**
 * Country pillar (Local SEO universe). Server component: the only client JS is the
 * shared header and the lead form.
 *
 * Section order and coverage follow the approved country-pillar template
 * (pinzo-country-pillar-template-content-guardrails.md §4, sixteen required H2s).
 *
 * Unlike the industry x city leaf, this template ships NO fallback copy. A country
 * pillar filled with generic defaults would be the "changed only the country name"
 * page §4 explicitly forbids, so a section with no imported content renders nothing
 * and shows up as a gap in QA rather than as plausible filler.
 *
 * Guardrail 5: no U+2013, U+2014, U+2011 or U+2212 in any visible string here.
 */
// A same-site absolute URL navigates better as a path, and must not open in a new
// tab. Anything else (WhatsApp, an external tool) is left exactly as authored.
const sameSite = (url: string) => url.replace(/^https?:\/\/(www\.)?pinzo\.io/, '') || '/'

export default function CseoPillar({ page, livePaths = new Set<string>() }: { page: CseoPageData; livePaths?: Set<string> }) {
  const c = page.content || {}

  // Never render an anchor to a page that does not exist yet (guardrail: no links
  // to planned pages). Unpublished destinations degrade to plain text.
  const SafeLink = makeSafeLink(livePaths)
  const country = page.country_label
  const jsonLd = buildCseoJsonLd(page)
  const primaryCta = c.primary_cta || 'Get a Free Local SEO Audit'
  const secondaryCta = c.secondary_cta || 'Start Free Trial'
  const whatsapp = 'https://wa.me/919869855079?text=' + encodeURIComponent(`Hi, I'd like a Pinzo local SEO audit for my business in ${country}.`)


  const Cards = ({ rows, cols = 'sm:grid-cols-2 lg:grid-cols-4' }: { rows: { title: string; detail: string }[]; cols?: string }) => (
    <div className={`grid grid-cols-1 gap-4 ${cols}`}>
      {rows.map((r) => (
        <article key={r.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
          <h3 className="text-sm font-bold text-foreground">{r.title}</h3>
          {r.detail && <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{r.detail}</p>}
        </article>
      ))}
    </div>
  )

  const LinkGrid = ({ links }: { links: CseoLink[] }) => (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {links.map((l) => (
        <SafeLink key={l.url} href={l.url} className="rounded-2xl border border-border bg-card p-5 shadow-sm transition-colors hover:border-primary/40">
          <span className="flex items-center justify-between gap-2 text-sm font-semibold text-foreground">
            {l.anchor} <ArrowRight className="h-4 w-4 shrink-0 opacity-60" />
          </span>
          {l.detail && <span className="mt-1.5 block text-xs leading-relaxed text-muted-foreground">{l.detail}</span>}
        </SafeLink>
      ))}
    </div>
  )

  const Ctas = () => (
    <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
      <a href="#audit" className="flex w-full min-w-[240px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 sm:w-auto">
        {primaryCta} <ArrowRight className="h-4 w-4" />
      </a>
      <a href="/#pricing" className="flex w-full min-w-[180px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
        {secondaryCta}
      </a>
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
          <li><Link href="/local-seo-services" className="hover:text-foreground">Local SEO Services</Link></li>
          <li aria-hidden>/</li>
          <li className="text-foreground">{country}</li>
        </ol>
      </nav>

      {/* 1. HERO */}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <div className="space-y-6">
          {c.badge && (
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
              <Sparkles className="h-3.5 w-3.5" />{c.badge}
            </div>
          )}
          <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{page.h1}</h1>
          {c.hero_copy && <p className="max-w-xl text-base text-muted-foreground sm:text-lg">{c.hero_copy}</p>}
          <Ctas />
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 text-[11px] font-semibold text-muted-foreground">
            {['Single or multiple locations', 'No ranking guarantees', 'Reporting you can audit'].map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
            ))}
          </div>
        </div>
        <div className="rounded-3xl border border-border bg-card p-4 shadow-xl" role="img"
             aria-label={`Illustrative Pinzo dashboard showing local visibility across ${country}. Sample data, not a client result.`}>
          <div className="flex items-center justify-between px-1 pb-3">
            <div className="flex items-center gap-2 text-xs font-bold text-foreground"><BarChart3 className="h-4 w-4 text-primary" /> {country} visibility</div>
            <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Illustrative</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {(c.city_hubs || []).slice(0, 6).map((h, i) => (
              <div key={h.url} className="rounded-xl border border-border bg-background p-3">
                <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{h.anchor.replace(/^Local SEO Services in /, '')}</p>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${[72, 58, 64, 45, 51, 38][i] ?? 50}%` }} />
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-[10px] text-muted-foreground">Sample view. Bars are illustrative and are not measured results.</p>
        </div>
      </section>

      {/* 2. DIRECT ANSWER */}
      {c.direct_answer && (
        <section className="pb-10">
          <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
              <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-primary">Direct answer</p>
              <h2 className="mb-3 text-lg font-bold text-foreground">{c.direct_question || `What do Local SEO services in ${country} include?`}</h2>
              <p className="leading-relaxed text-muted-foreground">{c.direct_answer}</p>
            </div>
          </div>
        </section>
      )}

      {/* 3. SEARCH BEHAVIOUR */}
      {(c.search_behaviour || []).length > 0 && (
        <Section alt eyebrow="Search behaviour" title={`How local search works in ${country}`}
                 sub="A country page has to explain how people actually search here, not restate the service.">
          <Cards rows={c.search_behaviour!} />
        </Section>
      )}

      {/* 4. SERVICE SCOPE */}
      {(c.service_matrix || []).length > 0 && (
        <Section id="services" eyebrow="Complete service scope" title={`Local SEO services for businesses in ${country}`}>
          <div className="overflow-x-auto">
            <div className="min-w-[720px] overflow-hidden rounded-3xl border border-border shadow-sm">
              <div className="grid grid-cols-[220px_1fr_1fr] border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                <div className="p-3.5">SEO area</div>
                <div className="p-3.5">What Pinzo manages</div>
                <div className="p-3.5">Why it matters in {country}</div>
              </div>
              {c.service_matrix!.map((s, i) => (
                <div key={s.area} className={`grid grid-cols-[220px_1fr_1fr] items-start border-b border-border last:border-0 ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                  <div className="flex items-center gap-2.5 p-3.5 text-sm font-bold text-foreground">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Globe className="h-4 w-4 text-primary" /></span>
                    {s.area}
                  </div>
                  <p className="p-3.5 text-xs leading-relaxed text-muted-foreground">{s.work}</p>
                  <p className="p-3.5 text-xs leading-relaxed text-foreground">{s.why}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* 5. RANKING PRINCIPLES AND LIMITS */}
      {(c.ranking_factors || []).length > 0 && (
        <Section alt eyebrow="Ranking principles" title="What influences local visibility on Google?"
                 sub="Relevance, distance and prominence decide most local results. No provider controls them outright.">
          <Cards rows={c.ranking_factors!} cols="sm:grid-cols-3" />
        </Section>
      )}

      {/* 6. CITY STRATEGY */}
      {(c.city_hubs || []).length > 0 && (
        <Section id="cities" eyebrow="City strategy" title={`Why Local SEO in ${country} needs a city-by-city plan`}
                 sub="Competition, catchment and customer behaviour change by city, so each one gets its own page and its own priorities.">
          <LinkGrid links={c.city_hubs!} />
        </Section>
      )}

      {/* 7. INDUSTRY STRATEGY */}
      {(c.industry_hubs || []).length > 0 && (
        <Section alt id="industries" eyebrow="Industry strategy" title={`Industry-specific Local SEO across ${country}`}
                 sub="Search wording, proof expectations and the conversion action differ by industry.">
          <LinkGrid links={c.industry_hubs!} />
        </Section>
      )}

      {/* 8. SINGLE AND MULTI LOCATION */}
      {((c.single_location_points || []).length > 0 || (c.multi_location_points || []).length > 0) && (
        <Section id="business-models" eyebrow="Operating models" title="Local SEO for one location and for many">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {(c.single_location_points || []).length > 0 && (
              <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <div className="mb-4 flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><MapPin className="h-[18px] w-[18px] text-primary" /></div>
                  <h3 className="text-sm font-bold text-foreground">One location</h3>
                </div>
                <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                  {c.single_location_points!.map((p) => (
                    <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{p}</li>
                  ))}
                </ul>
              </div>
            )}
            {(c.multi_location_points || []).length > 0 && (
              <div className="rounded-2xl border-2 border-primary/40 bg-card p-6 shadow-md">
                <div className="mb-4 flex items-center gap-2.5">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Building className="h-[18px] w-[18px] text-primary" /></div>
                  <h3 className="text-sm font-bold text-foreground">Multi-location brands</h3>
                </div>
                <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                  {c.multi_location_points!.map((p) => (
                    <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />{p}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Section>
      )}

      {/* 9. AI SEARCH */}
      {(c.ai_entity_plan || []).length > 0 && (
        <Section alt id="ai-search" eyebrow="AI search visibility" title="How Local SEO supports AI search discovery"
                 sub="AI answers lean on the same entity clarity and evidence that local search rewards. No provider can guarantee a citation or a recommendation.">
          <Cards rows={c.ai_entity_plan!} cols="sm:grid-cols-2" />
        </Section>
      )}

      {/* 10. SAFEGUARDS */}
      {(c.safeguards || []).length > 0 && (
        <Section id="safeguards" eyebrow="Operational safeguards" title={`Controls for multi-location Local SEO in ${country}`}>
          <Cards rows={c.safeguards!} cols="sm:grid-cols-3" />
        </Section>
      )}

      {/* 11. MONTHLY DELIVERABLES */}
      {(c.monthly_deliverables || []).length > 0 && (
        <Section alt id="deliverables" eyebrow="Monthly deliverables" title="What your business receives each month">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {c.monthly_deliverables!.map((d) => (
              <div key={d} className="flex items-start gap-2.5 rounded-2xl border border-border bg-card p-4 shadow-sm">
                <RefreshCw className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                <span className="text-sm font-semibold text-foreground">{d}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 12. FIRST 90 DAYS */}
      {(c.roadmap_90_days || []).length > 0 && (
        <Section id="process" eyebrow="Implementation" title={`A practical Local SEO rollout for ${country}`}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {c.roadmap_90_days!.map((p, i) => (
              <article key={p.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <span className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{String(i + 1).padStart(2, '0')}</span>
                <h3 className="mt-1 text-sm font-bold text-foreground">{p.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{p.detail}</p>
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 13. BUYER EVALUATION */}
      {(c.buyer_checklist || []).length > 0 && (
        <Section alt id="agency-choice" eyebrow="Decision support" title={`How to evaluate a Local SEO company in ${country}`}>
          <div className="overflow-x-auto">
            <div className="min-w-[680px] overflow-hidden rounded-2xl border border-border shadow-sm">
              <div className="grid grid-cols-3 border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                <div className="p-3.5">Ask for</div>
                <div className="p-3.5">Good evidence</div>
                <div className="p-3.5">Warning sign</div>
              </div>
              {c.buyer_checklist!.map((r, i) => (
                <div key={r.ask} className={`grid grid-cols-3 items-start text-xs ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                  <div className="p-3.5 font-bold text-foreground">{r.ask}</div>
                  <div className="flex items-start gap-1.5 p-3.5 text-muted-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{r.good}</div>
                  <div className="p-3.5 text-muted-foreground">{r.warning}</div>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* 14. PACKAGES AND PRICING */}
      {((c.packages || []).length > 0 || c.package_copy) && (
        <Section id="packages" eyebrow="Packages" title={`Local SEO packages and pricing in ${country}`} sub={c.package_copy}>
          {(c.packages || []).length > 0 && (
            <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
              {c.packages!.map((p) => (
                <article key={p.name} className="flex flex-col rounded-2xl border border-border bg-card p-7 shadow-sm">
                  {p.tag && <span className="self-start rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-primary">{p.tag}</span>}
                  <h3 className="mt-3 text-lg font-extrabold text-foreground">{p.name}</h3>
                  {p.detail && <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{p.detail}</p>}
                  <ul className="mt-4 flex-1 space-y-2.5">
                    {p.features.map((f) => (
                      <li key={f} className="flex items-start gap-2 text-xs text-muted-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{f}</li>
                    ))}
                  </ul>
                  {p.cta_label && p.cta_url && (
                    <a href={sameSite(p.cta_url)}
                       {...(/^https?:/.test(sameSite(p.cta_url)) ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
                       className="mt-6 flex items-center justify-center rounded-lg border border-border bg-muted/30 px-4 py-2.5 text-xs font-bold text-foreground transition-colors hover:border-primary/40 hover:text-primary">
                      {p.cta_label}
                    </a>
                  )}
                </article>
              ))}
            </div>
          )}
          {/* Guardrail 11: no Offer schema and no embedded prices. The note is the
              approved closing line from the package, not template filler. */}
          {c.package_note && <p className="text-center text-[11px] text-muted-foreground">{c.package_note}</p>}
        </Section>
      )}

      {/* 15. PROOF AND REPORTING */}
      {((c.proof_assets || []).length > 0 || (c.audit_checklist || []).length > 0) && (
        <Section alt id="proof" eyebrow="Proof and reporting" title="See what Pinzo measures"
                 sub="The visuals below are labelled samples. They are replaced with approved, anonymised evidence before this page becomes indexable.">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_1fr]">
            {(c.audit_checklist || []).length > 0 && (
              <div className="space-y-4 rounded-2xl border border-border bg-card p-7 shadow-sm">
                <h3 className="flex items-center gap-2 text-sm font-bold text-foreground"><ClipboardCheck className="h-4 w-4 text-primary" /> Sample Pinzo Local SEO audit</h3>
                <ul className="space-y-2.5">
                  {c.audit_checklist!.map((r) => (
                    <li key={r.title} className="grid gap-1 border-b border-border pb-2.5 text-xs last:border-0 last:pb-0 sm:grid-cols-[60%_1fr] sm:gap-4">
                      <span className="font-semibold text-foreground">{r.title}</span>
                      <span className="text-muted-foreground">{r.detail}</span>
                    </li>
                  ))}
                </ul>
                <p className="text-[11px] text-muted-foreground">Illustrative audit format. It is not a client result or a ranking promise.</p>
              </div>
            )}
            {(c.proof_assets || []).length > 0 && (
              <div className="grid grid-cols-1 gap-3">
                {c.proof_assets!.map((a) => (
                  <div key={a.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                    <FileText className="mb-2 h-[18px] w-[18px] text-primary" />
                    <p className="text-sm font-bold text-foreground">{a.title}</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{a.detail}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Section>
      )}

      {/* 16. FAQS (visible copy is the exact source of the FAQPage schema) */}
      {(c.faqs || []).length > 0 && (
        <Section id="faq" eyebrow="Frequently asked questions" title={`Questions about Local SEO services in ${country}`}>
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
        </Section>
      )}

      {/* 17. AUDIT CTA */}
      <section id="audit" className="py-16">
        <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 gap-8 rounded-3xl border border-primary/20 bg-primary/[0.04] p-8 sm:p-10 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="space-y-4">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary"><ShieldCheck className="h-3.5 w-3.5" /> Free visibility review</div>
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground">Find the biggest local visibility gaps in your {country} presence</h2>
              <p className="text-sm leading-relaxed text-muted-foreground">Share your website or Google Maps link. Pinzo reviews profile quality, location-page coverage, reviews, local rankings, technical gaps and lead tracking. No ranking promises, just prioritised opportunities.</p>
              <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-xs font-bold text-primary hover:underline"><Phone className="h-3.5 w-3.5" /> Prefer WhatsApp? Message us</a>
            </div>
            {/* Shared with the leaf pages: stores the lead before emailing, and carries
                the consent, UTM, GCLID and landing-page capture guardrail 12 requires. */}
            <LpseoLeadForm page={`/${page.locale}/local-seo-services/`} submitLabel={primaryCta} />
          </div>
        </div>
      </section>

      {/* 18. RELATED LINKS */}
      {(c.internal_links || []).length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="mb-6 space-y-2 text-center">
            <p className="text-[11px] font-bold uppercase tracking-wider text-primary">Explore related services</p>
            <h2 className="text-xl font-extrabold tracking-tight text-foreground">Continue through the Pinzo Local SEO structure</h2>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {c.internal_links!.map((l) => (
              <SafeLink key={l.url} href={l.url} className="rounded-2xl border border-border bg-card p-4 text-xs font-semibold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary">{l.anchor}</SafeLink>
            ))}
          </div>
        </section>
      )}

      <MarketingFooter />
    </div>
  )
}
