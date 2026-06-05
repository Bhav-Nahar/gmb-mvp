'use client'

import { useEffect, useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { RefreshCw, CheckCircle2 } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'

function LoginSuccessContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { refresh } = useAuth()
  const [statusMessage, setStatusMessage] = useState('Securing connection...')

  useEffect(() => {
    const token = searchParams.get('token')
    const csrf = searchParams.get('csrf')
    const onboarding = searchParams.get('onboarding')

    if (!token) {
      router.replace('/login?error=token_missing')
      return
    }

    if (csrf) {
      document.cookie = `gmb_csrf_token=${csrf}; path=/; max-age=${3600 * 24 * 7}; samesite=lax`
    }
    
    // Fetch profile and store
    const fetchAndRedirect = async () => {
      try {
        setStatusMessage('Establishing workspace...')
        await refresh()
        
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

export default LoginSuccessContent
