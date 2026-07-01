'use client'

import { useEffect, useState, useRef, useMemo, Suspense } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { useBillingStatus } from '@/hooks/useBilling'
import { api } from '@/lib/api'
import { trackTrialStart } from '@/lib/analytics'
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
  Star,
  Zap,
  TrendingUp,
  TrendingDown,
  Minus,
  Search,
  ArrowRight,
  MessageSquare,
  MessageCircle,
  Clock
} from 'lucide-react'
import Link from 'next/link'
import { UpgradeModal } from '@/components/modals/UpgradeModal'
import { RemandateBanner } from '@/components/billing/RemandateBanner'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'

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
  // Embedded Microsite Status
  microsite_status?: string | null
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

interface ReputationSummary {
  avg_rating: number | null
  rated_location_count: number
  total_reviews: number
  total_reviews_all_time: number
  review_velocity_per_day: {
    current: number
    prior: number
    percentage_change: number | null
  }
  response_rate: number | null
}

interface TopKeyword {
  keyword: string
  impressions: number
  impressions_prior: number
  mom_growth: number | null
  is_brand_term: boolean
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
  const [reputationSummary, setReputationSummary] = useState<ReputationSummary | null>(null)
  const [topKeywords, setTopKeywords] = useState<TopKeyword[] | null>(null)
  
  // Loaders
  const [loadingLocations, setLoadingLocations] = useState(true)
  const [loadingLogs, setLoadingLogs] = useState(true)
  const [syncing, setSyncing] = useState(false)
  // Live progress of the location sync (polled from /locations/sync-status), so the UI
  // reflects the real background job instead of a fixed timer.
  const [syncProgress, setSyncProgress] = useState<null | {
    sync_in_progress: boolean; last_sync_status: string | null; last_sync_error: string | null;
    locations_total: number; locations_synced: number; locations_failed: number;
  }>(null)
  const syncPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

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
  const trialStartFiredRef = useRef(false)
  const locationPollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Parse URL params (onboarding flag, success/error alerts). Cheap & idempotent,
  // so it's fine for this to re-run when the query string changes.
  useEffect(() => {
    const onboardingParam = searchParams.get('onboarding')
    const successParam = searchParams.get('success')
    const errorParam = searchParams.get('error')
    const detailParam = searchParams.get('detail')

    if (onboardingParam === 'true') {
      // Don't trust the URL param blindly. A genuinely-new org has a Pending org-level
      // sync log (or none yet, because the Celery task just kicked off); an already-
      // onboarded user whose latest org sync is already terminal must NOT see the overlay
      // even if the param somehow leaks through. Confirm with the server first.
      ;(async () => {
        try {
          const logsRes = await api.get<{ items: SyncLog[] }>('/locations/sync-logs?page=1&size=10')
          const latestOrgLog = logsRes.items.find(log => log.location_id === null)
          const syncInProgress =
            !latestOrgLog || (latestOrgLog.status !== 'Success' && latestOrgLog.status !== 'Failed')
          if (syncInProgress) {
            setIsOnboarding(true)
          } else {
            // Already onboarded — strip the stale param without showing the overlay.
            router.replace('/dashboard')
          }
        } catch {
          // If we can't confirm, fail closed: skip the overlay rather than flash it.
          router.replace('/dashboard')
        }
      })()
    }

    if (successParam === 'google_connected') {
      setSuccessAlert('Google Business Profile successfully synced!')
    } else if (errorParam) {
      setErrorAlert(`Google authentication failed: ${detailParam || errorParam}`)
    }
  }, [searchParams, router])

