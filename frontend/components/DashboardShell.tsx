'use client'

import { useState } from 'react'
import { Menu, RefreshCw } from 'lucide-react'
import Sidebar from './Sidebar'
import MobileBottomNav from './MobileBottomNav'

/**
 * Dashboard chrome. On `md` and up the sidebar is always-visible and sits in
 * the flow beside the content. Below `md` it collapses into an off-canvas
 * drawer, fronted by a compact top bar and a persistent bottom tab bar for
 * thumb-reach navigation, so the 240px rail never eats the phone viewport.
 */
export default function DashboardShell({ children }: { children: React.ReactNode }) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)

  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar mobileOpen={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      {/* Content column. `pb-16` on mobile keeps page content clear of the
          fixed bottom tab bar (h-16); removed from md up. */}
      <div className="flex-1 flex flex-col min-h-screen min-w-0 overflow-x-hidden pb-16 md:pb-0">
        {/* Mobile top bar — only below md, where the sidebar is a drawer */}
        <header className="md:hidden sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-border bg-background/90 backdrop-blur px-4">
          <button
            onClick={() => setMobileNavOpen(true)}
            className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
            aria-label="Open navigation menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2 min-w-0">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 shadow-md shrink-0">
              <RefreshCw className="h-4 w-4 text-white" />
            </div>
            <span className="text-sm font-bold tracking-tight truncate">Pinzo</span>
          </div>
        </header>

        {children}
      </div>

      <MobileBottomNav onOpenMore={() => setMobileNavOpen(true)} />
    </div>
  )
}
