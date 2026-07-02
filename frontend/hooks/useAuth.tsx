'use client'

import React, { createContext, useContext, useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { trackCustomerData } from '@/lib/analytics'

export interface User {
  id: number
  name: string
  email: string
  role: string
  avatar?: string
  phone?: string | null
  is_superuser?: boolean
  organization_id: number
}

interface AuthContextType {
  user: User | null
  isAdmin: boolean
  isSuperAdmin: boolean
  loading: boolean
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchProfile = async () => {
    try {
      const userProfile = await api.get<User>('/users/me')
      setUser(userProfile)
      trackCustomerData({
        name: userProfile.name,
        mobile: userProfile.phone ?? "",
        email: userProfile.email,
      })
    } catch (e) {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    // Only fetch the session inside the authenticated app (dashboard/admin).
    // Public pages — marketing AND microsites at /{slug} — must not call
    // /users/me, which would 401 for visitors and bounce them to /login.
    const path = window.location.pathname
    const isAppArea = path.startsWith('/dashboard') || path.startsWith('/admin')
    if (!isAppArea) {
      setLoading(false)
      return
    }
    fetchProfile()
  }, [])

  const logout = async () => {
    // Note: we intentionally KEEP the push subscription across logout so the
    // device keeps receiving lead alerts (it "remembers"). Notification payloads
    // carry no customer PII, so this is safe even on shared devices.
    try {
      await api.post('/auth/logout')
    } catch (e) {
      console.error('Logout error', e)
    }
    if (typeof document !== 'undefined') {
      document.cookie = "gmb_csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT"
    }
    setUser(null)
  }

  const isAdmin = user?.role === 'Admin' || user?.role === 'admin' || user?.role === 'Owner' || user?.role === 'owner'
  const isSuperAdmin = !!user?.is_superuser

  return (
    <AuthContext.Provider value={{ user, isAdmin, isSuperAdmin, loading, logout, refresh: fetchProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
