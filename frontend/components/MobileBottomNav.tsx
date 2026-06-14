'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { MapPin, TrendingUp, MessageSquare, Calendar, Menu } from 'lucide-react'

/**
 * Persistent bottom tab bar for phones (hidden from `md` up, where the sidebar
 * takes over). Surfaces the four highest-traffic destinations for thumb reach;
 * "More" opens the full nav drawer (Search Intelligence, Settings, Team,
 * Billing, Logs all live there). Sits at z-30 so the drawer backdrop (z-40)
 * and modals (z-50) cover it when open.
 */
export default function MobileBottomNav({ onOpenMore }: { onOpenMore: () => void }) {
  const pathname = usePathname() || ''

  const items = [
    { label: 'Home', href: '/dashboard', icon: MapPin, active: pathname === '/dashboard' || pathname.startsWith('/dashboard/locations') },
    { label: 'Insights', href: '/dashboard/insights', icon: TrendingUp, active: pathname.startsWith('/dashboard/insights') },
    { label: 'Reviews', href: '/dashboard/reviews', icon: MessageSquare, active: pathname.startsWith('/dashboard/reviews') },
    { label: 'Posts', href: '/dashboard/posts', icon: Calendar, active: pathname.startsWith('/dashboard/posts') },
  ]

  return (
    <nav
      className="md:hidden fixed bottom-0 inset-x-0 z-30 flex h-16 items-stretch justify-around border-t border-border bg-background/95 backdrop-blur"
      aria-label="Primary"
    >
      {items.map((it) => (
        <Link
          key={it.href}
          href={it.href}
          aria-current={it.active ? 'page' : undefined}
          className={`flex flex-1 flex-col items-center justify-center gap-1 text-[10px] font-bold uppercase tracking-wide transition-colors ${
            it.active ? 'text-primary' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          <it.icon className={`h-5 w-5 ${it.active ? 'text-primary' : 'text-muted-foreground/70'}`} />
          <span>{it.label}</span>
        </Link>
      ))}
      <button
        type="button"
        onClick={onOpenMore}
        className="flex flex-1 flex-col items-center justify-center gap-1 text-[10px] font-bold uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
        aria-label="Open full navigation menu"
      >
        <Menu className="h-5 w-5 text-muted-foreground/70" />
        <span>More</span>
      </button>
    </nav>
  )
}
