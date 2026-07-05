import Link from 'next/link'
import {
  Check, X, Sparkles, MapPin, MessageSquare, Calendar, Camera, TrendingUp,
  Building, Star, ArrowRight, Search, ListChecks, RefreshCw,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import { buildPseoJsonLd, industryHubPath, rootHubPath, type PseoPageData } from '@/lib/pseo'

/**
 * Programmatic SEO landing page (industry x city), 13-section template.
 * Server component — pure HTML/CSS, no client JS beyond the shared header.
 * Sections with no content in the CMS blob are skipped entirely.
 */
export default function PseoLanding({ page }: { page: PseoPageData }) {
  const c = page.content || {}
  const industry = page.industry_label
  const city = page.city_label
  const jsonLd = buildPseoJsonLd(page)
  const primaryCta = c.primary_cta || 'Start Free Trial'
  const secondaryCta = c.secondary_cta || 'Book a Demo'
  const whatsappDemo = 'https://wa.me/917021052482?text=' + encodeURIComponent(`Hi, I'd like a Pinzo demo for my ${industry.toLowerCase()} business in ${city}.`)

  const SectionHeading = ({ eyebrow, title, sub }: { eyebrow?: string; title: string; sub?: string }) => (
    <div className="mx-auto max-w-3xl space-y-3 text-center">
      {eyebrow && <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">{eyebrow}</div>}
      <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{title}</h2>
      {sub && <p className="text-muted-foreground">{sub}</p>}
    </div>
  )

  const CtaButtons = ({ location }: { location: string }) => (
    <div className="flex flex-col items-center justify-center gap-3 sm:flex-row" data-cta={location}>
      <Link href="/login" className="flex w-full min-w-[220px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 sm:w-auto">
        {primaryCta} <ArrowRight className="h-4 w-4" />
      </Link>
      <a href={whatsappDemo} target="_blank" rel="noopener noreferrer" className="flex w-full min-w-[160px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
        {secondaryCta}
      </a>
    </div>
  )

  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />

      <MarketingHeader />

      {/* Visible breadcrumb (matches BreadcrumbList schema) */}
      <nav aria-label="Breadcrumb" className="mx-auto max-w-5xl px-4 pt-6 sm:px-6 lg:px-8">
        <ol className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
          <li><Link href="/" className="hover:text-foreground">Home</Link></li>
          <li aria-hidden>/</li>
          <li><Link href={rootHubPath(page.locale)} className="hover:text-foreground">GBP Management</Link></li>
          <li aria-hidden>/</li>
          <li><Link href={industryHubPath(page.locale, page.industry_slug)} className="hover:text-foreground">{industry}</Link></li>
          <li aria-hidden>/</li>
          <li className="text-foreground">{city}</li>
        </ol>
      </nav>

      {/* 1. HERO */}
      <section className="mx-auto max-w-5xl space-y-7 px-4 pb-16 pt-10 text-center sm:px-6 lg:px-8">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
          <Sparkles className="h-3.5 w-3.5" />
          <span>{c.badge || `Google Business Profile management for ${industry} in ${city}`}</span>
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{page.h1}</h1>
        {c.hero_sub && <p className="mx-auto max-w-2xl text-base text-muted-foreground sm:text-lg">{c.hero_sub}</p>}
        <CtaButtons location="hero" />
        <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2.5 text-[11px] font-semibold text-muted-foreground">
          {['Free 7-day trial', 'No credit card required', 'Secure Google OAuth', 'Cancel anytime'].map((t) => (
            <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
          ))}
        </div>
      </section>

      {/* 2. WHY GBP MATTERS FOR {INDUSTRY} IN {CITY} */}
      {(c.why_matters_body || (c.why_matters_points || []).length > 0) && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Why Google Business Profile matters for ${industry.toLowerCase()} in ${city}`} sub={c.why_matters_body} />
            {(c.why_matters_points || []).length > 0 && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                {(c.why_matters_points || []).map((p) => (
                  <div key={p} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
                    <TrendingUp className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
                    <span className="text-sm font-medium text-foreground">{p}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      )}

      {/* 3. COMMON GBP PROBLEMS */}
      {(c.problems || []).length > 0 && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Common Google Business Profile problems for ${industry.toLowerCase()}`} />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(c.problems || []).map((p) => (
                <div key={p.title} className="flex h-full flex-col gap-2.5 rounded-xl border border-border bg-card p-5 shadow-sm">
                  <X className="h-5 w-5 text-rose-500" />
                  <h3 className="text-sm font-bold text-foreground">{p.title}</h3>
                  {p.detail && <p className="text-xs leading-relaxed text-muted-foreground">{p.detail}</p>}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 4. HOW PINZO SOLVES THESE */}
      {(c.solutions || []).length > 0 && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="The fix" title="How Pinzo solves these problems" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {(c.solutions || []).map((s) => (
                <div key={s.title} className="flex h-full flex-col gap-2.5 rounded-xl border border-border bg-card p-5 shadow-sm">
                  <Check className="h-5 w-5 text-emerald-500" />
                  <h3 className="text-sm font-bold text-foreground">{s.title}</h3>
                  {s.detail && <p className="text-xs leading-relaxed text-muted-foreground">{s.detail}</p>}
                </div>
              ))}
            </div>
            <div className="pt-2"><CtaButtons location="solutions" /></div>
          </div>
        </section>
      )}

      {/* 5. WHAT TO ADD TO GBP FOR {INDUSTRY} */}
      {((c.gbp_categories || []).length > 0 || (c.gbp_services || []).length > 0 || (c.gbp_attributes || []).length > 0) && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`What ${industry.toLowerCase()} should add to their Google Business Profile`} sub="Complete profiles rank higher and give AI engines more to recommend. Pinzo audits every field and flags what's missing." />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {([
                { label: 'Categories', items: c.gbp_categories || [], icon: Building },
                { label: 'Services', items: c.gbp_services || [], icon: ListChecks },
                { label: 'Attributes & extras', items: c.gbp_attributes || [], icon: Sparkles },
              ] as const).filter((g) => g.items.length > 0).map((g) => (
                <div key={g.label} className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><g.icon className="h-[18px] w-[18px] text-primary" /></div>
                    <h3 className="text-sm font-bold text-foreground">{g.label}</h3>
                  </div>
                  <ul className="space-y-2 text-xs font-medium text-muted-foreground">
                    {g.items.map((it) => (
                      <li key={it} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{it}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 6. REVIEW MANAGEMENT USE CASE */}
      {(c.reviews_body || (c.review_themes || []).length > 0 || c.example_review) && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto grid max-w-6xl grid-cols-1 items-center gap-10 px-4 sm:px-6 lg:grid-cols-2 lg:px-8">
            <div className="space-y-5">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Reputation management</div>
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Review management for {industry.toLowerCase()} in {city}</h2>
              {c.reviews_body && <p className="leading-relaxed text-muted-foreground">{c.reviews_body}</p>}
              {(c.review_themes || []).length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">What customers mention most</p>
                  <div className="flex flex-wrap gap-2">
                    {(c.review_themes || []).map((t) => (
                      <span key={t} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm">{t}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            {c.example_review && (
              <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-lg">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-foreground">Customer review</span>
                  <div className="flex gap-0.5 text-amber-400">{[...Array(5)].map((_, i) => <Star key={i} className="h-3 w-3 fill-current" />)}</div>
                </div>
                <p className="text-xs italic leading-relaxed text-muted-foreground">&quot;{c.example_review}&quot;</p>
                {c.example_reply && (
                  <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3.5">
                    <div className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-primary" /><span className="text-[10px] font-bold uppercase tracking-wide text-primary">AI drafted reply</span></div>
                    <p className="text-xs leading-normal text-foreground">&quot;{c.example_reply}&quot;</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      )}

      {/* 7. GOOGLE POSTS IDEAS */}
      {(c.post_ideas || []).length > 0 && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Stay active on Google" title={`Google Posts ideas for ${industry.toLowerCase()}`} sub="Fresh posts signal an active business to Google and to AI engines. Schedule these across every location with Pinzo." />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(c.post_ideas || []).map((idea) => (
                <div key={idea} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
                  <Calendar className="mt-0.5 h-[18px] w-[18px] shrink-0 text-primary" />
                  <span className="text-sm font-medium text-foreground">{idea}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 8. PHOTO / CONTENT CHECKLIST */}
      {(c.photo_checklist || []).length > 0 && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Photo & content checklist for ${industry.toLowerCase()}`} sub="Profiles with complete, current photos get more calls and direction requests." />
            <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(c.photo_checklist || []).map((item) => (
                <li key={item} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 text-sm font-medium text-foreground shadow-sm">
                  <Camera className="mt-0.5 h-[18px] w-[18px] shrink-0 text-primary" />{item}
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}

      {/* 9. WHY {CITY} BUSINESSES NEED STRONGER LOCAL VISIBILITY */}
      {(c.city_visibility_body || (c.neighborhoods || []).length > 0) && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Why ${city} businesses need stronger local visibility`} sub={c.city_visibility_body} />
            {(c.neighborhoods || []).length > 0 && (
              <div className="space-y-3 text-center">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Areas where customers search in {city}</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {(c.neighborhoods || []).map((n) => (
                    <span key={n} className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm">
                      <MapPin className="h-3.5 w-3.5 text-primary" />{n}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* 10. SINGLE-LOCATION VS MULTI-LOCATION */}
      {((c.single_points || []).length > 0 || (c.multi_points || []).length > 0) && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title="One location or one hundred — Pinzo fits" />
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {(c.single_points || []).length > 0 && (
                <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
                  <div className="mb-4 flex items-center gap-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><MapPin className="h-[18px] w-[18px] text-primary" /></div>
                    <h3 className="text-sm font-bold text-foreground">Single-location {industry.toLowerCase()}</h3>
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
                    <h3 className="text-sm font-bold text-foreground">Multi-location &amp; franchises</h3>
                  </div>
                  <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                    {(c.multi_points || []).map((p) => (
                      <li key={p} className="flex items-start gap-2"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />{p}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* 11. MONTHLY PINZO WORKFLOW */}
      {(c.monthly_workflow || []).length > 0 && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="What running it looks like" title="Your monthly workflow with Pinzo" />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {(c.monthly_workflow || []).map((step, i) => (
                <div key={step.title} className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm">
                  <div className="flex items-center justify-between">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><RefreshCw className="h-[18px] w-[18px] text-primary" /></div>
                    <span className="text-xl font-extrabold text-muted-foreground/20">{String(i + 1).padStart(2, '0')}</span>
                  </div>
                  <h3 className="text-sm font-bold text-foreground">{step.title}</h3>
                  {step.detail && <p className="text-xs leading-relaxed text-muted-foreground">{step.detail}</p>}
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 12. FAQS */}
      {(c.faqs || []).length > 0 && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title="Frequently asked questions" />
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
          </div>
        </section>
      )}

      {/* 13. FINAL CTA */}
      <section className="mx-auto max-w-5xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-primary/5 p-8 text-center sm:p-12">
          <div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl" />
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            {c.final_heading || `Grow your ${industry.toLowerCase()} visibility in ${city}`}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">
            {c.final_sub || `Connect your Google Business Profile and see your health score, review gaps and local visibility in minutes. Free 7-day trial, no card required.`}
          </p>
          <div className="pt-6"><CtaButtons location="footer" /></div>
        </div>
        {/* Internal links for crawl depth — spoke back up to the hubs + editorial links. */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs font-semibold text-muted-foreground">
          <Link href={industryHubPath(page.locale, page.industry_slug)} className="inline-flex items-center gap-1.5 hover:text-foreground"><MapPin className="h-3.5 w-3.5" />{industry} in other cities</Link>
          <Link href={rootHubPath(page.locale)} className="inline-flex items-center gap-1.5 hover:text-foreground"><Building className="h-3.5 w-3.5" />All industries</Link>
          <Link href="/" className="inline-flex items-center gap-1.5 hover:text-foreground"><Search className="h-3.5 w-3.5" />AI Visibility platform</Link>
          <Link href="/pricing" className="inline-flex items-center gap-1.5 hover:text-foreground"><ListChecks className="h-3.5 w-3.5" />Pricing</Link>
          {(c.related_pages || []).map((r) => (
            <a key={r.url} href={r.url} className="inline-flex items-center gap-1.5 hover:text-foreground"><ArrowRight className="h-3.5 w-3.5" />{r.anchor}</a>
          ))}
        </div>
      </section>

      <MarketingFooter />
    </div>
  )
}
