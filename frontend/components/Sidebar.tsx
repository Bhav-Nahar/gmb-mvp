'use client'

import { useRouter, usePathname } from 'next/navigation'
import { LogOut, User as UserIcon, RefreshCw, Layers, MapPin, TrendingUp, MessageSquare, Calendar, Users, Settings, CreditCard } from 'lucide-react'
import Link from 'next/link'
import { useAuth } from '@/hooks/useAuth'

export default function Sidebar() {
  const router = useRouter()
  const pathname = usePathname()
  const { user, logout } = useAuth()
  
  const userName = user?.name || 'Google User'
  const userRole = user?.role || ''
  const userAvatar = user?.avatar || null

  const handleLogout = async () => {
    await logout()
    router.push('/login')
  }

  const menuItems = [
    { label: 'Dashboard', href: '/dashboard', icon: MapPin },
    { label: 'Insights', href: '/dashboard/insights', icon: TrendingUp },
    { label: 'Reviews', href: '/dashboard/reviews', icon: MessageSquare },
    { label: 'Posts & Media', href: '/dashboard/posts', icon: Calendar },
    ...(userRole && ['Owner', 'Admin', 'Regional Manager'].includes(userRole) 
      ? [{ label: 'Team', href: '/dashboard/team', icon: Users }] 
      : []),
    { label: 'Settings', href: '/dashboard/settings', icon: Settings },
    ...(userRole && ['Owner', 'Admin'].includes(userRole) 
      ? [{ label: 'Billing', href: '/dashboard/settings/billing', icon: CreditCard }] 
      : []),
  ]

  const isActive = (href: string) => {
    if (href === '/dashboard') {
      return pathname === '/dashboard' || pathname?.startsWith('/dashboard/locations')
    }
    return pathname === href
  }

  return (
    <aside className="w-60 border-r border-border bg-card flex flex-col h-screen sticky top-0 shrink-0">
      {/* Brand Header */}
      <div className="h-16 px-6 border-b border-border flex items-center gap-2.5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 shadow-md">
          <RefreshCw className="h-5 w-5 text-white animate-pulse" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-bold text-foreground tracking-tight leading-none">
            GMB Sync Engine
          </span>
          <span className="text-[10px] text-muted-foreground font-semibold mt-0.5">
            Operational Hub
          </span>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-4 py-6 space-y-1 overflow-y-auto">
        {menuItems.map((item) => {
          const active = isActive(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
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
  )
}
