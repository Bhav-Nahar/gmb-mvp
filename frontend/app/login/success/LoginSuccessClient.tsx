'use client'

import { useEffect, useState, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { RefreshCw, CheckCircle2 } from 'lucide-react'
import { api, storeCsrfToken } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { trackSignUpStart } from '@/lib/analytics'
import { getAttribution } from '@/lib/attribution'

function LoginSuccessContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { refresh } = useAuth()
  const [statusMessage, setStatusMessage] = useState('Securing connection...')

  useEffect(() => {
    const onboarding = searchParams.get('onboarding')

    // Fetch profile and store
    const fetchAndRedirect = async () => {
      try {
        setStatusMessage('Establishing workspace...')
        // Call /auth/refresh to rotate tokens and get the CSRF token in the response body.
        // We store it in localStorage because document.cookie cannot read cross-domain cookies
        // (frontend on vercel.app, backend on railway.app).
        const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
        const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
        })
        if (refreshRes.ok) {
          const data = await refreshRes.json()
          if (data?.csrf_token) storeCsrfToken(data.csrf_token)
        }
        await refresh()

        // Hand the browser's first-touch attribution to the backend so it's stamped on
        // the org (first-touch wins server-side) and available for Meta/Google conversions.
        // Best-effort: never block the dashboard redirect on this.
        try {
          const attribution = getAttribution()
          if (Object.keys(attribution).length > 0) {
            await api.post('/users/me/attribution', attribution)
          }
        } catch (e) {
          console.warn('attribution post failed', e)
        }

        const isOnboarding = onboarding === 'true'
        // New user just completed OAuth -> the real signup. Fires once (consumes
        // the stored cta_location); returning users don't trigger it.
        if (isOnboarding) trackSignUpStart()
        setStatusMessage(isOnboarding ? 'Onboarding workspace...' : 'Loading your dashboard...')
        // Brief delay only for new-user onboarding; existing users redirect immediately
        setTimeout(() => {
          router.replace(isOnboarding ? '/dashboard?onboarding=true' : '/dashboard')
        }, isOnboarding ? 1000 : 0)
      } catch (e: any) {
        console.error('LoginSuccessClient error during fetchAndRedirect:', e)
        const errorMsg = e instanceof Error ? e.message : String(e)
        router.replace(`/login?error=profile_fetch_failed&details=${encodeURIComponent(errorMsg)}`)
      }
    }

    fetchAndRedirect()
  }, [router, searchParams])

  return (
    <div className="flex min-h-screen w-full items-center justify-center bg-background px-4 py-12 sm:px-6 lg:px-8">
      <div className="flex flex-col items-center gap-4 text-center p-6 w-full max-w-sm glass-panel border border-border rounded-2xl shadow-2xl">
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
