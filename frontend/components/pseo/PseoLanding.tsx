import Link from 'next/link'
import {
  Check, X, Sparkles, MapPin, MessageSquare, Calendar, Camera, TrendingUp,
  Building, Star, ArrowRight, Search, ListChecks, RefreshCw,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import { buildPseoJsonLd, industryHubPath, rootHubPath, pseoPath, type PseoPageData, type PseoListItem } from '@/lib/pseo'

/**
 * Programmatic SEO landing page (industry x city), 13-section template.
 * Server component — pure HTML/CSS, no client JS beyond the shared header.
 * Sections with no content in the CMS blob are skipped entirely.
 */
export default function PseoLanding({ page, siblings = [] }: { page: PseoPageData; siblings?: PseoListItem[] }) {
  const c = page.content || {}
  const industry = page.industry_label
  const city = page.city_label
  const jsonLd = buildPseoJsonLd(page)
  const primaryCta = c.primary_cta || 'Start Free Trial'
  const secondaryCta = c.secondary_cta || 'Book a Demo'
  // Non-India pSEO pages present pricing in USD by default; India (country 'in') stays in ₹.
  // Display-only: Razorpay still charges INR. 'From' price = Lite plan (₹999/mo); the USD
  // figure uses the same 1 USD = ₹100 peg as /pricing.
  const isIndia = page.country === 'in'
  const fromPrice = isIndia ? '₹999' : '$10'
  const pricingHref = isIndia ? '/pricing' : '/pricing?ccy=usd'
  const whatsappDemo = 'https://wa.me/917715845972?text=' + encodeURIComponent(`Hi, I'd like a Pinzo demo for my ${industry.toLowerCase()} business in ${city}.`)

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

  // Contextual internal links (audit §8). The targets are identical on every pSEO
  // page — only locale/industry swap — so they're derived here, not entered per page
  // or via CSV. Point ONLY at routes that exist today (broken links hurt SEO); when
  // the /features/* pages ship, add their href here and every page links them.
  // Per-page `content.internal_links` (with a `section`) still merge in as overrides.
  const defaultLinks: Record<string, { anchor: string; href: string }[]> = {
    solutions: [{ anchor: 'Run a free GBP audit', href: '/features/gbp-audit' }],
    reviews: [{ anchor: `AI review replies for ${industry.toLowerCase()}`, href: '/features/ai-review-replies' }],
    posts: [{ anchor: 'Google Posts scheduler', href: '/features/google-posts-scheduler' }],
    city: [{ anchor: 'Local rank tracking', href: '/features/local-rank-tracker' }],
    multi: [{ anchor: 'Multi-location GBP dashboard', href: '/features/multi-location-gbp-management' }],
  }
  const RelatedLinks = ({ section }: { section: string }) => {
    const cms = (c.internal_links || []).filter((l) => l.section === section).map((l) => ({ anchor: l.anchor, href: l.url }))
    const seen = new Set<string>()
    const links = [...(defaultLinks[section] || []), ...cms].filter((l) => !seen.has(l.href) && seen.add(l.href))
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

  // Audit-added sections. Comparison + audit checklist are near-constant, so they
  // default here and render on every page; per-page CMS values override them. The
  // answer block defaults from the industry/city; review examples fall back to the
  // legacy single example so nothing regresses.
  const answerBlock = c.answer_block || `Google Business Profile management for ${industry.toLowerCase()} in ${city} means keeping the profile updated with correct business information, categories, services, product photos, customer reviews, Google Posts, offers and performance tracking — so local customers can find and trust the business on Google Search and Maps.`
  const comparison = (c.comparison && c.comparison.length > 0) ? c.comparison : [
    { point: 'Review replies', manual: 'Written one by one — some slip through', pinzo: 'AI drafts every reply in your tone; you approve' },
    { point: 'Google Posts', manual: 'Posted ad hoc, with visible gaps', pinzo: 'Scheduled ahead across every location' },
    { point: 'Profile audits', manual: 'No clear view of what’s missing', pinzo: 'Health Score with a prioritized fix list' },
    { point: 'Multiple locations', manual: 'Log into each listing separately', pinzo: 'One dashboard for every profile' },
    { point: 'Local visibility', manual: 'Guesswork on where you rank', pinzo: 'Geo-grid rank tracking, street by street' },
    { point: 'Reporting', manual: 'Manual spreadsheets', pinzo: 'Calls, directions and clicks in one report' },
  ]
  const auditChecklist = (c.audit_checklist && c.audit_checklist.length > 0) ? c.audit_checklist : [
    'Profile completeness check', 'Category and service gap check', 'Review reply gap check',
    'Google Posts activity check', 'Photo freshness check', 'Competitor profile comparison',
    'Branch information consistency check', 'Local visibility improvement opportunities',
  ]
  const reviewExamples = (c.review_examples && c.review_examples.length > 0)
    ? c.review_examples
    : (c.example_review ? [{ review: c.example_review, reply: c.example_reply || '' }] : [])

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
          {['Free audit — no card', '7-day trial — no charge today', 'Secure Google OAuth', 'Cancel anytime'].map((t) => (
            <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
          ))}
        </div>
        <p className="text-xs font-medium text-muted-foreground">
          Plans from <span className="font-semibold text-foreground">{fromPrice}/mo</span>
          {' · '}
          <Link href={pricingHref} className="underline underline-offset-2 hover:text-foreground">see full pricing</Link>
        </p>
      </section>

      {/* 1b. DIRECT ANSWER (AEO) — extractable definition under the hero */}
      <section className="pb-6">
        <div className="mx-auto max-w-3xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <h2 className="mb-3 text-lg font-bold text-foreground">What is Google Business Profile management for {industry.toLowerCase()} in {city}?</h2>
            <p className="leading-relaxed text-muted-foreground">{answerBlock}</p>
          </div>
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
            <RelatedLinks section="solutions" />
          </div>
        </section>
      )}

      {/* 4b. MANUAL VS PINZO COMPARISON */}
      <section className="py-16">
        <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
          <SectionHeading eyebrow="Manual vs Pinzo" title="Doing it by hand vs running it with Pinzo" />
          <div className="overflow-hidden rounded-2xl border border-border shadow-sm">
            <div className="grid grid-cols-3 border-b border-border bg-muted/30 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              <div className="p-3.5" />
              <div className="p-3.5 text-center">Manual management</div>
              <div className="p-3.5 text-center text-primary">With Pinzo</div>
            </div>
            {comparison.map((row, i) => (
              <div key={row.point} className={`grid grid-cols-3 items-start text-xs ${i % 2 ? 'bg-muted/10' : 'bg-card'}`}>
                <div className="p-3.5 font-bold text-foreground">{row.point}</div>
                <div className="flex items-start gap-1.5 p-3.5 text-muted-foreground"><X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-rose-500" />{row.manual}</div>
                <div className="flex items-start gap-1.5 p-3.5 font-medium text-foreground"><Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-500" />{row.pinzo}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. WHAT TO ADD TO GBP FOR {INDUSTRY} */}
      {((c.gbp_categories || []).length > 0 || (c.gbp_services || []).length > 0 || (c.gbp_attributes || []).length > 0) && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`What ${industry.toLowerCase()} should add to their Google Business Profile`} sub="A complete, active profile gives customers clearer information and helps search systems better understand your business. Pinzo audits every field and flags what's missing." />
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

      {/* 6. REVIEW MANAGEMENT USE CASE — centered header + responsive review grid */}
      {(c.reviews_body || (c.review_themes || []).length > 0 || reviewExamples.length > 0) && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-6xl space-y-10 px-4 sm:px-6 lg:px-8">
            <div className="mx-auto max-w-3xl space-y-4 text-center">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Reputation management</div>
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Review management for {industry.toLowerCase()} in {city}</h2>
              {c.reviews_body && <p className="leading-relaxed text-muted-foreground">{c.reviews_body}</p>}
              {(c.review_themes || []).length > 0 && (
                <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
                  {(c.review_themes || []).map((t) => (
                    <span key={t} className="rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm">{t}</span>
                  ))}
                </div>
              )}
            </div>
            {reviewExamples.length > 0 && (
              // 1 -> centered single; 2 -> two columns; 3+ -> three columns; all stack to 1 on mobile.
              <div className={
                reviewExamples.length === 1 ? 'mx-auto max-w-2xl'
                : reviewExamples.length === 2 ? 'mx-auto grid max-w-4xl gap-4 sm:grid-cols-2'
                : 'grid gap-4 sm:grid-cols-2 lg:grid-cols-3'
              }>
                {reviewExamples.map((ex, i) => (
                  <div key={i} className="flex h-full flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-lg">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-foreground">Example review</span>
                      <div className="flex gap-0.5 text-amber-400">{[...Array(5)].map((_, j) => <Star key={j} className="h-3 w-3 fill-current" />)}</div>
                    </div>
                    <p className="text-xs italic leading-relaxed text-muted-foreground">&quot;{ex.review}&quot;</p>
                    {ex.reply && (
                      <div className="mt-auto space-y-2 rounded-lg border border-border bg-muted/30 p-3.5">
                        <div className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-primary" /><span className="text-[10px] font-bold uppercase tracking-wide text-primary">AI drafted reply</span></div>
                        <p className="text-xs leading-normal text-foreground">&quot;{ex.reply}&quot;</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {reviewExamples.length > 0 && (
              <p className="text-center text-[11px] text-muted-foreground">
                Illustrative examples showing how customer reviews and AI-drafted replies appear inside Pinzo for {industry.toLowerCase()} businesses — not real customer reviews.
              </p>
            )}
            <RelatedLinks section="reviews" />
          </div>
        </section>
      )}

      {/* 7. GOOGLE POSTS IDEAS */}
      {(c.post_ideas || []).length > 0 && (
        <section className="py-16">
          <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading eyebrow="Stay active on Google" title={`Google Posts ideas for ${industry.toLowerCase()}`} sub="Fresh posts help customers see recent offers, collections, announcements and updates when they view your profile. Schedule these across every location with Pinzo." />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(c.post_ideas || []).map((idea) => (
                <div key={idea} className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
                  <Calendar className="mt-0.5 h-[18px] w-[18px] shrink-0 text-primary" />
                  <span className="text-sm font-medium text-foreground">{idea}</span>
                </div>
              ))}
            </div>
            <RelatedLinks section="posts" />
          </div>
        </section>
      )}

      {/* 8. PHOTO / CONTENT CHECKLIST */}
      {(c.photo_checklist || []).length > 0 && (
        <section className="border-y border-border/40 bg-muted/10 py-16">
          <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
            <SectionHeading title={`Photo & content checklist for ${industry.toLowerCase()}`} sub="Current, real photos can improve customer trust before customers call or ask for directions." />
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
      {(c.city_visibility_body || (c.neighborhoods || []).length > 0 || siblings.length > 0) && (
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
            {siblings.length > 0 && (
              <div className="space-y-3 text-center">
                <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">{industry} in other cities</p>
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {siblings.map((s) => (
                    <Link key={s.slug} href={pseoPath(s.locale, s.slug)} className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs font-bold text-foreground shadow-sm transition-colors hover:border-primary/40 hover:text-primary">
                      <MapPin className="h-3.5 w-3.5 text-primary" />{s.city_label}
                    </Link>
                  ))}
                </div>
              </div>
            )}
            <RelatedLinks section="city" />
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
            <RelatedLinks section="multi" />
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

      {/* 11b. FREE AUDIT / PROOF BLOCK (CRO §7.1) */}
      <section className="py-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8">
          <div className="rounded-3xl border border-primary/20 bg-primary/5 p-8 sm:p-10">
            <div className="mx-auto max-w-2xl space-y-3 text-center">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Free audit</div>
              <h2 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">See what your free {industry.toLowerCase()} GBP audit includes</h2>
              <p className="text-sm text-muted-foreground">Connect Google and get a Health Score for your {city} profile in minutes. Secure Google OAuth — no password sharing.</p>
            </div>
            <ul className="mx-auto mt-7 grid max-w-3xl grid-cols-1 gap-2.5 sm:grid-cols-2">
              {auditChecklist.map((item) => (
                <li key={item} className="flex items-start gap-2.5 rounded-xl border border-border bg-card p-3.5 text-sm font-medium text-foreground shadow-sm">
                  <ListChecks className="mt-0.5 h-[18px] w-[18px] shrink-0 text-primary" />{item}
                </li>
              ))}
            </ul>
            <div className="mt-8"><CtaButtons location="audit" /></div>
          </div>
        </div>
      </section>

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
            {c.final_sub || `Connect your Google Business Profile and see your health score, review gaps and local visibility in minutes. Free audit with no card, then a 7-day free trial — no charge today.`}
          </p>
          <div className="pt-6"><CtaButtons location="footer" /></div>
        </div>
        {/* Internal links for crawl depth — spoke back up to the hubs + editorial links. */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs font-semibold text-muted-foreground">
          <Link href={industryHubPath(page.locale, page.industry_slug)} className="inline-flex items-center gap-1.5 hover:text-foreground"><MapPin className="h-3.5 w-3.5" />{industry} in other cities</Link>
          <Link href={rootHubPath(page.locale)} className="inline-flex items-center gap-1.5 hover:text-foreground"><Building className="h-3.5 w-3.5" />All industries</Link>
          <Link href="/" className="inline-flex items-center gap-1.5 hover:text-foreground"><Search className="h-3.5 w-3.5" />AI Visibility platform</Link>
          <Link href={pricingHref} className="inline-flex items-center gap-1.5 hover:text-foreground"><ListChecks className="h-3.5 w-3.5" />Pricing</Link>
          {(c.related_pages || []).map((r) => (
            <a key={r.url} href={r.url} className="inline-flex items-center gap-1.5 hover:text-foreground"><ArrowRight className="h-3.5 w-3.5" />{r.anchor}</a>
          ))}
        </div>
      </section>

      <MarketingFooter />
    </div>
  )
}
