'use client'

import { useEffect } from 'react'
import { useRouter, usePathname } from 'next/navigation'
import Link from 'next/link'
import { ShieldCheck, ArrowLeft, LogOut } from 'lucide-react'
import { useAuth } from '@/hooks/useAuth'

const navCls = (active: boolean) =>
  `px-3 py-1.5 rounded-lg text-xs font-bold uppercase tracking-wider transition-colors ${
    active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
  }`

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const onAudit = !!pathname?.startsWith('/admin/audit')
  const onHolidays = !!pathname?.startsWith('/admin/holidays')
  const onPseo = !!pathname?.startsWith('/admin/pseo')

  useEffect(() => {
    if (loading) return
    if (!user) {
      router.replace('/login?expired=true')
      return
    }
    if (!user.is_superuser) {
      router.replace('/dashboard')
    }
  }, [loading, user, router])

  // Backend enforces the gate too (superadmin_required); this is just UX.
  if (loading || !user || !user.is_superuser) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="h-16 sticky top-0 z-30 border-b border-border bg-card px-6 flex items-center justify-between">
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2.5">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <span className="text-sm font-bold uppercase tracking-wider">Super Admin</span>
          </div>
          <nav className="hidden sm:flex items-center gap-1">
            <Link href="/admin" className={navCls(!onAudit && !onHolidays && !onPseo)}>Accounts</Link>
            <Link href="/admin/audit" className={navCls(onAudit)}>Audit log</Link>
            <Link href="/admin/holidays" className={navCls(onHolidays)}>Holidays</Link>
            <Link href="/admin/pseo" className={navCls(onPseo)}>pSEO pages</Link>
          </nav>
        </div>
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to app
          </Link>
          <button
            onClick={() => logout().then(() => { window.location.href = '/' })}
            className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-red-500"
          >
            <LogOut className="h-3.5 w-3.5" /> Log out
          </button>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  )
}
