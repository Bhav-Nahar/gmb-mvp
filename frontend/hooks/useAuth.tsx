'use client'

import React, { createContext, useContext, useState, useEffect } from 'react'
import { api } from '@/lib/api'

export interface User {
  id: number
  name: string
  email: string
  role: string
  avatar?: string
}

interface AuthContextType {
  user: User | null
  isAdmin: boolean
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
    } catch (e) {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const isPublicPage = window.location.pathname === '/login' || 
                         window.location.pathname.startsWith('/invite/') ||
                         window.location.pathname === '/login/success' ||
                         window.location.pathname === '/' ||
                         window.location.pathname === '/privacy' ||
                         window.location.pathname === '/terms' ||
                         window.location.pathname === '/refund' ||
                         window.location.pathname === '/contact'
                         
    if (isPublicPage) {
      setLoading(false)
      return
    }
    fetchProfile()
  }, [])

  const logout = async () => {
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

  return (
    <AuthContext.Provider value={{ user, isAdmin, loading, logout, refresh: fetchProfile }}>
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
