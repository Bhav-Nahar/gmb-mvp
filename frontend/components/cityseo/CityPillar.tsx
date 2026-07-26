import Link from 'next/link'
import {
  Sparkles, Check, MapPin, ArrowRight, ShieldCheck, BarChart3, Bot,
  Globe, Compass, Phone, FileText, HelpCircle, CalendarClock,
} from 'lucide-react'
import { canLink } from '@/lib/lpseo'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import LpseoLeadForm from '@/components/lpseo/LpseoLeadForm'
import { buildCityJsonLd, countryHubPath, type CityPageData, type CitySectionKey } from '@/lib/cityseo'

/**
 * City pillar (Local SEO universe), served at /{locale}/local-seo-services/{city-slug}.
 * Server component: the only client JS is the shared header and the lead form.
 *
 * Section order follows the approved city-pillar template
 * (pinzo-local-seo-city-pillar-template-and-guardrails.md, "Recommended page structure").
 *
 * ONE RULE, the same one CseoPillar follows: this template ships NO fallback copy.
 * Every visible string below comes from the import, and a section whose content the
 * import did not supply renders nothing at all. A city page half-filled with generic
 * defaults is the "city name replacement" the guardrails explicitly forbid, and a
 * blend of imported and invented copy is impossible to QA. A gap shows up as a gap.
 *
 * Guardrail: no U+2013, U+2014, U+2011 or U+2212 in any visible string here.
 *
 * The FAQ block and the FAQPage schema both read content.faqs, so the visible answer
 * and the marked-up answer are the same string. The package's schema_json column is
 * never imported.
 */
