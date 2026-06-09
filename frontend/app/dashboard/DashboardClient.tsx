'use client'

import { useEffect, useState, useRef, useMemo, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import AuthGuard from '@/components/AuthGuard'
import Navbar from '@/components/Navbar'
import { useAuth } from '@/hooks/useAuth'
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
import Link from 'next/link'

interface Location {
  id: number
  google_location_id: string
  location_name: string
  primary_category?: string
  address?: string
  phone?: string
  website?: string
  total_reviews?: number
  average_rating?: number
  sync_status: string
  last_synced_at?: string
  created_at: string
  is_verified?: boolean | null
  is_suspended?: boolean | null
  is_duplicate?: boolean | null
  // Embedded from latest SyncLog by the backend — no extra fetch needed
  latest_sync_status?: string | null
  latest_sync_error?: string | null
}

interface SyncLog {
  id: number
  location_id: number | null
  status: string
  error_message?: string
  run_type: string
  created_at: string
}

interface TokenStatus {
  status: 'active' | 'requires_refresh' | 'expired' | 'sandbox_mock' | string
  message: string
  expires_in_seconds?: number
  google_email?: string
}

interface LocationSLASummary {
  location_id: number
  location_name: string
  sla_enabled: boolean
  sla_tracking_started_at: string | null
  avg_response_hours: number | null
  avg_sla_tier: string | null
  total_replied: number
  overdue_count: number
  pending_count: number
}

function DashboardContent() {
  const searchParams = useSearchParams()
  const router = useRouter()
  
  // Dashboard states
  const [locations, setLocations] = useState<Location[]>([])
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([])
  const [tokenStatus, setTokenStatus] = useState<TokenStatus | null>(null)
  const [syncStatuses, setSyncStatuses] = useState<Record<number, { status: string, error_message: string | null, last_synced_at: string | null }>>({})
  const [pollingLocationIds, setPollingLocationIds] = useState<number[]>([])
  const [slaSummaries, setSlaSummaries] = useState<Record<number, LocationSLASummary>>({})
  
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

  const { user } = useAuth()
  const userRole = user?.role || 'Viewer'

  // Refs for interval tracking to prevent memory leaks
  const onboardingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const locationPollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

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

    // Ensure only one onboarding interval runs at a time
    if (onboardingIntervalRef.current) {
      clearInterval(onboardingIntervalRef.current)
      onboardingIntervalRef.current = null
    }

    let pollCount = 0
    onboardingIntervalRef.current = setInterval(async () => {
      pollCount++

      try {
        // Query database state
        const locationsData = await api.get<Location[]>('/locations/')
        const logsRes = await api.get<{ items: SyncLog[] }>('/locations/sync-logs?page=1&size=10')
        const logsData = logsRes.items
        const statusData = await api.get<TokenStatus>('/users/me/token-status')

        setLocations(locationsData)
        setSyncLogs(logsData)
        setTokenStatus(statusData)

        // Check if any org-level sync log (location_id === null) has reached a terminal state.
        // BUG-013 fix: Don't rely on error_message string content — just check the status field.
        const terminalLog = logsData.find(log =>
          log.location_id === null &&
          (log.status === 'Success' || log.status === 'Failed')
        )
        const hasFinished = !!terminalLog

        // If succeeded or failed, or max poll duration (30 seconds) reached, resolve onboarding overlay
        if (hasFinished || pollCount >= 15) {
          if (onboardingIntervalRef.current) {
            clearInterval(onboardingIntervalRef.current)
            onboardingIntervalRef.current = null
          }
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

    return () => {
      if (onboardingIntervalRef.current) {
        clearInterval(onboardingIntervalRef.current)
        onboardingIntervalRef.current = null
      }
    }
  }, [isOnboarding, router])

  useEffect(() => {
    // Clear any existing location polling interval before starting a new one
    if (locationPollingIntervalRef.current) {
      clearInterval(locationPollingIntervalRef.current)
      locationPollingIntervalRef.current = null
    }

    if (pollingLocationIds.length === 0) return;

    locationPollingIntervalRef.current = setInterval(() => {
      loadLocations(false);
    }, 5000);

    return () => {
      if (locationPollingIntervalRef.current) {
        clearInterval(locationPollingIntervalRef.current)
        locationPollingIntervalRef.current = null
      }
    }
  }, [pollingLocationIds.length]);

  const handleLocationSync = async (locationId: number) => {
    try {
      await api.post(`/reviews/sync?location_id=${locationId}`);
      setSyncStatuses(prev => ({
        ...prev,
        [locationId]: {
          status: 'Pending',
          last_synced_at: prev[locationId]?.last_synced_at || null,
          error_message: null
        }
      }));
      setPollingLocationIds(prev => prev.includes(locationId) ? prev : [...prev, locationId]);
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to trigger location review sync.');
    }
  }

  const formatTimeAgo = (dateStr: string | null | undefined) => {
    if (!dateStr) return 'never';
    const now = new Date();
    const date = new Date(dateStr);
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins} min ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hr${diffHours > 1 ? 's' : ''} ago`;
    return date.toLocaleDateString();
  }

  const renderSyncStatus = (loc: Location) => {
    const syncState = syncStatuses[loc.id];
    
    if (!syncState) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-muted/40 text-muted-foreground border border-border/50">
          <HelpCircle className="h-3 w-3 animate-pulse" />
          Checking...
        </span>
      );
    }

    if (syncState.status === 'Pending') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
          <RefreshCw className="h-3 w-3 animate-spin" />
          Syncing...
        </span>
      );
    }

    if (syncState.status === 'Failed') {
      return (
        <div className="flex flex-col items-end gap-1.5">
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 text-red-400 border border-red-500/20 max-w-xs break-words">
            <XCircle className="h-3 w-3 shrink-0" />
            <span>Last sync failed: {syncState.error_message || 'Unknown error'}</span>
          </span>
          {userRole !== 'Viewer' && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleLocationSync(loc.id);
              }}
              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-red-500/20 hover:bg-red-500/30 text-red-400 hover:text-red-300 text-[10px] font-bold border border-red-500/30 transition-colors cursor-pointer"
            >
              <RefreshCw className="h-3 w-3" />
              Retry
            </button>
          )}
        </div>
      );
    }

    // Success
    return (
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <CheckCircle2 className="h-3 w-3" />
          Last synced {formatTimeAgo(syncState.last_synced_at)}
        </span>
        {userRole !== 'Viewer' && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              handleLocationSync(loc.id);
            }}
            className="inline-flex items-center justify-center p-1 rounded bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-400 hover:text-indigo-300 border border-indigo-600/30 hover:border-indigo-600/50 transition-all cursor-pointer"
            title="Sync Reviews"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    );
  }

  const loadDashboardData = async () => {
    // Run all loaders in parallel — errors are handled inside each loader
    await Promise.allSettled([
      loadTokenStatus(),
      loadLocations(),
      loadSyncLogs(),
      loadSlaSummary(),
    ])
  }

  const loadSlaSummary = async () => {
    try {
      const data = await api.get<LocationSLASummary[]>('/locations/sla-summary')
      const summaryMap: Record<number, LocationSLASummary> = {}
      for (const item of data) {
        summaryMap[item.location_id] = item
      }
      setSlaSummaries(summaryMap)
    } catch (e: any) {
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

  const loadLocations = async (isInitial = true) => {
    if (isInitial) setLoadingLocations(true)
    try {
      const data = await api.get<Location[]>('/locations/')
      setLocations(data)

      // Seed sync status from the embedded fields — zero extra HTTP calls
      const newStatuses: Record<number, { status: string; last_synced_at: string | null; error_message: string | null }> = {}
      const pendingIds: number[] = []

      for (const loc of data) {
        // latest_sync_status comes from the latest SyncLog row joined by the backend.
        // Fall back to loc.sync_status (the denormalised column) when no log exists yet.
        const status = loc.latest_sync_status ?? loc.sync_status
        newStatuses[loc.id] = {
          status,
          last_synced_at: loc.last_synced_at ?? null,
          error_message: loc.latest_sync_error ?? null,
        }
        if (status === 'Pending') {
          pendingIds.push(loc.id)
        }
      }

      const currentLocationIds = new Set(data.map(loc => loc.id))
      setSyncStatuses(prev => {
        const filtered: typeof prev = {}
        for (const key in prev) {
          if (currentLocationIds.has(Number(key))) {
            filtered[Number(key)] = prev[Number(key)]
          }
        }
        return { ...filtered, ...newStatuses }
      })
      setPollingLocationIds(pendingIds)
    } catch (e: any) {
      console.error(e)
    } finally {
      if (isInitial) setLoadingLocations(false)
    }
  }

  const loadSyncLogs = async (isInitial = true) => {
    if (isInitial) setLoadingLogs(true)
    try {
      const data = await api.get<{ items: SyncLog[] }>('/locations/sync-logs?page=1&size=10')
      setSyncLogs(data.items)
    } catch (e: any) {
      console.error(e)
    } finally {
      if (isInitial) setLoadingLogs(false)
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

  // Get last successful sync timestamp — memoized to avoid recomputing on every render
  const getLastSyncedTime = useMemo(() => {
    const successLogs = syncLogs.filter(l => l.status === 'Success' && l.error_message?.includes('Synchronized'))
    if (successLogs.length > 0) {
      return new Date(successLogs[0].created_at).toLocaleString()
    }
    if (locations.length > 0 && locations[0].last_synced_at) {
      return new Date(locations[0].last_synced_at).toLocaleString()
    }
    return 'Pending Sync'
  }, [syncLogs, locations])

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
          {userRole !== 'Viewer' && (
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
                      Last Sync: <strong className="text-white">{getLastSyncedTime}</strong>
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
          )}

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
                  <Link href={`/dashboard/locations/${loc.id}`} key={loc.id} className="interactive-card glass-panel border border-border rounded-xl p-5 flex flex-col justify-between space-y-4 hover:border-indigo-500/50 transition-colors group block">
                    <div className="space-y-2">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <h4 className="text-base font-bold text-white leading-tight group-hover:text-indigo-400 transition-colors flex items-center gap-2">
                            {loc.location_name}
                            <ChevronRight className="h-4 w-4 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </h4>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-[10px] uppercase font-bold tracking-wider text-indigo-400">{loc.primary_category || 'Storefront'}</span>
                            
                            {/* State Badges */}
                            {loc.is_suspended && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                                Suspended
                              </span>
                            )}
                            {loc.is_duplicate && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                                Duplicate
                              </span>
                            )}
                            {loc.is_verified === false && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-zinc-500/10 text-zinc-400 border border-zinc-500/20">
                                Unverified
                              </span>
                            )}
                            {loc.is_verified === true && !loc.is_suspended && !loc.is_duplicate && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                Verified
                              </span>
                            )}
                            
                            {/* SLA Badge */}
                            {slaSummaries[loc.id]?.sla_enabled && (
                              <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                                slaSummaries[loc.id].avg_sla_tier === 'Best' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                                slaSummaries[loc.id].avg_sla_tier === 'Good' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' :
                                slaSummaries[loc.id].avg_sla_tier === 'Average' ? 'bg-amber-500/10 text-amber-400 border-amber-500/20' :
                                slaSummaries[loc.id].avg_sla_tier === 'Poor' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                                'bg-muted/20 text-muted-foreground border-border'
                              }`}>
                                {slaSummaries[loc.id].avg_response_hours !== null ? `${slaSummaries[loc.id].avg_response_hours}h SLA` : 'SLA: No Data'}
                              </span>
                            )}
                            
                            {loc.average_rating !== undefined && loc.average_rating !== null && (
                              <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-yellow-500/10 border border-yellow-500/20 text-yellow-500 text-[10px] font-bold">
                                <Sparkles className="h-2.5 w-2.5 fill-current" />
                                <span>{Number(loc.average_rating).toFixed(1)}</span>
                                {loc.total_reviews !== undefined && loc.total_reviews !== null && (
                                  <span className="text-muted-foreground/70 ml-0.5">({loc.total_reviews})</span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                        {renderSyncStatus(loc)}
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
                        <span
                          onClick={(e) => {
                            e.preventDefault();
                            e.stopPropagation();
                            window.open(loc.website, '_blank', 'noopener,noreferrer');
                          }}
                          className="flex items-center gap-1 text-indigo-400 hover:text-indigo-300 cursor-pointer"
                        >
                          <Globe className="h-3.5 w-3.5" />
                          <span>Website</span>
                        </span>
                      )}
                      {loc.last_synced_at && (
                        <span className="ml-auto text-[10px] text-muted-foreground/60 flex items-center gap-1">
                          <Calendar className="h-3.5 w-3.5" />
                          {new Date(loc.last_synced_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </span>
                      )}
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </section>
        </main>
      </div>
    </AuthGuard>
  )
}

export default DashboardContent
