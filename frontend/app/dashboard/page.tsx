'use client'

import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'
import Navbar from '@/components/Navbar'
import { api } from '@/lib/api'
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  MapPin,
  Calendar,
  Globe,
  Phone,
  Layers,
  Sparkles,
  LogOut,
  ChevronRight,
  PlusCircle
} from 'lucide-react'

interface Location {
  id: number
  google_location_id: string
  location_name: string
  primary_category?: string
  address?: string
  phone?: string
  website?: string
  sync_status: string
  last_synced_at?: string
  created_at: string
}

interface SyncLog {
  id: number
  status: string
  error_message?: string
  run_type: string
  created_at: string
}

interface TokenStatus {
  status: string
  message: string
  expires_in_seconds?: number
  google_email?: string
}

export default function DashboardPage() {
  const searchParams = useSearchParams()
  const router = useRouter()
  
  // Dashboard states
  const [locations, setLocations] = useState<Location[]>([])
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([])
  const [tokenStatus, setTokenStatus] = useState<TokenStatus | null>(null)
  
  // Loaders
  const [loadingLocations, setLoadingLocations] = useState(true)
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [syncing, setSyncing] = useState(false)
  
  // Onboarding Sync states
  const [isOnboarding, setIsOnboarding] = useState(false)
  const [onboardingSuccess, setOnboardingSuccess] = useState(false)
  
  // Feedbacks
  const [errorAlert, setErrorAlert] = useState('')
  const [successAlert, setSuccessAlert] = useState('')

  useEffect(() => {
    const onboardingParam = searchParams.get('onboarding')
    const successParam = searchParams.get('success')
    const errorParam = searchParams.get('error')
    const detailParam = searchParams.get('detail')

    if (onboardingParam === 'true') {
      setIsOnboarding(true)
    }

    if (successParam === 'google_connected') {
      setSuccessAlert('Google Business Profile successfully synced!')
    } else if (errorParam) {
      setErrorAlert(`Google authentication failed: ${detailParam || errorParam}`)
    }

    // Load initial data
    loadDashboardData()
  }, [searchParams])

  // Polling logic when onboarding is active to check for Celery task completion
  useEffect(() => {
    if (!isOnboarding) return

    let pollCount = 0
    const pollInterval = setInterval(async () => {
      pollCount++
      
      try {
        // Query database state
        const locationsData = await api.get<Location[]>('/locations/')
        const logsData = await api.get<SyncLog[]>('/locations/sync-logs')
        const statusData = await api.get<TokenStatus>('/users/me/token-status')
        
        setLocations(locationsData)
        setSyncLogs(logsData)
        setTokenStatus(statusData)

        // Check if sync completed (represented by sync log records and updated locations)
        const hasFinished = logsData.length > 0 && (
          logsData[0].status === 'Success' || logsData[0].status === 'Failed'
        )

        // If succeeded or failed, or max poll duration (30 seconds) reached, resolve onboarding overlay
        if (hasFinished || pollCount >= 15) {
          clearInterval(pollInterval)
          setOnboardingSuccess(true)
          
          setTimeout(() => {
            setIsOnboarding(false)
            // Clear URL parameter
            router.replace('/dashboard')
          }, 1500)
        }
      } catch (e) {
        console.error('Polling error', e)
      }
    }, 2000)

    return () => clearInterval(pollInterval)
  }, [isOnboarding, router])

  const loadDashboardData = async () => {
    try {
      loadTokenStatus()
      loadLocations()
      loadSyncLogs()
    } catch (e) {
      console.error(e)
    }
  }

  const loadTokenStatus = async () => {
    try {
      const data = await api.get<TokenStatus>('/users/me/token-status')
      setTokenStatus(data)
    } catch (e: any) {
      console.error(e)
    }
  }

  const loadLocations = async () => {
    setLoadingLocations(true)
    try {
      const data = await api.get<Location[]>('/locations/')
      setLocations(data)
    } catch (e: any) {
      console.error(e)
    } finally {
      setLoadingLocations(false)
    }
  }

  const loadSyncLogs = async () => {
    setLoadingLogs(true)
    try {
      const data = await api.get<SyncLog[]>('/locations/sync-logs')
      setSyncLogs(data)
    } catch (e: any) {
      console.error(e)
    } finally {
      setLoadingLogs(false)
    }
  }

  const handleConnectGoogle = async () => {
    setErrorAlert('')
    setSuccessAlert('')
    try {
      const response: any = await api.get(`/auth/google/login`)
      if (response && response.url) {
        window.location.href = response.url
      }
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to connect Google Account.')
    }
  }

  const handleDisconnectGoogle = async () => {
    if (!confirm('Are you sure you want to disconnect Google Business Profile? Synced locations will remain, but automatic syncs will stop.')) {
      return
    }
    
    setErrorAlert('')
    setSuccessAlert('')
    try {
      await api.post('/users/disconnect-google')
      setSuccessAlert('Google Account disconnected successfully.')
      loadDashboardData()
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to disconnect Google Account.')
    }
  }

  const handleTriggerSync = async () => {
    setSyncing(true)
    setErrorAlert('')
    setSuccessAlert('')
    try {
      const response: any = await api.post('/locations/sync')
      setSuccessAlert(response.message || 'Synchronization task queued in background!')
      setTimeout(() => {
        loadLocations()
        loadSyncLogs()
        loadTokenStatus()
        setSyncing(false)
      }, 3000)
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to trigger background synchronization.')
      setSyncing(false)
    }
  }

  // Get last successful sync timestamp
  const getLastSyncedTime = () => {
    const successLogs = syncLogs.filter(l => l.status === 'Success' && l.error_message?.includes('Synchronized'))
    if (successLogs.length > 0) {
      return new Date(successLogs[0].created_at).toLocaleString()
    }
    if (locations.length > 0 && locations[0].last_synced_at) {
      return new Date(locations[0].last_synced_at).toLocaleString()
    }
    return 'Pending Sync'
  }

  return (
    <AuthGuard>
      {/* Onboarding Fullscreen Sync Overlay */}
      {isOnboarding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-md">
          <div className="flex flex-col items-center text-center p-8 max-w-md glass-panel border border-border rounded-2xl shadow-2xl space-y-6 relative overflow-hidden">
            <div className="absolute -top-12 -left-12 w-24 h-24 rounded-full bg-indigo-500/10 blur-xl"></div>
            
            {onboardingSuccess ? (
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 border border-emerald-500/20 shadow-lg text-emerald-400">
                <CheckCircle2 className="h-8 w-8 animate-bounce" />
              </div>
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/20 shadow-lg text-indigo-400">
                <RefreshCw className="h-8 w-8 animate-spin" />
              </div>
            )}

            <div className="space-y-2">
              <h3 className="text-xl font-bold text-white tracking-tight">
                {onboardingSuccess ? 'Onboarding Complete!' : 'Syncing Workspace...'}
              </h3>
              <p className="text-xs text-muted-foreground leading-relaxed max-w-xs">
                {onboardingSuccess 
                  ? 'We have successfully connected your Google Business Profile and downloaded your storefronts!'
                  : 'Retrieving business groups, downloading storefront locations, and caching local metadata layers...'}
              </p>
            </div>

            {!onboardingSuccess && (
              <div className="w-full bg-muted/30 rounded-full h-1.5 overflow-hidden border border-border/40">
                <div className="bg-gradient-to-r from-indigo-500 to-purple-600 h-full rounded-full animate-[pulse_1.5s_infinite] w-3/4"></div>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
          {/* Action alerts */}
          {errorAlert && (
            <div className="flex items-center gap-3 rounded-xl bg-red-500/10 border border-red-500/20 p-4 text-sm font-medium text-red-400">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <span>{errorAlert}</span>
            </div>
          )}

          {successAlert && (
            <div className="flex items-center gap-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-4 text-sm font-medium text-emerald-400">
              <CheckCircle2 className="h-5 w-5 shrink-0" />
              <span>{successAlert}</span>
            </div>
          )}

          {/* Connection Status widget & Alert Lifecycles */}
          <section className="glass-panel border border-border rounded-2xl p-6 relative overflow-hidden">
            <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full bg-indigo-500/5 blur-2xl"></div>
            
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-2 w-2 rounded-full bg-emerald-500 animate-ping"></span>
                  <h3 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                    <Sparkles className="h-5 w-5 text-indigo-400" />
                    Google Connection Status
                  </h3>
                </div>
                <p className="text-sm text-muted-foreground max-w-2xl">
                  Configure real-time storefront synchronization. We check and fetch data hourly from your Google Business Profile endpoints.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-3 shrink-0">
                {tokenStatus?.status === 'active' || tokenStatus?.status === 'requires_refresh' ? (
                  <>
                    <button
                      onClick={handleTriggerSync}
                      disabled={syncing}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors cursor-pointer"
                    >
                      <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
                      <span>{syncing ? 'Syncing...' : 'Sync Locations'}</span>
                    </button>
                    
                    <button
                      onClick={handleDisconnectGoogle}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-muted-foreground bg-muted/20 border border-border hover:bg-red-500/10 hover:text-red-400 transition-colors cursor-pointer"
                    >
                      <LogOut className="h-4 w-4" />
                      <span>Disconnect</span>
                    </button>
                  </>
                ) : (
                  <button
                    onClick={handleConnectGoogle}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white gradient-border-btn shadow-lg cursor-pointer"
                  >
                    <PlusCircle className="h-4 w-4" />
                    <span>Connect Google Account</span>
                  </button>
                )}
              </div>
            </div>

            {/* Token expiry / re-auth warnings */}
            {tokenStatus && (
              <div className="mt-6 border-t border-border/60 pt-6">
                {tokenStatus.status === 'active' ? (
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-semibold">
                    <span className="flex items-center gap-2 text-emerald-400">
                      <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                      Account: <strong className="text-white">{tokenStatus.google_email}</strong>
                    </span>
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      <Calendar className="h-4 w-4 text-indigo-400" />
                      Last Sync: <strong className="text-white">{getLastSyncedTime()}</strong>
                    </span>
                  </div>
                ) : tokenStatus.status === 'requires_refresh' ? (
                  <div className="flex items-center gap-3 rounded-lg bg-indigo-500/5 border border-indigo-500/10 p-3 text-xs font-semibold text-indigo-400">
                    <RefreshCw className="h-4 w-4 animate-spin shrink-0" />
                    <span>Google tokens expired. A silent refresh will occur automatically during the next synchronization run.</span>
                  </div>
                ) : tokenStatus.status === 'expired' ? (
                  <div className="flex items-center gap-3 rounded-lg bg-amber-500/5 border border-amber-500/10 p-3 text-xs font-semibold text-amber-400">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Google account expired or revoked! Re-authentication required to resume background sync loops. Please reconnect your account.</span>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 text-xs font-semibold text-muted-foreground">
                    <HelpCircle className="h-4 w-4" />
                    <span>Operating in Sandbox Mock mode. Link your real Google account to fetch production storefront data.</span>
                  </div>
                )}
              </div>
            )}
          </section>

          {/* Synced Locations */}
          <section className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
                <MapPin className="h-4 w-4 text-indigo-400" />
                Synced Storefronts ({locations.length})
              </h3>
              <span className="text-xs font-semibold text-muted-foreground">
                Auto-syncs hourly
              </span>
            </div>

            {loadingLocations ? (
              <div className="flex h-48 w-full items-center justify-center rounded-2xl border border-border glass-panel">
                <div className="flex flex-col items-center gap-2">
                  <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
                  <p className="text-xs text-muted-foreground">Fetching business locations...</p>
                </div>
              </div>
            ) : locations.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-border glass-panel">
                <MapPin className="h-10 w-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm font-bold text-white">No active storefronts found</p>
                <p className="text-xs text-muted-foreground max-w-sm mt-1">
                  We found no GBP storefront locations linked to this account. Refresh or connect a profile.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {locations.map((loc) => (
                  <div key={loc.id} className="interactive-card glass-panel border border-border rounded-xl p-5 flex flex-col justify-between space-y-4">
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-4">
                        <div>
                          <h4 className="text-base font-bold text-white leading-tight">{loc.location_name}</h4>
                          <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-400 mt-0.5 block">{loc.primary_category || 'Storefront'}</span>
                        </div>
                        <span className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                          loc.sync_status === 'Synced' 
                            ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                            : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                        }`}>
                          <CheckCircle2 className="h-3 w-3" />
                          {loc.sync_status}
                        </span>
                      </div>

                      {loc.address && (
                        <p className="text-xs text-muted-foreground/90 font-medium leading-relaxed pt-1 flex items-start gap-1.5">
                          <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60 mt-0.5" />
                          <span>{loc.address}</span>
                        </p>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border/50 pt-4 text-xs font-semibold text-muted-foreground">
                      {loc.phone && (
                        <span className="flex items-center gap-1">
                          <Phone className="h-3.5 w-3.5 text-muted-foreground/50" />
                          {loc.phone}
                        </span>
                      )}
                      {loc.website && (
                        <a href={loc.website} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300">
                          <Globe className="h-3.5 w-3.5" />
                          <span>Website</span>
                        </a>
                      )}
                      {loc.last_synced_at && (
                        <span className="ml-auto text-[10px] text-muted-foreground/60 flex items-center gap-1">
                          <Calendar className="h-3.5 w-3.5" />
                          {new Date(loc.last_synced_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Sync logs Table */}
          <section className="space-y-4">
            <h3 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              <Calendar className="h-4 w-4 text-indigo-400" />
              Synchronization Audits
            </h3>

            {loadingLogs ? (
              <div className="flex h-36 w-full items-center justify-center rounded-2xl border border-border glass-panel">
                <RefreshCw className="h-5 w-5 animate-spin text-indigo-500" />
              </div>
            ) : syncLogs.length === 0 ? (
              <div className="text-center p-8 border border-border rounded-xl glass-panel text-xs text-muted-foreground">
                No logs generated yet.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-border glass-panel">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="border-b border-border/70 text-[10px] uppercase font-bold tracking-wider text-muted-foreground/80 bg-muted/10">
                      <th className="px-6 py-3">Timestamp</th>
                      <th className="px-6 py-3">Run Type</th>
                      <th className="px-6 py-3">Status</th>
                      <th className="px-6 py-3">Audit Details / Diagnostics</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 text-xs font-medium">
                    {syncLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-muted/5 transition-colors">
                        <td className="px-6 py-4 whitespace-nowrap text-muted-foreground">
                          {new Date(log.created_at).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span className={`inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold ${
                            log.run_type === 'Scheduled' 
                              ? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
                              : 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                          }`}>
                            {log.run_type}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {log.status === 'Success' ? (
                            <span className="flex items-center gap-1 text-emerald-400 font-bold text-[10px] uppercase">
                              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                              Success
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-red-400 font-bold text-[10px] uppercase">
                              <XCircle className="h-3.5 w-3.5 text-red-500" />
                              Failed
                            </span>
                          )}
                        </td>
                        <td className="px-6 py-4 text-muted-foreground/90 font-mono text-[11px] leading-normal break-all">
                          {log.error_message || 'N/A'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </main>
      </div>
    </AuthGuard>
  )
}