  // Load dashboard data exactly once on mount. Kept separate from the param
  // effect above so a URL change (e.g. onboarding's router.replace('/dashboard'))
  // doesn't refire all ~7 dashboard requests.
  useEffect(() => {
    loadDashboardData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

        // First GBP sync succeeded -> fire trial_start once, now that we have locations.
        // business_category = most common primary_category (blank if none came back).
        if (terminalLog?.status === 'Success' && !trialStartFiredRef.current && user?.id) {
          trialStartFiredRef.current = true
          const counts = new Map<string, number>()
          for (const l of locationsData) {
            if (l.primary_category) counts.set(l.primary_category, (counts.get(l.primary_category) || 0) + 1)
          }
          const business_category = Array.from(counts.entries()).sort((a, b) => b[1] - a[1])[0]?.[0]
          trackTrialStart({ user_id: user.id, email: user.email, locationsCount: locationsData.length, business_category })
        }

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

  const renderMicrositeBadge = (status?: string | null) => {
    if (status === 'published') {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30">Microsite: Live</span>;
    }
    if (status === 'draft') {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30">Microsite: Draft</span>;
    }
    if (status === 'unpublished') {
      return <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-800 border border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30">Microsite: Offline</span>;
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
      loadReputationSummary(),
      loadTopKeywords(),
    ])
  }

  const loadReputationSummary = async () => {
    try {
      const data = await api.get<ReputationSummary>('/insights/summary')
      setReputationSummary(data)
    } catch (e: any) {
      console.error('Failed to load reputation summary:', e)
    }
  }

  const loadTopKeywords = async () => {
    try {
      const data = await api.get<{ items: TopKeyword[] }>(
        '/insights/keywords?page_size=5&sort_by=impressions&sort_desc=true'
      )
      setTopKeywords(data.items)
    } catch (e: any) {
      console.error('Failed to load top search queries:', e)
    }
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

  // Poll the real sync state until the location phase finishes (or fails), instead of
  // guessing with a fixed timer. Reviews/insights keep syncing in the background after.
  const pollSyncStatus = () => {
    if (syncPollRef.current) clearTimeout(syncPollRef.current)
    let sawInProgress = false
    let attempts = 0
    const tick = async () => {
      attempts++
      let s: any = null
      try { s = await api.get('/locations/sync-status') } catch { /* transient — retry */ }
      if (s) {
        setSyncProgress(s)
        if (s.sync_in_progress) sawInProgress = true
        // Finished once we've seen it running and it's no longer in progress. Grace of
        // ~20s covers the gap between queueing and the worker picking the task up.
        const finished = !s.sync_in_progress && (sawInProgress || attempts > 8)
        if (finished) {
          setSyncing(false)
          if (s.last_sync_status === 'Failed') {
            setErrorAlert(s.last_sync_error || 'Sync failed. Please try again.')
          } else {
            setSuccessAlert('Locations imported. Reviews & insights are updating in the background.')
          }
          loadLocations(); loadSyncLogs(); loadTokenStatus()
          syncPollRef.current = setTimeout(() => setSyncProgress(null), 5000)
          return
        }
      }
      syncPollRef.current = setTimeout(tick, 2500)
    }
    tick()
  }

  const handleTriggerSync = async () => {
    setSyncing(true)
    setErrorAlert('')
    setSuccessAlert('')
    setSyncProgress(null)
    try {
      await api.post('/locations/sync')
      pollSyncStatus()
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to trigger background synchronization.')
      setSyncing(false)
    }
  }

  // Stop polling if the user navigates away mid-sync.
  useEffect(() => () => { if (syncPollRef.current) clearTimeout(syncPollRef.current) }, [])

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
          {/* Alerts & Banners */}
          {errorAlert && (
            <div className="flex items-center gap-3 rounded-2xl bg-red-500/10 border border-red-500/20 p-4 text-sm font-semibold text-red-400 backdrop-blur-md shadow-sm">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <span>{errorAlert}</span>
            </div>
          )}

          {successAlert && (
            <div className="flex items-center gap-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 p-4 text-sm font-semibold text-emerald-400 backdrop-blur-md shadow-sm">
              <CheckCircle2 className="h-5 w-5 shrink-0" />
              <span>{successAlert}</span>
            </div>
          )}

          {/* Live sync progress — driven by the real background job, not a timer. */}
          {syncProgress && (syncProgress.sync_in_progress || syncing) && (
            <div className="rounded-2xl border border-primary/20 bg-primary/5 p-4 space-y-2 backdrop-blur-md shadow-sm">
              <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
                <RefreshCw className="h-4 w-4 shrink-0 animate-spin text-primary" />
                <span>
                  Importing your locations…
                  {syncProgress.locations_total > 0
                    ? ` ${syncProgress.locations_synced} of ${syncProgress.locations_total}`
                    : syncProgress.locations_synced > 0 ? ` ${syncProgress.locations_synced} imported` : ''}
                </span>
              </div>
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary/15">
                <div
                  className={`h-full rounded-full bg-primary transition-all duration-500 ${syncProgress.locations_total > 0 ? '' : 'w-1/3 animate-pulse'}`}
                  style={syncProgress.locations_total > 0
                    ? { width: `${Math.min(100, Math.round((syncProgress.locations_synced / syncProgress.locations_total) * 100))}%` }
                    : undefined}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                This can take a few minutes. Reviews &amp; insights keep updating in the background — you can keep using the dashboard.
              </p>
            </div>
          )}

          {/* UPI AutoPay needs re-approval after a location add-on raised the plan */}
          {userRole !== 'Viewer' && <RemandateBanner />}

          {/* Billing / quota bar — only when something needs attention (locked locations) */}
          {userRole !== 'Viewer' && billing && (billing.pending_location_count ?? 0) > 0 && (
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl bg-background/50 backdrop-blur-md border border-amber-500/30 px-5 py-4 shadow-sm">
              <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
                <div className="p-2 rounded-lg bg-amber-500/10 text-amber-500 shrink-0">
                  <Lock className="h-4 w-4" />
                </div>
                <span>
                  <span className="text-amber-500 font-bold">{billing.pending_location_count} location{billing.pending_location_count === 1 ? '' : 's'} locked</span> &middot;{' '}
                  <span className="text-muted-foreground">{billing.active_location_count ?? 0} of {(billing.active_location_count ?? 0) + (billing.pending_location_count ?? 0)} active on your plan</span>
                </span>
              </div>
              <button
                onClick={() => setShowUpgrade(true)}
                className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold uppercase tracking-widest bg-gradient-to-r from-amber-500 to-orange-500 text-white shadow hover:shadow-lg hover:-translate-y-0.5 cursor-pointer transition-all shrink-0"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Upgrade to unlock
              </button>
            </div>
          )}

          {/* Compact Google connection strip */}
          {userRole !== 'Viewer' && (
            (tokenStatus?.status === 'active' || tokenStatus?.status === 'requires_refresh') ? (
              <div className="flex items-center justify-between gap-3 rounded-2xl border border-border/50 bg-background/50 backdrop-blur-md px-5 py-3 shadow-sm">
                <div className="flex items-center gap-3 min-w-0 text-xs font-semibold">
                  <span className="flex h-2.5 w-2.5 rounded-full bg-emerald-500 shrink-0 shadow-[0_0_10px_rgba(16,185,129,0.5)]"></span>
                  <span className="truncate text-foreground font-bold">{tokenStatus.google_email || 'Google connected'}</span>
                  <span className="text-border hidden sm:inline">&middot;</span>
                  <span className="text-muted-foreground hidden sm:inline font-medium">
                    Synced {relativeTime(locations[0]?.last_synced_at) || getLastSyncedTime}
                  </span>
                  {tokenStatus.status === 'requires_refresh' && (
                    <span className="ml-1 text-indigo-400 hidden md:inline font-bold">&middot; token refresh pending</span>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 relative">
                  <button
                    onClick={handleTriggerSync}
                    disabled={syncing}
                    className="flex items-center gap-2 px-4 py-2 min-h-[40px] sm:min-h-0 rounded-xl text-xs font-bold text-white bg-indigo-500 hover:bg-indigo-400 shadow-md hover:shadow-lg disabled:opacity-50 transition-all cursor-pointer"
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
                    <span>{syncing ? 'Syncing...' : 'Sync'}</span>
                  </button>
                  <button
                    onClick={() => setConnMenuOpen(o => !o)}
                    className="flex items-center justify-center h-10 w-10 sm:h-auto sm:w-auto sm:p-2 rounded-xl text-muted-foreground hover:bg-muted transition-colors cursor-pointer"
                    aria-label="Connection options"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>
                  {connMenuOpen && (
                    <>
                      <div className="fixed inset-0 z-10" onClick={() => setConnMenuOpen(false)} />
                      <div className="absolute right-0 top-full mt-2 z-20 w-48 rounded-2xl border border-border/50 bg-card/95 backdrop-blur-xl shadow-xl py-2">
                        <button
                          onClick={() => { setConnMenuOpen(false); handleDisconnectGoogle(); }}
                          className="flex items-center gap-3 w-full px-4 py-2.5 text-xs font-bold text-muted-foreground hover:bg-red-500/10 hover:text-red-400 transition-colors cursor-pointer"
                        >
                          <LogOut className="h-4 w-4" />
                          Disconnect Google
                        </button>
                      </div>
                    </>
                  )}
                </div>
              </div>
            ) : tokenStatus?.status === 'expired' ? (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl bg-background/50 backdrop-blur-md border border-amber-500/30 px-5 py-4 shadow-sm">
                <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
                  <div className="p-2 rounded-lg bg-amber-500/10 text-amber-500 shrink-0">
                    <AlertTriangle className="h-4 w-4" />
                  </div>
                  <span>Google account expired or revoked — reconnect to resume background sync.</span>
                </div>
                <button
                  onClick={handleConnectGoogle}
                  className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-amber-500 to-orange-500 shadow hover:shadow-lg hover:-translate-y-0.5 cursor-pointer transition-all shrink-0"
                >
                  <PlusCircle className="h-3.5 w-3.5" />
                  Reconnect
                </button>
              </div>
            ) : (
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-border/50 bg-background/50 backdrop-blur-md px-5 py-4 shadow-sm">
                <div className="flex items-center gap-3 text-sm font-semibold text-foreground">
                  <div className="p-2 rounded-lg bg-primary/10 text-primary shrink-0">
                    <HelpCircle className="h-4 w-4" />
                  </div>
                  <span>{tokenStatus ? 'Sandbox mode — connect Google for live storefront data.' : 'Connect your Google Business Profile to get started.'}</span>
                </div>
                <button
                  onClick={handleConnectGoogle}
                  className="flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold text-white bg-primary shadow hover:shadow-lg hover:-translate-y-0.5 cursor-pointer transition-all shrink-0"
                >
                  <PlusCircle className="h-3.5 w-3.5" />
                  Connect Google Account
                </button>
              </div>
            )
          )}

          {/* Health Score + storefront status — top section, clickable to filter the grid */}
          <section className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            <div className="relative overflow-hidden text-left glass-panel rounded-2xl p-6 shadow-sm border-border/40">
              <div className="absolute -right-4 -top-4 opacity-[0.03] pointer-events-none">
                <Sparkles className="w-32 h-32 text-foreground" />
              </div>
              <div className="text-[11px] font-extrabold uppercase tracking-widest text-muted-foreground mb-2 relative z-10">Avg Health Score</div>
              <div className={`text-4xl font-black relative z-10 tracking-tight ${healthSummary?.average_score ? (healthSummary.average_score >= 75 ? 'text-emerald-500' : healthSummary.average_score >= 60 ? 'text-amber-500' : 'text-rose-500') : 'text-muted-foreground'}`}>
                {healthSummary ? <AnimatedNumber value={healthSummary.average_score} /> : '--'}
              </div>
            </div>
            <button
              onClick={() => focusStorefronts('all')}
              className="group relative overflow-hidden text-left glass-panel rounded-2xl p-6 shadow-sm border-border/40 hover:border-primary/50 hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-pointer"
            >
              <div className="absolute -right-4 -top-4 opacity-[0.03] group-hover:opacity-10 group-hover:scale-110 transition-all pointer-events-none">
                <MapPin className="w-32 h-32 text-primary" />
              </div>
              <div className="text-[11px] font-extrabold uppercase tracking-widest text-muted-foreground mb-2 relative z-10">Total Locations</div>
              <div className="text-4xl font-black text-foreground relative z-10 group-hover:text-primary transition-colors tracking-tight">
                <AnimatedNumber value={totalLocations} />
              </div>
            </button>
            <button
              onClick={() => focusStorefronts('unverified')}
              disabled={unverifiedCount === 0}
              className={`group relative overflow-hidden text-left glass-panel rounded-2xl p-6 shadow-sm border-border/40 transition-all duration-300 ${unverifiedCount === 0 ? 'opacity-60 cursor-default' : 'hover:border-amber-500/50 hover:shadow-lg hover:-translate-y-1 cursor-pointer'}`}
            >
              <div className={`absolute -right-4 -top-4 opacity-[0.03] transition-all pointer-events-none ${unverifiedCount > 0 ? 'group-hover:opacity-10 group-hover:scale-110 text-amber-500' : ''}`}>
                <AlertTriangle className="w-32 h-32" />
              </div>
              <div className="text-[11px] font-extrabold uppercase tracking-widest text-muted-foreground mb-2 relative z-10">Unverified</div>
              <div className={`text-4xl font-black relative z-10 transition-colors tracking-tight ${unverifiedCount === 0 ? 'text-muted-foreground' : 'text-amber-500'}`}>
                <AnimatedNumber value={unverifiedCount} />
              </div>
            </button>
            <button
              onClick={() => focusStorefronts('suspended')}
              disabled={suspendedCount === 0}
              className={`group relative overflow-hidden text-left glass-panel rounded-2xl p-6 shadow-sm border-border/40 transition-all duration-300 ${suspendedCount === 0 ? 'opacity-60 cursor-default' : 'hover:border-rose-500/50 hover:shadow-lg hover:-translate-y-1 cursor-pointer'}`}
            >
              <div className={`absolute -right-4 -top-4 opacity-[0.03] transition-all pointer-events-none ${suspendedCount > 0 ? 'group-hover:opacity-10 group-hover:scale-110 text-rose-500' : ''}`}>
                <XCircle className="w-32 h-32" />
              </div>
              <div className="text-[11px] font-extrabold uppercase tracking-widest text-muted-foreground mb-2 relative z-10">Suspended</div>
              <div className={`text-4xl font-black relative z-10 transition-colors tracking-tight ${suspendedCount === 0 ? 'text-muted-foreground' : 'text-rose-500'}`}>
                <AnimatedNumber value={suspendedCount} />
              </div>
            </button>
            <button
              onClick={() => focusStorefronts('all')}
              className="group relative overflow-hidden text-left glass-panel rounded-2xl p-6 shadow-sm border-border/40 hover:border-indigo-500/50 hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-pointer"
            >
              <div className="absolute -right-4 -top-4 opacity-[0.03] group-hover:opacity-10 group-hover:scale-110 transition-all pointer-events-none">
                <Clock className="w-32 h-32 text-indigo-500" />
              </div>
              <div className="text-[11px] font-extrabold uppercase tracking-widest text-muted-foreground mb-2 relative z-10">SLA Pending</div>
              <div className={`text-4xl font-black relative z-10 transition-colors tracking-tight ${slaNeedsResponseCount === 0 ? 'text-muted-foreground' : 'text-indigo-500'}`}>
                <AnimatedNumber value={slaNeedsResponseCount} />
              </div>
            </button>
          </section>

          {/* Reputation at-a-glance — org avg rating + review velocity */}
          {reputationSummary && totalLocations > 0 && (() => {
            const vel = reputationSummary.review_velocity_per_day
            const pct = vel.percentage_change
            const up = pct !== null && pct > 0
            const down = pct !== null && pct < 0
            const rating = reputationSummary.avg_rating
            const n = reputationSummary.rated_location_count
            const respRate = reputationSummary.response_rate
            return (
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <div className="glass-panel p-6 flex items-center gap-5 border-border/40">
                  <div className="p-3 rounded-2xl bg-gradient-to-br from-amber-400/20 to-orange-500/20 text-amber-500 shrink-0 shadow-inner">
                    <Star className="h-6 w-6 fill-amber-500" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-3xl font-black text-foreground leading-none tracking-tight">
                      {rating && rating > 0 ? <AnimatedNumber value={rating} isFloat formatter={(v) => v.toFixed(1)} /> : '—'}
                    </div>
                    <div className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground mt-2 truncate">
                      Avg rating across {n} loc{n === 1 ? '' : 's'}
                    </div>
                  </div>
                </div>

                <div className="glass-panel p-6 flex items-center gap-5 border-border/40">
                  <div className="p-3 rounded-2xl bg-gradient-to-br from-sky-400/20 to-indigo-500/20 text-sky-500 shrink-0 shadow-inner">
                    <MessageCircle className="h-6 w-6" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-3xl font-black text-foreground leading-none tabular-nums tracking-tight">
                      <AnimatedNumber value={reputationSummary.total_reviews_all_time} />
                    </div>
                    <div className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground mt-2 truncate">
                      Total reviews
                    </div>
                  </div>
                </div>

                <div className="glass-panel p-6 flex items-center gap-5 border-border/40">
                  <div className="p-3 rounded-2xl bg-gradient-to-br from-pink-400/20 to-rose-500/20 text-pink-500 shrink-0 shadow-inner">
                    <Zap className="h-6 w-6" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2">
                      <span className="text-3xl font-black text-foreground leading-none tracking-tight">
                        <AnimatedNumber value={vel.current} isFloat formatter={(v) => v.toFixed(1)} /><span className="text-sm font-bold text-muted-foreground ml-1">/day</span>
                      </span>
                    </div>
                    <div className="flex items-center gap-2 mt-2 truncate">
                      <span className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground">Reviews / day</span>
                      {pct !== null && (
                        <span className={`flex items-center text-[10px] font-black px-1.5 py-0.5 rounded-full ${up ? 'bg-emerald-500/10 text-emerald-500' : down ? 'bg-rose-500/10 text-rose-500' : 'bg-muted text-muted-foreground'}`}>
                          {pct === 0 ? <Minus className="h-3 w-3 mr-0.5" /> : up ? <TrendingUp className="h-3 w-3 mr-0.5" /> : <TrendingDown className="h-3 w-3 mr-0.5" />}
                          {Math.abs(pct).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="glass-panel p-6 flex items-center gap-5 border-border/40">
                  <div className="p-3 rounded-2xl bg-gradient-to-br from-emerald-400/20 to-teal-500/20 text-emerald-500 shrink-0 shadow-inner">
                    <MessageSquare className="h-6 w-6" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-3xl font-black text-foreground leading-none tracking-tight">
                      {respRate !== null && respRate !== undefined ? <><AnimatedNumber value={respRate} isFloat formatter={(v) => v.toFixed(0)} />%</> : '—'}
                    </div>
                    <div className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground mt-2 truncate">
                      Response rate
                    </div>
                  </div>
                </div>
              </div>
            )
          })()}

          {/* Top Search Queries teaser — hooks into the Search Intelligence deep-dive */}
          {topKeywords && totalLocations > 0 && (
            <Link
              href="/dashboard/insights/search-intelligence"
              className="block glass-panel p-6 group hover:border-primary/40 transition-all duration-300 shadow-sm border-border/40"
            >
              <div className="flex items-center justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="p-2 rounded-xl bg-sky-500/10 text-sky-500 shrink-0">
                    <Search className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-base font-extrabold text-foreground leading-none">Top Search Queries</h3>
                    <p className="text-[11px] font-semibold text-muted-foreground mt-1">How customers find you · last month</p>
                  </div>
                </div>
                <span className="flex items-center gap-1 text-[11px] font-extrabold uppercase tracking-widest text-primary group-hover:gap-2 transition-all">
                  View all <ArrowRight className="h-3.5 w-3.5" />
                </span>
              </div>

              {topKeywords.length === 0 ? (
                <div className="py-8 text-center text-sm font-medium text-muted-foreground">
                  No search-query data yet. Open Search Intelligence to sync the latest keywords.
                </div>
              ) : (
              <ul className="flex flex-col gap-1">
                {topKeywords.map((kw, idx) => {
                  const pct = kw.mom_growth
                  const up = pct !== null && pct > 0
                  const down = pct !== null && pct < 0
                  return (
                    <li key={idx} className="flex items-center gap-4 py-3 px-3 rounded-xl hover:bg-primary/5 transition-colors group/row">
                      <span className="text-[10px] font-black text-muted-foreground/30 w-4 shrink-0 tabular-nums">0{idx + 1}</span>
                      <span className="text-sm font-bold text-foreground truncate flex-1 min-w-0 group-hover/row:text-primary transition-colors">{kw.keyword}</span>
                      <span className={`hidden sm:inline-flex shrink-0 px-2 py-0.5 rounded text-[10px] font-extrabold uppercase tracking-widest ${
                        kw.is_brand_term ? 'border border-indigo-500/20 bg-indigo-500/10 text-indigo-500' : 'border border-border/50 bg-muted/30 text-muted-foreground'
                      }`}>
                        {kw.is_brand_term ? 'Brand' : 'Discovery'}
                      </span>
                      <span className="text-sm font-black text-foreground tabular-nums shrink-0 w-20 text-right">
                        {kw.impressions.toLocaleString()}
                      </span>
                      <span className={`flex items-center justify-end text-[11px] font-black w-16 shrink-0 ${
                        up ? 'text-emerald-500' : down ? 'text-rose-500' : 'text-muted-foreground/50'
                      }`}>
                        {pct === null ? (
                          kw.impressions_prior === 0 && kw.impressions > 0 ? 'New' : '—'
                        ) : (
                          <>
                            {pct === 0 ? <Minus className="h-3 w-3 mr-0.5" /> : up ? <TrendingUp className="h-3 w-3 mr-0.5" /> : <TrendingDown className="h-3 w-3 mr-0.5" />}
                            {Math.abs(pct).toFixed(0)}%
                          </>
                        )}
                      </span>
                    </li>
                  )
                })}
              </ul>
              )}
            </Link>
          )}

          {/* Synced Locations */}
          <section ref={storefrontsRef} className="space-y-6 scroll-mt-20">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-primary/10 rounded-xl text-primary">
                  <MapPin className="h-5 w-5" />
                </div>
                <h3 className="text-xl font-extrabold tracking-tight text-foreground">
                  Synced Storefronts <span className="text-muted-foreground font-medium">({locations.length})</span>
                </h3>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="flex bg-background/50 backdrop-blur-md p-1 rounded-xl border border-border/50 shadow-sm">
                  <button
                    onClick={() => setActiveFilter('all')}
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-extrabold uppercase tracking-widest transition-all ${activeFilter === 'all' ? 'bg-primary text-primary-foreground shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
                  >
                    All
                  </button>
                  <button 
                    onClick={() => setActiveFilter('unverified')}
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-extrabold uppercase tracking-widest transition-all ${activeFilter === 'unverified' ? 'bg-amber-500 text-white shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
                  >
                    Unverified
                  </button>
                  <button 
                    onClick={() => setActiveFilter('suspended')}
                    className={`px-4 py-1.5 rounded-lg text-[10px] font-extrabold uppercase tracking-widest transition-all ${activeFilter === 'suspended' ? 'bg-rose-500 text-white shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
                  >
                    Suspended
                  </button>
                </div>

                {/* Grid / Table view toggle — cards for browsing, table for scale */}
                <div className="ml-2 flex items-center gap-1 rounded-xl border border-border/50 bg-background/50 backdrop-blur-md p-1 shadow-sm">
                  <button
                    onClick={() => setViewMode('grid')}
                    aria-label="Card view"
                    title="Card view"
                    className={`flex items-center justify-center h-8 w-8 rounded-lg transition-all ${viewMode === 'grid' ? 'bg-card text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
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
              <div className="flex h-48 w-full items-center justify-center rounded-2xl border border-border/40 glass-panel shadow-sm">
                <div className="flex flex-col items-center gap-3">
                  <div className="p-3 bg-indigo-500/10 rounded-2xl">
                    <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
                  </div>
                  <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground">Fetching business locations...</p>
                </div>
              </div>
            ) : locations.length === 0 ? (
              <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-border/40 bg-card/50 backdrop-blur-md shadow-sm">
                <div className="p-4 bg-muted/50 rounded-2xl mb-4">
                  <MapPin className="h-10 w-10 text-muted-foreground/50" />
                </div>
                <p className="text-base font-extrabold text-foreground">No active storefronts found</p>
                <p className="text-sm font-semibold text-muted-foreground max-w-sm mt-2">
                  We found no GBP storefront locations linked to this account. Refresh or connect a profile.
                </p>
              </div>
            ) : viewMode === 'table' ? (
              /* Upgraded Premium Table View */
              <div className="overflow-x-auto rounded-2xl glass-panel shadow-sm border-border/40">
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-border/40 text-left text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground bg-muted/20">
                      <th className="px-6 py-4">Storefront</th>
                      <th className="px-5 py-4">Health</th>
                      <th className="px-5 py-4">Rating</th>
                      <th className="px-5 py-4 hidden md:table-cell">To reply</th>
                      <th className="px-5 py-4">Status</th>
                      <th className="px-5 py-4">Microsite</th>
                      <th className="px-6 py-4 text-right hidden md:table-cell">Last sync</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/20 font-medium bg-card/20 backdrop-blur-md">
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
                          className={`group transition-all duration-300 cursor-pointer ${isBlocked ? 'opacity-60 hover:bg-amber-500/5 active:bg-amber-500/10' : 'hover:bg-muted/30 hover:shadow-[inset_4px_0_0_0_hsl(var(--primary))]'}`}
                        >
                          <td className="px-6 py-4 max-w-xs">
                            <div className={`font-extrabold truncate transition-colors text-sm ${isBlocked ? 'text-foreground' : 'text-foreground group-hover:text-primary'}`}>{loc.location_name}</div>
                            <div className="flex items-center gap-1.5 mt-1.5 truncate">
                              <span className="text-[9px] uppercase font-black tracking-widest text-primary/80 bg-primary/10 px-1.5 py-0.5 rounded">{loc.primary_category || 'Storefront'}</span>
                              {addr && <span className="text-[11px] font-semibold text-muted-foreground truncate ml-1">{addr}</span>}
                            </div>
                          </td>
                          <td className="px-5 py-4">
                            {loc.health_score != null ? (
                              <span className={`inline-flex items-center px-2 py-1 rounded text-[11px] font-black tracking-wider border shadow-sm ${healthClasses(loc.health_score)}`}>
                                {loc.health_score}
                              </span>
                            ) : <span className="text-muted-foreground/30 font-black">—</span>}
                          </td>
                          <td className="px-5 py-4 whitespace-nowrap">
                            {loc.average_rating != null ? (
                              <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-black border shadow-sm ${
                                loc.average_rating >= 4.5 ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 
                                loc.average_rating >= 3.5 ? 'bg-amber-500/10 text-amber-500 border-amber-500/20' : 
                                'bg-rose-500/10 text-rose-500 border-rose-500/20'
                              }`}>
                                <Star className="h-3 w-3 fill-current" />
                                {Number(loc.average_rating).toFixed(1)}
                                {loc.total_reviews != null && <span className="opacity-60 ml-0.5">({loc.total_reviews})</span>}
                              </span>
                            ) : <span className="text-muted-foreground/30 font-black">—</span>}
                          </td>
                          <td className="px-5 py-4 hidden md:table-cell">
                            {pending > 0 ? (
                              <span className="inline-flex items-center px-2 py-1 rounded text-[10px] uppercase font-extrabold tracking-widest bg-indigo-500/10 text-indigo-500 border border-indigo-500/20 shadow-sm">{pending} pending</span>
                            ) : <span className="text-muted-foreground/30 font-black">—</span>}
                          </td>
                          <td className="px-5 py-4">
                            {isBlocked ? (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] uppercase font-extrabold tracking-widest bg-amber-500/10 text-amber-500 border border-amber-500/20 shadow-sm">
                                <Lock className="h-3 w-3" /> Locked
                              </span>
                            ) : (renderStateBadge(loc) ?? <span className="text-muted-foreground/30 font-black">—</span>)}
                          </td>
                          <td className="px-5 py-4">
                            {!isBlocked && renderMicrositeBadge(loc.microsite_status)}
                          </td>
                          <td className="px-6 py-4 text-right whitespace-nowrap text-[11px] font-bold text-muted-foreground hidden md:table-cell" title={loc.last_synced_at ? new Date(loc.last_synced_at).toLocaleString() : ''}>
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
                    className={`glass-panel border-border/40 rounded-2xl p-7 flex flex-col justify-between space-y-6 transition-all duration-500 shadow-sm group block ${isBlocked ? 'opacity-60 grayscale cursor-not-allowed' : 'hover:border-primary/50 hover:shadow-lg hover:-translate-y-1'}`}
                  >
                    <div className="space-y-5">
                      {/* Title row: health anchor · name + category + one state badge · sync */}
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-4 min-w-0 flex-1">
                          {/* Health score as the card's visual anchor */}
                          {loc.health_score != null ? (
                            <div
                              className={`flex flex-col items-center justify-center h-14 w-14 shrink-0 rounded-xl border ${healthClasses(loc.health_score)} shadow-inner`}
                              title={`Health ${loc.health_score}${loc.health_score_label ? ` (${loc.health_score_label})` : ''}`}
                            >
                              <span className="text-xl font-black leading-none">{loc.health_score}</span>
                              <span className="text-[8px] uppercase font-extrabold tracking-widest opacity-80 mt-1">Health</span>
                            </div>
                          ) : (
                            <div className="flex items-center justify-center h-14 w-14 shrink-0 rounded-xl border border-border bg-muted/20 text-muted-foreground text-[10px] font-black">N/A</div>
                          )}

                          <div className="min-w-0 pt-0.5">
                            <h4 className={`text-lg font-extrabold leading-tight flex items-center gap-1.5 ${isBlocked ? 'text-muted-foreground' : 'text-foreground group-hover:text-primary'} transition-colors tracking-tight`}>
                              <span className="truncate">{loc.location_name}</span>
                              {!isBlocked && <ChevronRight className="h-4 w-4 shrink-0 opacity-0 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all" />}
                            </h4>
                            <div className="flex flex-wrap items-center gap-2 mt-2">
                              <span className="text-[10px] uppercase font-black tracking-widest text-primary/80 bg-primary/5 px-2 py-0.5 rounded">{loc.primary_category || 'Storefront'}</span>
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
                                  className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] uppercase font-extrabold tracking-widest bg-amber-500/10 text-amber-500 border border-amber-500/20 shadow-sm hover:bg-amber-500/20 cursor-pointer transition-colors"
                                >
                                  <Sparkles className="h-3 w-3" />
                                  Upgrade to Reactivate
                                </button>
                              ) : (
                                <div className="flex flex-wrap items-center gap-2">
                                  {renderStateBadge(loc)}
                                  {renderMicrositeBadge(loc.microsite_status)}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                        {renderSyncStatus(loc)}
                      </div>

                      {/* Metrics row — quiet, uniform, no longer competing with status */}
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] font-extrabold uppercase tracking-widest bg-muted/10 p-3 rounded-xl border border-border/20">
                        {loc.average_rating != null && (
                          <span className="inline-flex items-center gap-1 text-amber-500">
                            <Star className="h-3.5 w-3.5 fill-current" />
                            {Number(loc.average_rating).toFixed(1)}
                            {loc.total_reviews != null && <span className="text-muted-foreground/60 font-semibold ml-0.5">({loc.total_reviews})</span>}
                          </span>
                        )}
                        {sla?.sla_enabled && (
                          <span className="text-muted-foreground/70 flex items-center gap-2">
                            <span className="h-1 w-1 rounded-full bg-border"></span>
                            {sla.avg_response_hours != null ? `${sla.avg_response_hours}h SLA` : 'SLA: No data'}
                          </span>
                        )}
                        {pending > 0 && (
                          <span className="inline-flex items-center gap-2 text-indigo-500">
                            <span className="h-1 w-1 rounded-full bg-border"></span>
                            {pending} to reply
                          </span>
                        )}
                      </div>

                      {addr && (
                        <p className="text-[11px] text-muted-foreground/80 font-bold leading-relaxed flex items-start gap-2">
                          <MapPin className="h-4 w-4 shrink-0 text-muted-foreground/40 mt-0.5" />
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
