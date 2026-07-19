import Link from 'next/link'
import {
  Check, ArrowRight, Sparkles, MessageSquare, Map, Calendar, Building,
  LayoutDashboard, Globe, BarChart2, RefreshCw,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import { buildFeatureJsonLd, getFeature, type Feature } from '@/lib/features'

// Feature icons referenced by name in the content map.
const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  MessageSquare, Sparkles, Map, Calendar, Building, LayoutDashboard, Globe, BarChart2,
}

/** Marketing landing page for a single Pinzo feature. Server component, no client JS. */
export default function FeatureLanding({ feature }: { feature: Feature }) {
  const f = feature
  const jsonLd = buildFeatureJsonLd(f)
  const HeroIcon = ICONS[f.icon] || Sparkles
  const whatsappDemo = 'https://wa.me/917021052482?text=' + encodeURIComponent(`Hi, I'd like a Pinzo demo — interested in ${f.name}.`)
  const related = f.related.map(getFeature).filter(Boolean) as Feature[]

  const CtaButtons = ({ location }: { location: string }) => (
    <div className="flex flex-col items-center justify-center gap-3 sm:flex-row" data-cta={location}>
      <Link href="/login" className="flex w-full min-w-[220px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 sm:w-auto">
        Start Free Trial <ArrowRight className="h-4 w-4" />
      </Link>
      <a href={whatsappDemo} target="_blank" rel="noopener noreferrer" className="flex w-full min-w-[160px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
        Book a Demo
      </a>
    </div>
  )

  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />

      <MarketingHeader />

      {/* Breadcrumb (matches BreadcrumbList schema) */}
      <nav aria-label="Breadcrumb" className="mx-auto max-w-5xl px-4 pt-6 sm:px-6 lg:px-8">
        <ol className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
          <li><Link href="/" className="hover:text-foreground">Home</Link></li>
          <li aria-hidden>/</li>
          <li><Link href="/features" className="hover:text-foreground">Features</Link></li>
          <li aria-hidden>/</li>
          <li className="text-foreground">{f.name}</li>
        </ol>
      </nav>

      {/* HERO */}
      <section className="mx-auto max-w-5xl space-y-7 px-4 pb-14 pt-10 text-center sm:px-6 lg:px-8">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
          <HeroIcon className="h-3.5 w-3.5" />
          <span>{f.badge}</span>
        </div>
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{f.h1}</h1>
        <p className="mx-auto max-w-2xl text-base text-muted-foreground sm:text-lg">{f.heroSub}</p>
        <CtaButtons location="hero" />
        <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2.5 text-[11px] font-semibold text-muted-foreground">
          {['Free audit — no card', '7-day trial — no charge today', 'Secure Google OAuth', 'Cancel anytime'].map((t) => (
            <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{t}</span>
          ))}
        </div>
      </section>

      {/* ANSWER BLOCK (AEO) */}
      <section className="border-y border-border/40 bg-muted/10 py-12">
        <div className="mx-auto max-w-3xl px-4 text-center sm:px-6 lg:px-8">
          <h2 className="mb-3 text-xl font-bold text-foreground">What is {f.name.toLowerCase()}?</h2>
          <p className="leading-relaxed text-muted-foreground">{f.definition}</p>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="py-16">
        <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
          <h2 className="text-center text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">How it works</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {f.howItWorks.map((s, i) => (
              <div key={s.title} className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><RefreshCw className="h-[18px] w-[18px] text-primary" /></div>
                  <span className="text-xl font-extrabold text-muted-foreground/20">{String(i + 1).padStart(2, '0')}</span>
                </div>
                <h3 className="text-sm font-bold text-foreground">{s.title}</h3>
                <p className="text-xs leading-relaxed text-muted-foreground">{s.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* BENEFITS */}
      <section className="border-y border-border/40 bg-muted/10 py-16">
        <div className="mx-auto max-w-5xl space-y-8 px-4 sm:px-6 lg:px-8">
          <h2 className="text-center text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Why it matters</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {f.benefits.map((b) => (
              <div key={b.title} className="flex items-start gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
                <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" />
                <div>
                  <h3 className="text-sm font-bold text-foreground">{b.title}</h3>
                  <p className="text-xs leading-relaxed text-muted-foreground">{b.detail}</p>
                </div>
              </div>
            ))}
          </div>
          <p className="text-center text-sm text-muted-foreground">
            {f.plan}{' '}
            <Link href="/pricing" className="font-semibold text-primary underline-offset-4 hover:underline">See pricing</Link>
          </p>
        </div>
      </section>

      {/* FAQ */}
      {f.faqs.length > 0 && (
        <section className="py-16">
          <div className="mx-auto max-w-4xl space-y-8 px-4 sm:px-6 lg:px-8">
            <h2 className="text-center text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Frequently asked questions</h2>
            <div className="space-y-3">
              {f.faqs.map((q) => (
                <details key={q.q} className="group overflow-hidden rounded-xl border border-border bg-card">
                  <summary className="flex cursor-pointer select-none items-center justify-between p-5 text-sm font-bold text-foreground [&::-webkit-details-marker]:hidden">
                    {q.q}
                    <span className="ml-4 text-muted-foreground transition-transform group-open:rotate-45">+</span>
                  </summary>
                  <div className="border-t border-border px-5 pb-5 pt-3.5 text-xs leading-relaxed text-muted-foreground">{q.a}</div>
                </details>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* FINAL CTA */}
      <section className="mx-auto max-w-5xl px-4 py-16 sm:px-6 lg:px-8">
        <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-primary/5 p-8 text-center sm:p-12">
          <div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl" />
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Try {f.name} with Pinzo</h2>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">Connect your Google Business Profile and get started in minutes. Free audit with no card, then a 7-day free trial — no charge today.</p>
          <div className="pt-6"><CtaButtons location="footer" /></div>
        </div>

        {/* Related features + key internal links for crawl depth */}
        {related.length > 0 && (
          <div className="mt-10">
            <p className="mb-3 text-center text-xs font-bold uppercase tracking-wide text-muted-foreground">Related features</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {related.map((r) => {
                const Icon = ICONS[r.icon] || Sparkles
                return (
                  <Link key={r.slug} href={`/features/${r.slug}`} className="flex items-center gap-3 rounded-xl border border-border bg-card p-4 shadow-sm transition-colors hover:border-primary/40">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Icon className="h-[18px] w-[18px] text-primary" /></div>
                    <span className="text-sm font-bold text-foreground">{r.name}</span>
                  </Link>
                )
              })}
            </div>
          </div>
        )}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs font-semibold text-muted-foreground">
          <Link href="/features" className="hover:text-foreground">All features</Link>
          <Link href="/google-business-profile-management" className="hover:text-foreground">GBP management</Link>
          <Link href="/pricing" className="hover:text-foreground">Pricing</Link>
        </div>
      </section>

      <MarketingFooter />
    </div>
  )
}