export default function CityPillar({ page, livePaths = new Set<string>() }: { page: CityPageData; livePaths?: Set<string> }) {
  const c = page.content || {}

  // Never render an anchor to a page that does not exist yet (guardrail: no links
  // to planned pages). Unpublished destinations degrade to plain text.
  const SafeLink = ({ href, className, children }: { href: string; className?: string; children: React.ReactNode }) =>
    canLink(href, livePaths)
      ? <Link href={href} className={className}>{children}</Link>
      : <span className={className} aria-disabled>{children}</span>
  const city = page.city_label
  const jsonLd = buildCityJsonLd(page)
  const eyebrows = c.section_eyebrows || {}
  const eb = (k: CitySectionKey) => eyebrows[k]
  const whatsapp = 'https://wa.me/917715845972?text=' + encodeURIComponent(
    `Hi, I'd like a Pinzo local SEO audit for my business in ${city}.`)

  // Links section 11 already renders, normalised so a trailing slash is not a
  // different destination.
  const norm = (u: string) => u.replace(/\/+$/, '').toLowerCase()
  const grouped = new Set((c.industry_link_groups || []).flatMap((g) => g.links.map((l) => norm(l.url))))
  const extraLinks = (c.internal_links || []).filter((l) => !grouped.has(norm(l.url)))

  const Section = ({ id, eyebrow, title, sub, children, alt }: {
    id?: string; eyebrow?: string; title: string; sub?: string
    children?: React.ReactNode; alt?: boolean
  }) => (
    <section id={id} className={alt ? 'border-y border-border/40 bg-muted/10 py-16' : 'py-16'}>
      <div className="mx-auto max-w-6xl space-y-8 px-4 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl space-y-3 text-center">
          {eyebrow && <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">{eyebrow}</div>}
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{title}</h2>
          {sub && <p className="text-muted-foreground">{sub}</p>}
        </div>
        {children}
      </div>
    </section>
  )

  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />

      <MarketingHeader />

      {/* 1. BREADCRUMBS */}
      <nav aria-label="Breadcrumb" className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 lg:px-8">
        <ol className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
          <li><Link href="/" className="hover:text-foreground">Home</Link></li>
          <li aria-hidden>/</li>
          <li><Link href="/local-seo-services" className="hover:text-foreground">Local SEO Services</Link></li>
          {c.country_label && (
            <>
              <li aria-hidden>/</li>
              <li><Link href={countryHubPath(page.locale)} className="hover:text-foreground">{c.country_label}</Link></li>
            </>
          )}
          <li aria-hidden>/</li>
          <li className="text-foreground">{city}</li>
        </ol>
      </nav>

      {/* 2. HERO */}
      <section className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-16 pt-10 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:px-8">
        <div className="space-y-6">
          {c.hero_eyebrow && (
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
              <Sparkles className="h-3.5 w-3.5" />{c.hero_eyebrow}
            </div>
          )}
          <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{page.h1}</h1>
          {c.hero_copy && <p className="max-w-xl text-base text-muted-foreground sm:text-lg">{c.hero_copy}</p>}
          {(c.primary_cta || c.secondary_cta) && (
            <div className="flex flex-col gap-3 sm:flex-row">
              {c.primary_cta && (
                <a href="#audit" className="flex w-full min-w-[240px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 sm:w-auto">
                  {c.primary_cta} <ArrowRight className="h-4 w-4" />
                </a>
              )}
              {c.secondary_cta && (
                <a href="/login" className="flex w-full min-w-[180px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
                  {c.secondary_cta}
                </a>
              )}
            </div>
          )}
          {(c.hero_trust_points || []).length > 0 && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2.5 text-[11px] font-semibold text-muted-foreground">
              {c.hero_trust_points!.map((t) => (
                <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
              ))}
            </div>
          )}
        </div>
        {c.hero_image_alt && (
          <figure className="rounded-3xl border border-border bg-card p-4 shadow-xl">
            <div role="img" aria-label={c.hero_image_alt}>
              <div className="flex items-center justify-between px-1 pb-3">
                <div className="flex items-center gap-2 text-xs font-bold text-foreground"><BarChart3 className="h-4 w-4 text-primary" /> {city} visibility</div>
                <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Illustrative</span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {(c.catchment_areas || []).slice(0, 6).map((a, i) => (
                  <div key={a.name} className="rounded-xl border border-border bg-background p-3">
                    <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{a.name}</p>
                    <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-primary" style={{ width: `${[72, 58, 64, 45, 51, 38][i] ?? 50}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {c.hero_image_caption && <figcaption className="mt-3 text-[10px] text-muted-foreground">{c.hero_image_caption}</figcaption>}
          </figure>
        )}
      </section>

      {/* 3. DIRECT ANSWER */}
      {c.direct_question && c.direct_answer && (
        <section className="pb-10">
          <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
              {eb('answer') && <p className="mb-2 text-[11px] font-bold uppercase tracking-wider text-primary">{eb('answer')}</p>}
              <h2 className="mb-3 text-lg font-bold text-foreground">{c.direct_question}</h2>
              <div className="space-y-3 leading-relaxed text-muted-foreground">
                <p>{c.direct_answer}</p>
                {c.direct_answer_support && <p>{c.direct_answer_support}</p>}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 4. CITY CATCHMENTS */}
      {c.catchment_heading && (c.catchment_areas || []).length > 0 && (
        <Section alt id="catchments" eyebrow={eb('catchments')} title={c.catchment_heading} sub={c.catchment_intro}>
          {/* content.city_context is deliberately NOT rendered here. It is the
              package's summary of this section, and its first sentence repeats
              catchment_heading word for word. See lib/cityseo.ts. */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {c.catchment_areas!.map((a) => (
              <article key={a.name} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <h3 className="flex items-center gap-2 text-sm font-bold text-foreground">
                  <MapPin className="h-4 w-4 shrink-0 text-primary" />{a.name}
                </h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{a.detail}</p>
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 5. FULL SERVICE SCOPE */}
      {c.service_scope_heading && (c.service_scope || []).length > 0 && (
        <Section id="services" eyebrow={eb('scope')} title={c.service_scope_heading}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {c.service_scope!.map((s, i) => (
              <article key={s.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <span className="text-[11px] font-extrabold uppercase tracking-widest text-primary">{s.num || String(i + 1).padStart(2, '0')}</span>
                <h3 className="mt-1 text-sm font-bold text-foreground">{s.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{s.detail}</p>
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 6. RELEVANCE, DISTANCE AND PROMINENCE */}
      {c.ranking_heading && (c.ranking_factors || []).length > 0 && (
        <Section alt id="how-rankings-work" eyebrow={eb('ranking')} title={c.ranking_heading}>
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-[1fr_1.1fr]">
            {(c.ranking_intro || []).length > 0 && (
              <div className="space-y-3 text-sm leading-relaxed text-muted-foreground">
                {c.ranking_intro!.map((p) => <p key={p.slice(0, 40)}>{p}</p>)}
              </div>
            )}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {c.ranking_factors!.map((f) => (
                <article key={f.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <Compass className="mb-2 h-[18px] w-[18px] text-primary" />
                  <h3 className="text-sm font-bold text-foreground">{f.title}</h3>
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{f.detail}</p>
                </article>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* 7. ONE LOCATION VS MANY (the reference table, all three columns intact) */}
      {c.operating_model_heading && (c.operating_model_rows || []).length > 0 && (
        <Section id="operating-model" eyebrow={eb('operating_model')} title={c.operating_model_heading}>
          <div className="overflow-x-auto">
            <div className="min-w-[720px] overflow-hidden rounded-3xl border border-border shadow-sm">
              {(c.operating_model_columns || []).length === 3 && (
                <div className="grid grid-cols-[200px_1fr_1fr] border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
                  {c.operating_model_columns!.map((h) => <div key={h} className="p-3.5">{h}</div>)}
                </div>
              )}
              {c.operating_model_rows!.map((r, i) => (
                <div key={r.area} className={`grid grid-cols-[200px_1fr_1fr] items-start border-b border-border last:border-0 ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                  <div className="flex items-center gap-2.5 p-3.5 text-sm font-bold text-foreground">
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Globe className="h-4 w-4 text-primary" /></span>
                    {r.area}
                  </div>
                  <p className="p-3.5 text-xs leading-relaxed text-muted-foreground">{r.single}</p>
                  <p className="p-3.5 text-xs leading-relaxed text-foreground">{r.multi}</p>
                </div>
              ))}
            </div>
          </div>
        </Section>
      )}

      {/* 8. 90 DAY FOUNDATION */}
      {c.roadmap_heading && (c.roadmap_phases || []).length > 0 && (
        <Section alt id="process" eyebrow={eb('roadmap')} title={c.roadmap_heading}>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {c.roadmap_phases!.map((p) => (
              <article key={p.title} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-primary">
                  <CalendarClock className="h-3 w-3" />{p.days}
                </span>
                <h3 className="mt-2.5 text-sm font-bold text-foreground">{p.title}</h3>
                <ul className="mt-3 space-y-2.5 text-xs text-muted-foreground">
                  {p.steps.map((s) => (
                    <li key={s} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{s}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
          {c.roadmap_note && <p className="mx-auto max-w-3xl text-center text-xs leading-relaxed text-muted-foreground">{c.roadmap_note}</p>}
        </Section>
      )}

      {/* 9. EVIDENCE AND REPORTING */}
      {c.proof_heading && (c.proof_metrics || []).length > 0 && (
        <Section id="proof" eyebrow={eb('proof')} title={c.proof_heading} sub={c.proof_intro}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {c.proof_metrics!.map((m) => (
              <div key={m.label} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <FileText className="mb-2 h-[18px] w-[18px] text-primary" />
                <p className="text-sm font-bold text-foreground">{m.label}</p>
                <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{m.detail}</p>
              </div>
            ))}
          </div>
          {/* The reference page carries a report screenshot here. It renders only when
              the import supplies BOTH a verified asset and its alt text: an <img> with
              no src is a broken image, and a src with no alt fails the alt-text
              guardrail. No placeholder stands in for a missing asset. */}
          {c.proof_asset_url && c.proof_image_alt && (
            /* eslint-disable-next-line @next/next/no-img-element */
            <img
              src={c.proof_asset_url}
              alt={c.proof_image_alt}
              loading="lazy"
              className="mx-auto w-full max-w-4xl rounded-2xl border border-border shadow-sm"
            />
          )}
          {(c.proof_asset_type || []).length > 0 && (
            <p className="text-center text-[11px] text-muted-foreground">
              Evidence supplied before launch: {c.proof_asset_type!.join(', ')}. The tiles above describe what is
              measured. They are not client results and not a ranking promise.
            </p>
          )}
        </Section>
      )}

      {/* 10. AI SEARCH READINESS */}
      {c.ai_heading && (c.ai_entity_signals || []).length > 0 && (
        <Section alt id="ai-search" eyebrow={eb('ai')} title={c.ai_heading}>
          <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
            <div className="space-y-3 text-sm leading-relaxed text-muted-foreground">
              {(c.ai_intro || []).map((p) => <p key={p.slice(0, 40)}>{p}</p>)}
              {c.ai_entity_plan && <p>{c.ai_entity_plan}</p>}
            </div>
            <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
              {c.ai_signals_heading && (
                <h3 className="flex items-center gap-2 text-sm font-bold text-foreground"><Bot className="h-4 w-4 text-primary" />{c.ai_signals_heading}</h3>
              )}
              <ul className="mt-3 space-y-2.5 text-xs text-muted-foreground">
                {c.ai_entity_signals!.map((s) => (
                  <li key={s} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{s}</li>
                ))}
              </ul>
            </div>
          </div>
        </Section>
      )}

      {/* 11. INDUSTRY CHILD PAGES */}
      {c.industry_links_heading && (c.industry_link_groups || []).length > 0 && (
        <Section id="industries" eyebrow={eb('industry_links')} title={c.industry_links_heading} sub={c.industry_links_intro}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {c.industry_link_groups!.map((g) => (
              <div key={g.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <h3 className="text-sm font-bold text-foreground">{g.title}</h3>
                <ul className="mt-3 space-y-2">
                  {g.links.map((l) => (
                    <li key={l.url}>
                      <SafeLink href={l.url} className="flex items-center justify-between gap-2 text-xs font-semibold text-muted-foreground transition-colors hover:text-primary">
                        {l.anchor} <ArrowRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
                      </SafeLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 12. CHOOSING A PARTNER */}
      {c.partner_heading && (c.partner_questions || []).length > 0 && (
        <Section alt id="choosing-a-partner" eyebrow={eb('partner')} title={c.partner_heading}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {c.partner_questions!.map((q) => (
              <article key={q.title} className="rounded-2xl border border-border bg-card p-5 shadow-sm">
                <HelpCircle className="mb-2 h-[18px] w-[18px] text-primary" />
                <h3 className="text-sm font-bold text-foreground">{q.title}</h3>
                <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">{q.detail}</p>
              </article>
            ))}
          </div>
        </Section>
      )}

      {/* 13. FAQS (this visible copy is the exact source of the FAQPage schema) */}
      {c.faq_heading && (c.faqs || []).length > 0 && (
        <Section id="faq" eyebrow={eb('faq')} title={c.faq_heading}>
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

      {/* 14. LEAD FORM. Shared with every other Local SEO page: it stores the lead
             before emailing, which the package's formsubmit.co destination does not. */}
      {c.lead_heading && (
        <section id="audit" className="py-16">
          <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
            <div className="grid grid-cols-1 gap-8 rounded-3xl border border-primary/20 bg-primary/[0.04] p-8 sm:p-10 lg:grid-cols-[0.9fr_1.1fr]">
              <div className="space-y-4">
                {c.lead_eyebrow && (
                  <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">
                    <ShieldCheck className="h-3.5 w-3.5" /> {c.lead_eyebrow}
                  </div>
                )}
                <h2 className="text-3xl font-extrabold tracking-tight text-foreground">{c.lead_heading}</h2>
                {c.lead_intro && <p className="text-sm leading-relaxed text-muted-foreground">{c.lead_intro}</p>}
                {(c.lead_points || []).length > 0 && (
                  <ul className="space-y-2 text-xs font-semibold text-muted-foreground">
                    {c.lead_points!.map((p) => (
                      <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{p}</li>
                    ))}
                  </ul>
                )}
                <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-2 text-xs font-bold text-primary hover:underline">
                  <Phone className="h-3.5 w-3.5" /> Prefer WhatsApp? Message us
                </a>
              </div>
              <div className="space-y-3">
                <LpseoLeadForm page={`/${page.locale}/local-seo-services/${page.slug}`} submitLabel={c.primary_cta} />
                {c.lead_consent_note && (
                  <p className="text-[11px] leading-relaxed text-muted-foreground">{c.lead_consent_note}</p>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* 15. FOOTER LINKS. Only destinations the industry-links section did not
             already link. `internal_links` is the package's flat list of every
             contextual link on the page, so rendering it whole reprints section 11
             tile for tile: nine identical URLs under a second heading, which is the
             "context free link wall" the guardrails forbid. Nothing left to add means
             no section, not a duplicate one. */}
      {extraLinks.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
          <div className="mb-6 space-y-2 text-center">
            <p className="text-[11px] font-bold uppercase tracking-wider text-primary">Explore related services</p>
            <h2 className="text-xl font-extrabold tracking-tight text-foreground">Continue through the Pinzo Local SEO structure</h2>
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {extraLinks.map((l) => (
              <SafeLink key={l.url} href={l.url} className="rounded-2xl border border-border bg-card p-4 text-xs font-semibold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary">{l.anchor}</SafeLink>
            ))}
          </div>
        </section>
      )}

      <MarketingFooter />
    </div>
  )
}
