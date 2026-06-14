'use client'

import { useEffect, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { RefreshCw, AlertTriangle, Shield, Layers } from 'lucide-react'
import { api } from '@/lib/api'

interface InviteDetails {
  email: string
  role: string
  organization_name: string
}

export default function InviteLandingPage() {
  const params = useParams()
  const router = useRouter()
  const token = params.token as string

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [invite, setInvite] = useState<InviteDetails | null>(null)
  const [loginLoading, setLoginLoading] = useState(false)

  useEffect(() => {
    if (!token) {
      setError('Invitation token is missing.')
      setLoading(false)
      return
    }

    verifyToken()
  }, [token])

  const verifyToken = async () => {
    setLoading(true)
    setError('')
    try {
      const data = await api.get<InviteDetails>(`/users/invite/${token}`)
      setInvite(data)
    } catch (err: any) {
      setError(err.message || 'This invitation link is invalid, expired, or has already been accepted.')
    } finally {
      setLoading(false)
    }
  }

  const handleContinueWithGoogle = async () => {
    setError('')
    setLoginLoading(true)
    try {
      const response: any = await api.get(`/auth/google/login?invite_token=${token}`)
      if (response && response.url) {
        window.location.href = response.url
      } else {
        throw new Error('Failed to retrieve authorization URL')
      }
    } catch (err: any) {
      setError(err.message || 'Failed to initiate Google Authentication.')
      setLoginLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background text-white px-4 py-12 sm:px-6 lg:px-8">
      <div className="w-full max-w-sm sm:max-w-md space-y-8 glass-panel p-6 sm:p-8 rounded-2xl border border-border shadow-2xl relative overflow-hidden text-center">
        {/* Background visual spheres */}
        <div className="absolute -top-24 -left-24 w-48 h-48 rounded-full bg-indigo-600/10 blur-3xl pointer-events-none"></div>
        <div className="absolute -bottom-24 -right-24 w-48 h-48 rounded-full bg-purple-600/10 blur-3xl pointer-events-none"></div>

        {/* Brand Header */}
        <div className="flex flex-col items-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 shadow-xl shadow-indigo-500/20">
            <RefreshCw className="h-6 w-6 text-white" />
          </div>
          <h2 className="mt-6 text-2xl font-bold tracking-tight text-white font-sans">
            GMB Sync Engine
          </h2>
          <p className="mt-1 text-xs text-muted-foreground">
            Workspace Invitation
          </p>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center py-10 space-y-3">
            <RefreshCw className="h-8 w-8 animate-spin text-indigo-500" />
            <p className="text-xs text-muted-foreground animate-pulse">Verifying secure token credentials...</p>
          </div>
        ) : error ? (
          <div className="py-6 space-y-5">
            <div className="flex mx-auto h-12 w-12 items-center justify-center rounded-xl bg-red-500/10 border border-red-500/20 text-red-400">
              <AlertTriangle className="h-6 w-6" />
            </div>
            <div className="space-y-2">
              <h3 className="text-base font-bold text-white">Invalid Invitation Link</h3>
              <p className="text-xs text-muted-foreground max-w-xs mx-auto leading-relaxed">
                {error}
              </p>
            </div>
            <button
              onClick={() => router.push('/login')}
              className="inline-flex justify-center items-center rounded-lg py-2.5 sm:py-2 px-5 sm:px-4 min-h-[44px] sm:min-h-0 text-xs font-semibold text-white bg-muted/20 border border-border hover:bg-muted/30 transition-colors cursor-pointer"
            >
              Back to Login
            </button>
          </div>
        ) : (
          invite && (
            <div className="space-y-6 pt-4">
              <div className="space-y-2">
                <p className="text-sm text-muted-foreground leading-relaxed">
                  You have been invited to join
                </p>
                <h3 className="text-xl font-extrabold text-white flex items-center justify-center gap-1.5 leading-tight">
                  <Layers className="h-5 w-5 text-indigo-400" />
                  {invite.organization_name}
                </h3>
                <div className="inline-flex flex-wrap items-center justify-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 mt-2 max-w-full">
                  <Shield className="h-3.5 w-3.5 shrink-0" />
                  <span className="break-words">Joining as {invite.role}</span>
                </div>
              </div>

              <div className="border-t border-border/50 pt-6 space-y-4">
                <div className="rounded-lg bg-indigo-500/5 border border-indigo-500/10 p-3 text-xs text-muted-foreground leading-relaxed text-left space-y-1">
                  <span className="font-bold text-white/80 block">Important Access Security:</span>
                  <span>This invite was issued specifically for <strong className="text-indigo-300 font-semibold">{invite.email}</strong>. To accept and register, click below and authenticate with that Google email.</span>
                </div>

                <button
                  onClick={handleContinueWithGoogle}
                  disabled={loginLoading}
                  className="w-full flex justify-center items-center gap-3 rounded-lg py-3.5 sm:py-3 px-4 min-h-[48px] sm:min-h-0 text-sm font-semibold text-white bg-white hover:bg-gray-50 border border-gray-200 text-gray-900 shadow-sm cursor-pointer disabled:opacity-50 transition-colors"
                >
                  {loginLoading ? (
                    <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent"></div>
                  ) : (
                    <>
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
            </div>
          )
        )}
      </div>
    </div>
  )
}
