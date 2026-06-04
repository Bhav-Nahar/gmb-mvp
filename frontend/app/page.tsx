'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'

export default function RootPage() {
  const router = useRouter()
  const { user, loading } = useAuth()

  useEffect(() => {
    if (!loading) {
      if (user) {
        router.replace('/dashboard')
      } else {
        router.replace('/login')
      }
    }
  }, [user, loading, router])

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background">
      <div className="flex h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
    </div>
  )
}
