'use client'

import { useEffect, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { RefreshCw, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'

export default function LoginSuccessPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [statusMessage, setStatusMessage] = useState('Securing connection...')

  useEffect(() => {
    const token = searchParams.get('token')
    const onboarding = searchParams.get('onboarding')

    if (!token) {
      router.replace('/login?error=token_missing')
      return
    }

    // Save token
    localStorage.setItem('gmb_auth_token', token)
    
    // Fetch profile and store
    const fetchAndRedirect = async () => {
      try {
        setStatusMessage('Establishing workspace...')
        const userProfile = await api.get('/users/me', undefined, {
          headers: { Authorization: `Bearer ${token}` }
        })
        localStorage.setItem('gmb_user', JSON.stringify(userProfile))
        
        setStatusMessage('Onboarding workspace...')
        // Short delay for sleek feel
        setTimeout(() => {
          if (onboarding === 'true') {
            router.replace('/dashboard?onboarding=true')
          } else {
            router.replace('/dashboard')
          }
        }, 1000)
      } catch (e) {
        localStorage.removeItem('gmb_auth_token')
        router.replace('/login?error=profile_fetch_failed')
      }
    }

    fetchAndRedirect()
  }, [router, searchParams])

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-4 text-center p-6 max-w-sm glass-panel border border-border rounded-2xl shadow-2xl">
        <div className="relative flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-xl shadow-indigo-500/20">
          <RefreshCw className="h-6 w-6 text-white animate-spin" />
        </div>
        <div className="space-y-1">
          <h3 className="text-base font-bold text-white">Google OAuth Verified</h3>
          <p className="text-xs text-muted-foreground font-medium animate-pulse">{statusMessage}</p>
        </div>
      </div>
    </div>
  )
}
