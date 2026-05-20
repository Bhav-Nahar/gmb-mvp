'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function RootPage() {
  const router = useRouter()

  useEffect(() => {
    const token = localStorage.getItem('gmb_auth_token')
    if (token) {
      router.replace('/dashboard')
    } else {
      router.replace('/login')
    }
  }, [router])

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background">
      <div className="flex h-10 w-10 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
    </div>
  )
}
