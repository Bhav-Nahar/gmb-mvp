'use client'

import Link from 'next/link'
import { usePathname, useSearchParams } from 'next/navigation'

/**
 * Sub-navigation for the Local SEO page family.
 *
 * The tiers live in two tables (country and global pillars in cseo_pages,
 * everything under /{locale}/local-seo-services/{slug} in lpseo_pages) but that is
 * a storage detail. To an editor it is one hierarchy, so it gets one top-level tab
 * and five sub-tabs rather than five entries in the header.
 */
const TABS = [
  // Ordered the way the hierarchy nests: global > country > industry/city > leaves.
  // Global and Country are the same table and the same page, split by a query param,
  // because "Global" filed under a tab called "Country" is unfindable.
  { href: '/admin/cseo?scope=global', label: 'Global', match: (p: string, _t: string | null, s: string | null) => p.startsWith('/admin/cseo') && s === 'global' },
  { href: '/admin/cseo', label: 'Country', match: (p: string, _t: string | null, s: string | null) => p.startsWith('/admin/cseo') && s !== 'global' },
  { href: '/admin/lpseo?type=industry_pillar', label: 'Industry', match: (p: string, t: string | null, _s: string | null) => p.startsWith('/admin/lpseo') && t === 'industry_pillar' },
  { href: '/admin/lpseo?type=city_pillar', label: 'City', match: (p: string, t: string | null, _s: string | null) => p.startsWith('/admin/lpseo') && t === 'city_pillar' },
  { href: '/admin/lpseo', label: 'Pages', match: (p: string, t: string | null, _s: string | null) => p.startsWith('/admin/lpseo') && t !== 'industry_pillar' && t !== 'city_pillar' },
]

export default function SeoSubNav() {
  const pathname = usePathname() || ''
  const params = useSearchParams()
  const type = params?.get('type') ?? null
  const scope = params?.get('scope') ?? null
  return (
    <nav aria-label="Local SEO sections" className="flex flex-wrap items-center gap-1 border-b border-border pb-3">
      {TABS.map((t) => {
        const active = t.match(pathname, type, scope)
        return (
          <Link
            key={t.label}
            href={t.href}
            aria-current={active ? 'page' : undefined}
            className={`rounded-lg px-3 py-1.5 text-xs font-bold uppercase tracking-wider transition-colors ${
              active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
            }`}
          >
            {t.label}
          </Link>
        )
      })}
    </nav>
  )
}
