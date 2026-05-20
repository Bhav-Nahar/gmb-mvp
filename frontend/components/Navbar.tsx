'use client'

import { useRouter } from 'next/navigation'
import { LogOut, User as UserIcon, RefreshCw, Layers } from 'lucide-react'
import { useEffect, useState } from 'react'
import Link from 'next/link'

export default function Navbar() {
  const router = useRouter()
  const [userName, setUserName] = useState<string>('')
  const [userRole, setUserRole] = useState<string>('')
  const [userAvatar, setUserAvatar] = useState<string | null>(null)

  useEffect(() => {
    const userStr = localStorage.getItem('gmb_user')
    if (userStr) {
      try {
        const u = JSON.parse(userStr)
        setUserName(u.name || 'Google User')
        setUserRole(u.role || '')
        setUserAvatar(u.avatar || null)
      } catch (e) {
        console.error(e)
      }
    }
  }, [])

  const handleLogout = () => {
    localStorage.removeItem('gmb_auth_token')
    localStorage.removeItem('gmb_user')
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
            <span className="bg-gradient-to-r from-white to-gray-400 bg-clip-text text-lg font-bold tracking-tight text-transparent">
              GMB Sync Engine
            </span>
          </div>

          <nav className="flex items-center gap-6">
            <Link
              href="/dashboard"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-white transition-colors"
            >
              Dashboard
            </Link>
            <Link
              href="/dashboard/team"
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-white transition-colors"
            >
              Team
            </Link>
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
              <span className="text-xs font-bold text-white leading-tight">{userName}</span>
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
