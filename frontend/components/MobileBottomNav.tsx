'use client'

import { usePathname } from 'next/navigation'
import Link from 'next/link'
import { MapPin, TrendingUp, MessageSquare, Calendar, Menu, MessageCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'

/**
 * Persistent bottom tab bar for phones (hidden from `md` up, where the sidebar
 * takes over). Surfaces the highest-traffic destinations for thumb reach;
 * "More" opens the full nav drawer (Search Intelligence, Settings, Team,
 * Billing, Logs all live there). Sits at z-30 so the drawer backdrop (z-40)
 * and modals (z-50) cover it when open.
 */
export default function MobileBottomNav({ onOpenMore }: { onOpenMore: () => void }) {
  const pathname = usePathname() || ''

  // Shares React Query's cache with the sidebar badge (same key), so adding it
  // here costs no extra request. Owner/Admin only, matching the backend gate.
  const { user } = useAuth()
  const canUseInbox = !!user?.role && ['Owner', 'Admin'].includes(user.role)
  const { data: waiting } = useQuery<{ count: number }>({
    queryKey: ['whatsapp-needs-reply'],
    queryFn: () => api.get('/whatsapp/inbox/needs-reply'),
    enabled: canUseInbox,
    staleTime: 60_000,
    refetchInterval: (query) => (query.state.error ? false : 60_000),
    retry: false,
  })
  const waitingCount = waiting?.count ?? 0

  const items: { label: string; href: string; icon: any; active: boolean; badge?: number }[] = [
    { label: 'Home', href: '/dashboard', icon: MapPin, active: pathname === '/dashboard' || pathname.startsWith('/dashboard/locations') },
    { label: 'Insights', href: '/dashboard/insights', icon: TrendingUp, active: pathname.startsWith('/dashboard/insights') },
    { label: 'Reviews', href: '/dashboard/reviews', icon: MessageSquare, active: pathname.startsWith('/dashboard/reviews') },
    { label: 'Posts', href: '/dashboard/posts', icon: Calendar, active: pathname.startsWith('/dashboard/posts') },
    // Labelled "Chats" rather than "WhatsApp": six tabs on a 360px screen means
    // every label has to stay short or they wrap. Hidden entirely for roles the
    // backend refuses, which also keeps the bar at five tabs for them.
    ...(canUseInbox
      ? [{ label: 'Chats', href: '/dashboard/whatsapp/inbox', icon: MessageCircle,
           active: pathname.startsWith('/dashboard/whatsapp'), badge: waitingCount }]
      : []),
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
          <span className="relative">
            <it.icon className={`h-5 w-5 ${it.active ? 'text-primary' : 'text-muted-foreground/70'}`} />
            {!!it.badge && (
              <span className="absolute -right-2 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-emerald-500 px-1 text-[9px] font-bold tabular-nums text-white">
                {it.badge > 9 ? '9+' : it.badge}
              </span>
            )}
          </span>
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
