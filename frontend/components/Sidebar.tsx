'use client'

import { usePathname } from 'next/navigation'
import { useState } from 'react'
import { LogOut, User as UserIcon, RefreshCw, Layers, MapPin, TrendingUp, MessageSquare, Calendar, Users, Settings, CreditCard, Search, ChevronDown, FileClock, X } from 'lucide-react'
import Link from 'next/link'
import { useAuth } from '@/hooks/useAuth'

export default function Sidebar({
  mobileOpen = false,
  onClose,
}: {
  // Below `md` the sidebar is an off-canvas drawer toggled from the mobile top
  // bar; from `md` up it is always-visible and these props are inert.
  mobileOpen?: boolean
  onClose?: () => void
}) {
  const pathname = usePathname()
  const { user, logout } = useAuth()

  const userName = user?.name || 'Google User'
  const userRole = user?.role || ''
  const userAvatar = user?.avatar || null

  const handleLogout = async () => {
    await logout()
    // Full navigation to the homepage so all in-memory auth state is cleared.
    window.location.href = '/'
  }

  const menuItems = [
    { label: 'Dashboard', href: '/dashboard', icon: MapPin },
    { label: 'Insights', href: '/dashboard/insights', icon: TrendingUp },
    { label: 'Search Intelligence', href: '/dashboard/insights/search-intelligence', icon: Search },
    { label: 'Reviews', href: '/dashboard/reviews', icon: MessageSquare },
    { label: 'Posts & Media', href: '/dashboard/posts', icon: Calendar },
  ]

  // Settings is a collapsible group: Profile / Team / Billing / Activity Logs.
  const settingsChildren = [
    { label: 'Profile', href: '/dashboard/settings', icon: UserIcon },
    ...(userRole && ['Owner', 'Admin', 'Regional Manager'].includes(userRole)
      ? [{ label: 'Team', href: '/dashboard/team', icon: Users }]
      : []),
    ...(userRole && ['Owner', 'Admin'].includes(userRole)
      ? [{ label: 'Billing', href: '/dashboard/settings/billing', icon: CreditCard }]
      : []),
    ...(userRole && ['Owner', 'Admin'].includes(userRole)
      ? [{ label: 'Reply Templates', href: '/dashboard/settings/reply-templates', icon: MessageSquare }]
      : []),
    { label: 'Activity Logs', href: '/dashboard/settings/logs', icon: FileClock },
  ]

  const inSettings = pathname === '/dashboard/team' || pathname?.startsWith('/dashboard/settings')
  const [settingsOpen, setSettingsOpen] = useState<boolean>(!!inSettings)

  const isActive = (href: string) => {
    if (href === '/dashboard') {
      return pathname === '/dashboard' || pathname?.startsWith('/dashboard/locations')
    }
    return pathname === href
  }

  return (
    <>
      {/* Mobile backdrop — only rendered while the drawer is open below md */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`fixed md:sticky inset-y-0 left-0 top-0 z-50 md:z-30 h-screen w-64 max-w-[82vw] md:w-60 md:max-w-none shrink-0 border-r border-border bg-card flex flex-col transform transition-transform duration-200 ease-in-out md:translate-x-0 ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
      {/* Brand Header */}
      <div className="h-16 px-6 border-b border-border flex items-center justify-between gap-2.5">
        <div className="flex items-center gap-2.5 min-w-0">
          <img
            src="/logo-horizontal-3.png"
            alt="Pinzo"
            className="h-8 object-contain shrink-0"
          />
        </div>
        {/* Close affordance — drawer only (hidden once the sidebar is static) */}
        <button
          onClick={onClose}
          className="md:hidden flex h-8 w-8 items-center justify-center rounded-md border border-border bg-muted/20 text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors shrink-0"
          aria-label="Close navigation menu"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
        {menuItems.map((item) => {
          const active = isActive(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors ${
                active
                  ? 'bg-primary/10 text-primary border border-primary/20'
                  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground border border-transparent'
              }`}
            >
              <item.icon className={`h-4 w-4 shrink-0 ${active ? 'text-primary' : 'text-muted-foreground/60'}`} />
              <span>{item.label}</span>
            </Link>
          )
        })}

        {/* Settings group */}
        <div className="pt-2 mt-2 border-t border-border/60">
          <button
            onClick={() => setSettingsOpen(o => !o)}
            className={`w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors ${inSettings ? 'text-foreground' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'}`}
          >
            <span className="flex items-center gap-3">
              <Settings className={`h-4 w-4 shrink-0 ${inSettings ? 'text-primary' : 'text-muted-foreground/60'}`} />
              Settings
            </span>
            <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform ${settingsOpen ? 'rotate-180' : ''}`} />
          </button>
          {settingsOpen && (
            <div className="mt-1 ml-3 pl-3 border-l border-border/60 space-y-1">
              {settingsChildren.map((item) => {
                const active = isActive(item.href)
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={onClose}
                    className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-[11px] font-bold uppercase tracking-wider transition-colors ${
                      active
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                    }`}
                  >
                    <item.icon className={`h-3.5 w-3.5 shrink-0 ${active ? 'text-primary' : 'text-muted-foreground/60'}`} />
                    <span>{item.label}</span>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </nav>

      {/* Workspace Indicator & User Details */}
      <div className="p-4 border-t border-border space-y-4">
        {/* Workspace info */}
        <div className="flex items-center gap-2 rounded-lg bg-muted/40 px-3 py-2 text-xs font-semibold">
          <Layers className="h-4 w-4 text-indigo-500" />
          <span className="text-muted-foreground truncate">Workspace active</span>
        </div>

        {/* User Card */}
        <div className="flex items-center justify-between gap-3 bg-muted/20 p-2.5 rounded-xl border border-border/50">
          <div className="flex items-center gap-2.5 min-w-0">
            {userAvatar ? (
              <img
                src={userAvatar}
                alt={userName}
                className="h-8 w-8 rounded-full border border-border bg-muted/40 shrink-0"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-muted/40 text-muted-foreground shrink-0">
                <UserIcon className="h-4 w-4" />
              </div>
            )}
            <div className="flex flex-col min-w-0">
              <span className="text-xs font-bold text-foreground truncate leading-tight">{userName}</span>
              <span className="text-[9px] uppercase font-extrabold tracking-wider text-indigo-500 mt-0.5 truncate">{userRole}</span>
            </div>
          </div>

          <button
            onClick={handleLogout}
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-muted/20 text-muted-foreground hover:bg-red-500/10 hover:text-red-500 transition-colors shrink-0"
            title="Log Out"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
      </aside>
    </>
  )
}
