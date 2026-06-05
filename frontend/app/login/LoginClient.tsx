'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { RefreshCw, AlertTriangle, ArrowRight } from 'lucide-react'
import { api } from '@/lib/api'

function LoginContent() {
  const searchParams = useSearchParams()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [expiredAlert, setExpiredAlert] = useState(false)

  useEffect(() => {
    // Alert if session expired
    if (searchParams.get('expired') === 'true') {
      setExpiredAlert(true)
    }
    
    // Check if error callback from Google auth redirect
    const errorParam = searchParams.get('error')
    if (errorParam) {
      let friendlyMessage = 'An unexpected authentication error occurred. Please try again.'
      if (errorParam === 'oauth_failed') {
        friendlyMessage = 'Google Authentication failed. Please verify your Google account permissions.'
      } else if (errorParam === 'oauth_validation_failed') {
        friendlyMessage = 'Security state validation failed. Please try logging in again.'
      } else if (errorParam === 'session_expired') {
        friendlyMessage = 'Your session has expired. Please sign in again.'
      }
      setError(friendlyMessage)
    }
  }, [searchParams])

  const handleContinueWithGoogle = async () => {
    setError('')
    setLoading(true)
    try {
      // Trigger Google authorize URL fetch
      const response: any = await api.get('/auth/google/login')
      if (response && response.url) {
        // Redirect browser to Google Consent Page
        window.location.href = response.url
      } else {
        throw new Error('Failed to retrieve authorization URL')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to initiate Google Authentication flow.')
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-md space-y-8 glass-panel p-8 rounded-2xl border border-border shadow-2xl relative overflow-hidden">
        {/* Background visual blur spheres */}
        <div className="absolute -top-24 -left-24 w-48 h-48 rounded-full bg-indigo-600/10 blur-3xl pointer-events-none"></div>
        <div className="absolute -bottom-24 -right-24 w-48 h-48 rounded-full bg-purple-600/10 blur-3xl pointer-events-none"></div>

        {/* Brand Header */}
        <div className="flex flex-col items-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-xl shadow-indigo-500/20">
            <RefreshCw className="h-6 w-6 text-white animate-pulse" />
          </div>
          <h2 className="mt-6 text-center text-3xl font-bold tracking-tight text-white font-sans">
            GBP Manager Pro
          </h2>
          <p className="mt-2 text-center text-xs text-muted-foreground max-w-xs leading-relaxed">
            Centralize reviews, posts, analytics, and multi-location operations in one premium platform.
          </p>
        </div>

        {/* Connection panel */}
        <div className="mt-8 space-y-5">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs font-semibold text-red-400">
              {error}
            </div>
          )}

          {expiredAlert && (
            <div className="rounded-lg bg-amber-500/10 border border-amber-500/20 p-3 text-xs font-semibold text-amber-400 flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              <span>Session expired. Please sign in again.</span>
            </div>
          )}

          <button
            onClick={handleContinueWithGoogle}
            disabled={loading}
            className="w-full flex justify-center items-center gap-3 rounded-lg py-3 px-4 text-sm font-semibold bg-white hover:bg-gray-50 border border-gray-200 text-gray-950 shadow-sm cursor-pointer disabled:opacity-50 transition-colors"
          >
            {loading ? (
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent"></div>
            ) : (
              <>
                {/* SVG Google Icon */}
                <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24">
                  <path
                    fill="#EA4335"
                    d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114A5.99 5.99 0 0 1 8 12.5a5.99 5.99 0 0 1 5.99-6.015c1.474 0 2.812.538 3.854 1.424l3.22-3.22A10.93 10.93 0 0 0 13.99 2 10.99 10.99 0 0 0 3 13c0 6.075 4.925 11 10.99 11 5.753 0 10.457-4.143 10.94-9.673H12.24Z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M13.99 2a10.93 10.93 0 0 0-7.045 2.58l3.22 3.22A5.99 5.99 0 0 1 13.99 5.985V2Z"
                  />
                  <path
                    fill="#34A853"
                    d="M3 13c0 2.215.656 4.275 1.785 6.015l3.22-3.22A5.99 5.99 0 0 1 8 12.5c0-1.282.4-2.472 1.085-3.465L5.865 5.815A10.93 10.93 0 0 0 3 13Z"
                  />
                  <path
                    fill="#4285F4"
                    d="M13.99 24c3.045 0 5.81-1.233 7.82-3.225l-3.22-3.22A5.99 5.99 0 0 1 13.99 18.5a5.99 5.99 0 0 1-5.99-6.015c0-.46.057-.905.158-1.332L4.938 7.913A10.97 10.97 0 0 0 13.99 24Z"
                  />
                </svg>
                <span className="font-semibold text-gray-800">Continue with Google</span>
              </>
            )}
          </button>
        </div>

        <div className="pt-6 border-t border-border/50 text-center">
          <p className="text-xs text-muted-foreground/60">
            By continuing, you link your Google profile and grant read/write access to manage Google Business Profile locations.
          </p>
        </div>
      </div>
    </div>
  )
}

export default LoginContent
