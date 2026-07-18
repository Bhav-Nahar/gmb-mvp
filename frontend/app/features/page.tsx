import type { Metadata } from 'next'
import Link from 'next/link'
import {
  Check, Sparkles, MessageSquare, Map, Calendar, Building, LayoutDashboard, Globe, BarChart2,
} from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'
import { FEATURES } from '@/lib/features'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'

const ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  MessageSquare, Sparkles, Map, Calendar, Building, LayoutDashboard, Globe, BarChart2,
}

export const metadata: Metadata = {
  title: 'Features — Google Business Profile & AI Visibility Tools | Pinzo',
  description: 'Everything Pinzo does for your Google Business Profiles: AI review replies, AI Search Visibility, local rank tracking, Google Posts, audits, multi-location management and more.',
  alternates: { canonical: `${SITE_URL}/features` },
  robots: { index: true, follow: true },
}

export default function FeaturesIndexPage() {
  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />
      <MarketingHeader />

      <section className="mx-auto max-w-5xl space-y-4 px-4 pb-10 pt-14 text-center sm:px-6 lg:px-8">
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">Everything Pinzo does</h1>
        <p className="mx-auto max-w-2xl text-base text-muted-foreground sm:text-lg">One dashboard to manage every Google Business Profile, answer reviews with AI, and get found on Google, Maps and AI search.</p>
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => {
            const Icon = ICONS[f.icon] || Sparkles
            return (
              <Link key={f.slug} href={`/features/${f.slug}`} className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm transition-colors hover:border-primary/40">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Icon className="h-5 w-5 text-primary" /></div>
                <h2 className="text-base font-bold text-foreground">{f.name}</h2>
                <p className="text-sm leading-relaxed text-muted-foreground">{f.heroSub}</p>
                <span className="mt-auto pt-2 text-xs font-bold uppercase tracking-wide text-primary">Learn more →</span>
              </Link>
            )
          })}
        </div>
        <div className="mt-10 text-center">
          <Link href="/login" className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90">
            Start Free Trial
          </Link>
          <p className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-[11px] font-semibold text-muted-foreground">
            {['Free 7-day trial', 'No credit card required', 'Secure Google OAuth'].map((t) => (
              <span key={t} className="inline-flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />{t}</span>
            ))}
          </p>
        </div>
      </section>

      <MarketingFooter />
    </div>
  )
}
