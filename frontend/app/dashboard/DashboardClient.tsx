'use client'

import { useEffect, useState, useRef, useMemo, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { useBillingStatus } from '@/hooks/useBilling'
import { api } from '@/lib/api'
import {
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  HelpCircle,
  MapPin,
  Globe,
  Phone,
  Sparkles,
  LogOut,
  ChevronRight,
  PlusCircle,
  MoreHorizontal,
  Lock,
  LayoutGrid,
  Table as TableIcon,
  Star
} from 'lucide-react'
import Link from 'next/link'
import { UpgradeModal } from '@/components/modals/UpgradeModal'
import { RemandateBanner } from '@/components/billing/RemandateBanner'

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
  billing_status?: string  // 'active' | 'pending_payment' (locked, needs upgrade)
  last_synced_at?: string
  created_at: string
  is_verified?: boolean | null
  is_suspended?: boolean | null
  is_duplicate?: boolean | null
  // Embedded from latest SyncLog by the backend — no extra fetch needed
  latest_sync_status?: string | null
  latest_sync_error?: string | null
  // Embedded Health Score
  health_score?: number | null
  health_score_label?: string | null
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

interface OrganizationHealthSummaryOut {
  average_score: number
  total_locations: number
  excellent_count: number
  good_count: number
  average_count: number
  poor_count: number
  critical_count: number
}

// Locations store the GBP storefrontAddress as a JSON string
// ({addressLines, locality, administrativeArea, postalCode, regionCode}).
// Flatten it into a single readable line; fall back to the raw value if it
// isn't the JSON shape we expect (older rows / already-formatted strings).
function formatAddress(raw?: string | null): string | null {
  if (!raw) return null
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return trimmed
  try {
    const a = JSON.parse(trimmed) as {
      addressLines?: string[]
      locality?: string
      administrativeArea?: string
      postalCode?: string
      regionCode?: string
    }
    const parts = [
      ...(Array.isArray(a.addressLines) ? a.addressLines : []),
      a.locality,
      a.administrativeArea,
      a.postalCode,
      a.regionCode,
    ].filter(Boolean)
    return parts.length ? parts.join(', ') : trimmed
  } catch {
    return trimmed
  }
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
  const [healthSummary, setHealthSummary] = useState<OrganizationHealthSummaryOut | null>(null)
  
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
  const { data: billing } = useBillingStatus()

  // Computed Summaries
  const totalLocations = locations.length;
  const unverifiedCount = locations.filter(l => l.is_verified === false).length;
  const suspendedCount = locations.filter(l => l.is_suspended).length;
  const slaNeedsResponseCount = Object.values(slaSummaries).reduce((acc, summary) => acc + summary.pending_count, 0);

  // Filters
  const [activeFilter, setActiveFilter] = useState<'all' | 'unverified' | 'suspended'>('all');
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [connMenuOpen, setConnMenuOpen] = useState(false);

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

    // Hard cap so we never poll forever: if a location stays stuck in "Pending"
    // (e.g. a sync task died or Google errored out), stop after ~3 minutes
    // instead of hammering /locations/ every 5s for the life of the open tab.
    // The poll restarts naturally with a fresh budget whenever the pending set
    // actually changes (effect dep below), so genuine progress is never cut off.
    const MAX_LOCATION_POLLS = 36; // 36 × 5s = 3 minutes
    let pollCount = 0;

    locationPollingIntervalRef.current = setInterval(() => {
      pollCount++;
      loadLocations(false);
      if (pollCount >= MAX_LOCATION_POLLS && locationPollingIntervalRef.current) {
        clearInterval(locationPollingIntervalRef.current);
        locationPollingIntervalRef.current = null;
      }
    }, 5000);

    return () => {
      if (locationPollingIntervalRef.current) {
        clearInterval(locationPollingIntervalRef.current)
        locationPollingIntervalRef.current = null
      }
    }
  }, [pollingLocationIds.length]);

  // Refresh the (imperatively-loaded) locations grid after a billing change — payment
  // flows dispatch 'billing:refresh' since locations aren't in the react-query cache.
  useEffect(() => {
    const onBillingRefresh = () => loadLocations(false);
    window.addEventListener('billing:refresh', onBillingRefresh);
    return () => window.removeEventListener('billing:refresh', onBillingRefresh);
  }, []);

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

  // Single primary state badge (priority: suspended > duplicate > unverified > verified).
  // Darker text + stronger border so it stays readable on the white card background.
  const renderStateBadge = (loc: Location) => {
    if (loc.is_suspended) {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30">Suspended</span>;
    }
    if (loc.is_duplicate) {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30">Duplicate</span>;
    }
    if (loc.is_verified === false) {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-zinc-200 text-zinc-700 border border-zinc-400 dark:bg-zinc-500/15 dark:text-zinc-300 dark:border-zinc-500/30">Unverified</span>;
    }
    if (loc.is_verified === true) {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30">Verified</span>;
    }
    return null;
  };

  // Colour ramp shared by the health dot/score anchor.
  const healthClasses = (score: number) =>
    score >= 75 ? 'bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30'
      : score >= 60 ? 'bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30'
      : 'bg-red-100 text-red-800 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30';

  const loadDashboardData = async () => {
    // Run all loaders in parallel — errors are handled inside each loader
    await Promise.allSettled([
      loadTokenStatus(),
      loadLocations(),
      loadSyncLogs(),
      loadSlaSummary(),
      loadHealthSummary(),
    ])
  }

  const loadHealthSummary = async () => {
    try {
      const data = await api.get<OrganizationHealthSummaryOut>('/locations/health-score-summary')
      setHealthSummary(data)
    } catch (e: any) {
      console.error('Failed to load health summary:', e)
    }
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

  const storefrontsRef = useRef<HTMLElement>(null)

  // Compact "4m ago" / "2h ago" / "3d ago" relative time for sync timestamps.
  const relativeTime = (dateStr?: string | null) => {
    if (!dateStr) return null
    const diffMs = Date.now() - new Date(dateStr).getTime()
    const mins = Math.floor(diffMs / 60000)
    if (mins < 1) return 'just now'
    if (mins < 60) return `${mins}m ago`
    const hrs = Math.floor(mins / 60)
    if (hrs < 24) return `${hrs}h ago`
    return `${Math.floor(hrs / 24)}d ago`
  }

  // KPI cards click to filter + scroll to the storefront grid.
  const focusStorefronts = (filter: 'all' | 'unverified' | 'suspended') => {
    setActiveFilter(filter)
    storefrontsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const sortedLocations = useMemo(() => {
    let filtered = locations;
    if (activeFilter === 'unverified') {
      filtered = locations.filter(l => l.is_verified === false);
    } else if (activeFilter === 'suspended') {
      filtered = locations.filter(l => l.is_suspended);
    }
    return [...filtered].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  }, [locations, activeFilter])

  return (
    <>
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
              <h3 className="text-xl font-bold text-foreground tracking-tight">
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

      <div className="w-full">
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8 space-y-6 sm:space-y-8">
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

          {/* UPI AutoPay needs re-approval after a location add-on raised the plan */}
          {userRole !== 'Viewer' && <RemandateBanner />}

          {/* Billing / quota bar — only when something needs attention (locked locations) */}
          {userRole !== 'Viewer' && billing && (billing.pending_location_count ?? 0) > 0 && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl bg-amber-500/5 border border-amber-500/20 px-4 py-3">
              <div className="flex items-center gap-2 text-sm font-semibold text-amber-500">
                <Lock className="h-4 w-4 shrink-0" />
                <span>
                  {billing.pending_location_count} location{billing.pending_location_count === 1 ? '' : 's'} locked &middot;{' '}
                  {billing.active_location_count ?? 0} of {(billing.active_location_count ?? 0) + (billing.pending_location_count ?? 0)} active on your plan
                </span>
              </div>
              <button
                onClick={() => setShowUpgrade(true)}
                className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-widest bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm cursor-pointer transition-colors shrink-0"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Upgrade to unlock
              </button>
            </div>
          )}

          {/* Compact Google connection strip — whispers when healthy, shouts on error */}
          {userRole !== 'Viewer' && (
            (tokenStatus?.status === 'active' || tokenStatus?.status === 'requires_refresh') ? (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-2.5 shadow-sm">
                <div className="flex items-center gap-2 min-w-0 text-xs font-semibold">
                  <span className="flex h-2 w-2 rounded-full bg-emerald-500 shrink-0"></span>
                  <span className="truncate text-foreground">{tokenStatus.google_email || 'Google connected'}</span>
                  <span className="text-muted-foreground/40 hidden sm:inline">&middot;</span>
                  <span className="text-muted-foreground hidden sm:inline">
                    Synced {relativeTime(locations[0]?.last_synced_at) || getLastSyncedTime}
                  </span>
                  {tokenStatus.status === 'requires_refresh' && (
                    <span className="ml-1 text-indigo-400 hidden md:inline">&middot; token refresh pending</span>
                  )}
                </div>
                <div className="flex items-center gap-1.5 shrink-0 relative">
                  <button
                    onClick={handleTriggerSync}
                    disabled={syncing}
                    className="flex items-center gap-1.5 px-3 py-1.5 min-h-[40px] sm:min-h-0 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
                    <span>{syncing ? 'Syncing...' : 'Sync'}</span>
                  </button>
                  <button
                    onClick={() => setConnMenuOpen(o => !o)}
                    className="flex items-center justify-center h-10 w-10 sm:h-auto sm:w-auto sm:p-1.5 rounded-lg text-muted-foreground hover:bg-muted/40 transition-colors cursor-pointer"
                    aria-label="Connection options"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                  {connMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setConnMenuOpen(false)} />
                      <div className="absolute right-0 top-full mt-1 z-20 w-40 rounded-lg border border-border bg-card shadow-lg py-1">
                        <button
                          onClick={() => { setConnMenuOpen(false); handleDisconnectGoogle(); }}
                          className="flex items-center gap-2 w-full px-3 py-2 text-xs font-semibold text-muted-foreground hover:bg-red-500/10 hover:text-red-400 transition-colors cursor-pointer"
                        >
                          <LogOut className="h-3.5 w-3.5" />
                          Disconnect Google
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ) : tokenStatus?.status === 'expired' ? (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl bg-amber-500/5 border border-amber-500/20 px-4 py-3 text-xs font-semibold text-amber-400">
                <span className="flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  Google account expired or revoked — reconnect to resume background sync.
                </span>
                <button
                  onClick={handleConnectGoogle}
                  className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold text-white gradient-border-btn shadow cursor-pointer shrink-0"
                >
                  <PlusCircle className="h-3.5 w-3.5" />
                  Reconnect
                </button>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-border bg-card px-4 py-3 text-xs font-semibold text-muted-foreground shadow-sm">
                <span className="flex items-center gap-2">
                  <HelpCircle className="h-4 w-4 shrink-0" />
                  {tokenStatus ? 'Sandbox mode — connect Google for live storefront data.' : 'Connect your Google Business Profile to get started.'}
                </span>
                <button
                  onClick={handleConnectGoogle}
                  className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold text-white gradient-border-btn shadow cursor-pointer shrink-0"
                >
                  <PlusCircle className="h-3.5 w-3.5" />
                  Connect Google Account
                </button>
              </div>
            )
          )}

          {/* Summary KPI Cards — clickable to filter the storefront grid below */}
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
            <div className="text-left bg-card border border-border rounded-xl p-5 shadow-sm">
              <div className="text-sm font-medium text-muted-foreground mb-1">Avg Health Score</div>
              <div className={`text-2xl font-bold ${healthSummary?.average_score ? (healthSummary.average_score >= 75 ? 'text-emerald-600' : healthSummary.average_score >= 60 ? 'text-amber-600' : 'text-red-600') : 'text-muted-foreground'}`}>
                {healthSummary ? healthSummary.average_score : '--'}
              </div>
            </div>
            <button
              onClick={() => focusStorefronts('all')}
              className="text-left bg-card border border-border rounded-xl p-5 shadow-sm hover:border-primary/50 transition-colors cursor-pointer"
            >
              <div className="text-sm font-medium text-muted-foreground mb-1">Total Locations</div>
              <div className="text-2xl font-bold text-foreground">{totalLocations}</div>
            </button>
            <button
              onClick={() => focusStorefronts('unverified')}
              disabled={unverifiedCount === 0}
              className={`text-left bg-card border border-border rounded-xl p-5 shadow-sm transition-colors ${unverifiedCount === 0 ? 'opacity-50 cursor-default' : 'hover:border-amber-500/50 cursor-pointer'}`}
            >
              <div className="text-sm font-medium text-muted-foreground mb-1">Unverified</div>
              <div className={`text-2xl font-bold ${unverifiedCount === 0 ? 'text-muted-foreground' : 'text-amber-600'}`}>{unverifiedCount}</div>
            </button>
            <button
              onClick={() => focusStorefronts('suspended')}
              disabled={suspendedCount === 0}
              className={`text-left bg-card border border-border rounded-xl p-5 shadow-sm transition-colors ${suspendedCount === 0 ? 'opacity-50 cursor-default' : 'hover:border-destructive/50 cursor-pointer'}`}
            >
              <div className="text-sm font-medium text-muted-foreground mb-1">Suspended</div>
              <div className={`text-2xl font-bold ${suspendedCount === 0 ? 'text-muted-foreground' : 'text-destructive'}`}>{suspendedCount}</div>
            </button>
            <button
              onClick={() => focusStorefronts('all')}
              className="text-left bg-card border border-border rounded-xl p-5 shadow-sm hover:border-indigo-500/50 transition-colors cursor-pointer"
            >
              <div className="text-sm font-medium text-muted-foreground mb-1">SLA Needs Response</div>
              <div className={`text-2xl font-bold ${slaNeedsResponseCount === 0 ? 'text-muted-foreground' : 'text-indigo-600'}`}>{slaNeedsResponseCount}</div>
            </button>
          </section>

          {/* Synced Locations */}
          <section ref={storefrontsRef} className="space-y-4 scroll-mt-20">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-2">
                <MapPin className="h-5 w-5 text-primary" />
                <h3 className="text-lg font-bold tracking-tight text-foreground">
                  Synced Storefronts ({locations.length})
                </h3>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => setActiveFilter('all')}
                  className={`px-3 py-1.5 min-h-[40px] sm:min-h-0 rounded-md text-xs font-medium transition-colors ${activeFilter === 'all' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
                >
                  All
                </button>
                <button 
                  onClick={() => setActiveFilter('unverified')}
                  className={`px-3 py-1.5 min-h-[40px] sm:min-h-0 rounded-md text-xs font-medium transition-colors ${activeFilter === 'unverified' ? 'bg-amber-100 text-amber-700 border border-amber-200' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
                >
                  Unverified
                </button>
                <button 
                  onClick={() => setActiveFilter('suspended')}
                  className={`px-3 py-1.5 min-h-[40px] sm:min-h-0 rounded-md text-xs font-medium transition-colors ${activeFilter === 'suspended' ? 'bg-red-100 text-red-700 border border-red-200' : 'bg-muted text-muted-foreground hover:bg-muted/80'}`}
                >
                  Suspended
                </button>

                {/* Grid / Table view toggle — cards for browsing, table for scale */}
                <div className="ml-1 flex items-center gap-0.5 rounded-md border border-border bg-muted/40 p-0.5">
                  <button
                    onClick={() => setViewMode('grid')}
                    aria-label="Card view"
                    title="Card view"
                    className={`flex items-center justify-center h-9 w-9 sm:h-7 sm:w-7 rounded transition-colors ${viewMode === 'grid' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    <LayoutGrid className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => setViewMode('table')}
                    aria-label="Table view"
                    title="Table view"
                    className={`flex items-center justify-center h-9 w-9 sm:h-7 sm:w-7 rounded transition-colors ${viewMode === 'table' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}
                  >
                    <TableIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>

            {loadingLocations ? (
              <div className="flex h-48 w-full items-center justify-center rounded-2xl border border-border glass-panel">
                <div className="flex flex-col items-center gap-2">
                  <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
                  <p className="text-xs text-muted-foreground">Fetching business locations...</p>
                </div>
              </div>
            ) : locations.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-center rounded-xl border border-border bg-card shadow-sm">
                <MapPin className="h-10 w-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm font-bold text-foreground">No active storefronts found</p>
                <p className="text-xs text-muted-foreground max-w-sm mt-1">
                  We found no GBP storefront locations linked to this account. Refresh or connect a profile.
                </p>
              </div>
            ) : viewMode === 'table' ? (
              /* Dense table view — scales past ~10 storefronts, scannable & comparable */
              <div className="overflow-x-auto rounded-xl border border-border bg-card shadow-sm">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                      <th className="px-4 py-3 font-bold">Storefront</th>
                      <th className="px-4 py-3 font-bold">Health</th>
                      <th className="px-4 py-3 font-bold">Rating</th>
                      <th className="px-4 py-3 font-bold hidden md:table-cell">To reply</th>
                      <th className="px-4 py-3 font-bold">Status</th>
                      <th className="px-4 py-3 font-bold text-right hidden md:table-cell">Last sync</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedLocations.map((loc, index) => {
                      const isBlocked = loc.billing_status
                        ? loc.billing_status === 'pending_payment'
                        : (billing?.location_quota !== undefined && index >= billing.location_quota);
                      const pending = slaSummaries[loc.id]?.pending_count ?? 0;
                      const addr = formatAddress(loc.address);
                      return (
                        <tr
                          key={loc.id}
                          onClick={() => isBlocked ? setShowUpgrade(true) : router.push(`/dashboard/locations/${loc.id}`)}
                          className={`border-b border-border/50 last:border-0 transition-colors cursor-pointer ${isBlocked ? 'opacity-60 hover:bg-amber-500/5 active:bg-amber-500/10' : 'hover:bg-muted/30 active:bg-muted/50'}`}
                        >
                          <td className="px-4 py-3 max-w-xs">
                            <div className="font-bold text-foreground truncate">{loc.location_name}</div>
                            <div className="text-xs sm:text-[11px] text-muted-foreground truncate">
                              <span className="uppercase font-semibold tracking-wide text-primary/80">{loc.primary_category || 'Storefront'}</span>
                              {addr && <span> &middot; {addr}</span>}
                            </div>
                          </td>
                          <td className="px-4 py-3">
                            {loc.health_score != null ? (
                              <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-bold border ${healthClasses(loc.health_score)}`}>
                                {loc.health_score}
                              </span>
                            ) : <span className="text-muted-foreground/50">—</span>}
                          </td>
                          <td className="px-4 py-3 whitespace-nowrap">
                            {loc.average_rating != null ? (
                              <span className="inline-flex items-center gap-1 font-semibold text-amber-700 dark:text-amber-400">
                                <Star className="h-3.5 w-3.5 fill-current" />
                                {Number(loc.average_rating).toFixed(1)}
                                {loc.total_reviews != null && <span className="text-muted-foreground font-normal">({loc.total_reviews})</span>}
                              </span>
                            ) : <span className="text-muted-foreground/50">—</span>}
                          </td>
                          <td className="px-4 py-3 hidden md:table-cell">
                            {pending > 0 ? (
                              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold bg-indigo-100 text-indigo-800 border border-indigo-300 dark:bg-indigo-500/15 dark:text-indigo-300 dark:border-indigo-500/30">{pending}</span>
                            ) : <span className="text-muted-foreground/50">0</span>}
                          </td>
                          <td className="px-4 py-3">
                            {isBlocked ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30">
                                <Lock className="h-3 w-3" /> Locked
                              </span>
                            ) : (renderStateBadge(loc) ?? <span className="text-muted-foreground/50 text-xs">—</span>)}
                          </td>
                          <td className="px-4 py-3 text-right whitespace-nowrap text-xs text-muted-foreground hidden md:table-cell" title={loc.last_synced_at ? new Date(loc.last_synced_at).toLocaleString() : ''}>
                            {relativeTime(loc.last_synced_at) ?? 'never'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {sortedLocations.map((loc, index) => {
                  // Source of truth is the backend's per-location billing_status.
                  // Fall back to the quota heuristic only for older payloads that
                  // don't carry it yet.
                  const isBlocked = loc.billing_status
                    ? loc.billing_status === 'pending_payment'
                    : (billing?.location_quota !== undefined && index >= billing.location_quota);
                  const pending = slaSummaries[loc.id]?.pending_count ?? 0;
                  const sla = slaSummaries[loc.id];
                  const addr = formatAddress(loc.address);

                  return (
                  <Link
                    href={isBlocked ? '#' : `/dashboard/locations/${loc.id}`}
                    key={loc.id}
                    onClick={(e) => {
                      if (isBlocked) e.preventDefault();
                    }}
                    className={`bg-card text-card-foreground border border-border rounded-xl p-5 flex flex-col justify-between space-y-4 transition-colors shadow-sm group block ${isBlocked ? 'opacity-50 grayscale cursor-not-allowed' : 'hover:border-primary/50 hover:shadow-md'}`}
                  >
                    <div className="space-y-3">
                      {/* Title row: health anchor · name + category + one state badge · sync */}
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3 min-w-0 flex-1">
                          {/* Health score as the card's visual anchor */}
                          {loc.health_score != null ? (
                            <div
                              className={`flex flex-col items-center justify-center h-11 w-11 shrink-0 rounded-lg border ${healthClasses(loc.health_score)}`}
                              title={`Health ${loc.health_score}${loc.health_score_label ? ` (${loc.health_score_label})` : ''}`}
                            >
                              <span className="text-sm font-bold leading-none">{loc.health_score}</span>
                              <span className="text-[8px] uppercase font-bold tracking-wide opacity-70 mt-0.5">Health</span>
                            </div>
                          ) : (
                            <div className="flex items-center justify-center h-11 w-11 shrink-0 rounded-lg border border-border bg-muted/30 text-muted-foreground text-[9px] font-bold">N/A</div>
                          )}

                          <div className="min-w-0">
                            <h4 className={`text-base font-bold leading-tight flex items-center gap-1.5 ${isBlocked ? 'text-muted-foreground' : 'text-foreground group-hover:text-primary'} transition-colors`}>
                              <span className="truncate">{loc.location_name}</span>
                              {!isBlocked && <ChevronRight className="h-4 w-4 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />}
                            </h4>
                            <div className="flex flex-wrap items-center gap-1.5 mt-1">
                              <span className="text-[10px] uppercase font-bold tracking-wider text-primary">{loc.primary_category || 'Storefront'}</span>
                              {isBlocked ? (
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    // The card is a disabled Link; intercept so the
                                    // click opens the upgrade flow instead of navigating.
                                    e.preventDefault();
                                    e.stopPropagation();
                                    setShowUpgrade(true);
                                  }}
                                  className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 hover:bg-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30 dark:hover:bg-amber-500/25 cursor-pointer transition-colors"
                                >
                                  <Sparkles className="h-3 w-3" />
                                  Upgrade to Reactivate
                                </button>
                              ) : renderStateBadge(loc)}
                            </div>
                          </div>
                        </div>
                        {renderSyncStatus(loc)}
                      </div>

                      {/* Metrics row — quiet, uniform, no longer competing with status */}
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs sm:text-[11px] font-semibold">
                        {loc.average_rating != null && (
                          <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                            <Star className="h-3 w-3 fill-current" />
                            {Number(loc.average_rating).toFixed(1)}
                            {loc.total_reviews != null && <span className="text-muted-foreground font-normal">({loc.total_reviews})</span>}
                          </span>
                        )}
                        {sla?.sla_enabled && (
                          <span className="text-muted-foreground">
                            <span className="text-muted-foreground/40 mr-2">&middot;</span>
                            {sla.avg_response_hours != null ? `${sla.avg_response_hours}h SLA` : 'SLA: No data'}
                          </span>
                        )}
                        {pending > 0 && (
                          <span className="inline-flex items-center gap-1 text-indigo-700 dark:text-indigo-400">
                            <span className="text-muted-foreground/40 mr-1">&middot;</span>
                            {pending} to reply
                          </span>
                        )}
                      </div>

                      {addr && (
                        <p className="text-xs text-muted-foreground/90 font-medium leading-relaxed flex items-start gap-1.5">
                          <MapPin className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60 mt-0.5" />
                          <span>{addr}</span>
                        </p>
                      )}
                    </div>

                    {/* Footer — contact only; sync timestamp already lives in the status badge */}
                    {(loc.phone || loc.website) && (
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
                            className="flex items-center gap-1 text-indigo-500 hover:text-indigo-400 cursor-pointer"
                          >
                            <Globe className="h-3.5 w-3.5" />
                            <span>Website</span>
                          </span>
                        )}
                      </div>
                    )}
                  </Link>
                )})}
              </div>
            )}
          </section>
        </main>
      </div>

      <UpgradeModal open={showUpgrade} onOpenChange={setShowUpgrade} />
    </>
  )
}

export default DashboardContent
