'use client'

import { useRouter } from 'next/navigation'
import { LogOut, User as UserIcon, RefreshCw, Layers } from 'lucide-react'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'

export default function Navbar() {
  const router = useRouter()
  const { user, logout } = useAuth()
  
  const userName = user?.name || 'Google User'
  const userRole = user?.role || ''
  const userAvatar = user?.avatar || null

  const handleLogout = async () => {
    await logout()
    router.push('/login')
  }

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border glass-panel">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Left Side: Brand Logo & Navigation */}
        <div className="flex items-center gap-8">
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 shadow-lg shadow-indigo-500/20">
              <RefreshCw className="h-5 w-5 text-white animate-pulse" />
            </div>
            <span className="bg-gradient-to-r from-indigo-600 to-purple-700 bg-clip-text text-lg font-bold tracking-tight text-transparent">
              GMB Sync Engine
            </span>
          </div>

          <nav className="flex items-center gap-6">
            <Link
              href="/dashboard"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              Dashboard
            </Link>
            <Link
              href="/dashboard/insights"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              Insights
            </Link>
            {['Owner', 'Admin', 'Regional Manager'].includes(userRole) && (
              <Link
                href="/dashboard/team"
                className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
              >
                Team
              </Link>
            )}
            <Link
              href="/dashboard/reviews"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              Reviews
            </Link>
            <Link
              href="/dashboard/posts"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              Posts & Media
            </Link>
            <Link
              href="/dashboard/settings"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
            >
              Settings
            </Link>
            {['Owner', 'Admin'].includes(userRole) && (
              <Link
                href="/dashboard/settings/billing"
                className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
              >
                Billing
              </Link>
            )}
          </nav>
        </div>

        {/* Right Side: Account Details & Actions */}
        <div className="flex items-center gap-4">
          {/* Organisation Scope Info */}
          <div className="hidden sm:flex items-center gap-1.5 rounded-full border border-border bg-muted/30 px-3 py-1 text-xs font-semibold">
            <Layers className="h-3.5 w-3.5 text-indigo-400" />
            <span className="text-muted-foreground">Workspace active</span>
          </div>

          {/* User Details */}
          <div className="flex items-center gap-3 border-l border-border pl-4">
            <div className="flex flex-col items-end">
              <span className="text-xs font-bold text-foreground leading-tight">{userName}</span>
              <span className="text-[10px] uppercase font-extrabold tracking-wider text-indigo-400 mt-0.5">{userRole}</span>
            </div>
            
            {userAvatar ? (
              <img
                src={userAvatar}
                alt={userName}
                className="h-8 w-8 rounded-full border border-border bg-muted/40 shadow-inner"
                referrerPolicy="no-referrer"
              />
            ) : (
              <div className="flex h-8 w-8 items-center justify-center rounded-full border border-border bg-muted/40">
                <UserIcon className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
          </div>

          {/* Logout Trigger */}
          <button
            onClick={handleLogout}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-red-500/10 hover:text-red-400 transition-colors"
            title="Log Out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </header>
  )
}
