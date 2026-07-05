import Link from 'next/link'
import { ArrowRight, MapPin } from 'lucide-react'
import { MarketingHeader } from '@/components/MarketingHeader'
import { MarketingFooter } from '@/components/MarketingFooter'

export interface HubCard { href: string; title: string; subtitle?: string }
export interface Crumb { label: string; href?: string }

/** Shared layout for pSEO hub pages (industry hub, root hub-of-hubs).
 * A hub is just a heading + a grid of link cards to child pages — its whole
 * job is internal linking and crawl depth, so keep it lean. */
export default function PseoHub({
  crumbs, title, subtitle, cards, emptyText,
}: {
  crumbs: Crumb[]
  title: string
  subtitle?: string
  cards: HubCard[]
  emptyText?: string
}) {
  return (
    <div className="relative min-h-screen overflow-x-clip bg-background font-sans text-foreground">
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[600px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />
      <MarketingHeader />

      <nav aria-label="Breadcrumb" className="mx-auto max-w-6xl px-4 pt-6 sm:px-6 lg:px-8">
        <ol className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
          {crumbs.map((c, i) => (
            <li key={i} className="flex items-center gap-1.5">
              {i > 0 && <span aria-hidden>/</span>}
              {c.href ? <Link href={c.href} className="hover:text-foreground">{c.label}</Link> : <span className="text-foreground">{c.label}</span>}
            </li>
          ))}
        </ol>
      </nav>

      <section className="mx-auto max-w-3xl space-y-4 px-4 py-12 text-center sm:px-6 lg:px-8">
        <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl">{title}</h1>
        {subtitle && <p className="mx-auto max-w-2xl text-base text-muted-foreground">{subtitle}</p>}
      </section>

      <section className="mx-auto max-w-6xl px-4 pb-20 sm:px-6 lg:px-8">
        {cards.length === 0 ? (
          <p className="text-center text-sm text-muted-foreground">{emptyText || 'No pages yet.'}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {cards.map((c) => (
              <Link key={c.href} href={c.href} className="group flex items-center justify-between gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
                <span className="flex items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><MapPin className="h-[18px] w-[18px] text-primary" /></span>
                  <span>
                    <span className="block text-sm font-bold text-foreground">{c.title}</span>
                    {c.subtitle && <span className="block text-xs text-muted-foreground">{c.subtitle}</span>}
                  </span>
                </span>
                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
              </Link>
            ))}
          </div>
        )}
      </section>

      <MarketingFooter />
    </div>
  )
}
