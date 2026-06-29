'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import {
  Eye,
  Search,
  MapPin,
  Phone,
  Globe,
  Navigation,
  Calendar,
  AlertTriangle,
  RefreshCw,
  Star,
  Zap,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import {
  KpiCard,
  TrendChart,
  TrendLegend,
  ConversionQuality,
  SearchComposition,
  ReputationGrid,
  PeriodComparison,
  PlatformDeviceImpressions,
  type ReputationVelocity,
  type OverviewKPIs,
  type DailyMetricPoint,
  type SentimentBreakdown,
  type SLAMetricsSummary,
  type IssueCategorySummary,
  type PlatformDeviceBreakdown,
  type TrendMetricKey,
} from '@/components/insights/InsightsShared'

interface LocationInsightsResponse {
  location_id: number
  location_name: string
  attention_needed: boolean
  attention_reason: string | null
  last_insights_sync_at: string | null
  kpis: OverviewKPIs
  trends: DailyMetricPoint[]
  sentiment: SentimentBreakdown
  sla: SLAMetricsSummary
  top_issue_categories: IssueCategorySummary[]
  platform_device: PlatformDeviceBreakdown
  reputation: ReputationVelocity
}

export function InsightsTab({ locationId }: { locationId: number }) {
  const queryClient = useQueryClient()
  const [range, setRange] = useState('30')
  const [syncing, setSyncing] = useState(false)
  const [selectedMetrics, setSelectedMetrics] = useState<Set<TrendMetricKey>>(
    new Set<TrendMetricKey>(['profile_views', 'search_impressions'])
  )

  const {
    data,
    isLoading: loading,
    error: queryError,
  } = useQuery<LocationInsightsResponse>({
    queryKey: ['location-insights', locationId, range],
    queryFn: () => {
      const today = new Date()
      const endStr = today.toISOString().split('T')[0]
      const start = new Date()
      start.setDate(today.getDate() - parseInt(range))
      const startStr = start.toISOString().split('T')[0]

      return api.get<LocationInsightsResponse>(
        `/insights/locations/${locationId}?start_date=${startStr}&end_date=${endStr}`
      )
    },
  })

  const error = queryError ? ((queryError as any).message || 'Failed to load insights.') : ''

  const triggerManualSync = async () => {
    setSyncing(true)
    try {
      const today = new Date()
      const endStr = today.toISOString().split('T')[0]
      const start = new Date()
      start.setDate(today.getDate() - 90) // manual sync defaults to 90 days
      const startStr = start.toISOString().split('T')[0]

      await api.post(`/insights/locations/${locationId}/sync?start_date=${startStr}&end_date=${endStr}`, {})
      toast.success('Synchronization task queued successfully!')
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['location-insights', locationId, range] })
      }, 2000)
    } catch (err: any) {
      toast.error(err.message || 'Failed to queue sync task.')
    } finally {
      setSyncing(false)
    }
  }

  const toggleMetric = (key: TrendMetricKey) => {
    setSelectedMetrics((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        if (next.size > 1) next.delete(key) // keep at least one plotted
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <div className="space-y-6">
      {/* Subheader Filters */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-6">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight text-foreground">Location Analytics</h2>
          {data?.last_insights_sync_at && (
            <p className="text-[11px] font-bold text-muted-foreground mt-1">
              Last synchronized: {new Date(data.last_insights_sync_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex flex-1 items-center gap-2 border border-border/50 rounded-xl px-3 min-h-[44px] py-2 sm:flex-none sm:min-h-0 bg-background/50 backdrop-blur-md shadow-sm">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <select
              value={range}
              onChange={(e) => setRange(e.target.value)}
              className="w-full bg-transparent text-xs font-bold text-foreground outline-none border-none cursor-pointer sm:w-auto"
            >
              <option value="7">Last 7 Days</option>
              <option value="30">Last 30 Days</option>
              <option value="90">Last 90 Days</option>
            </select>
          </div>

          <Button
            size="sm"
            onClick={triggerManualSync}
            disabled={syncing || loading}
            className="min-h-[44px] sm:h-9 sm:min-h-0 text-xs bg-indigo-500 hover:bg-indigo-400 text-white font-bold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all rounded-xl"
          >
            <RefreshCw className={`mr-2 h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
            Sync Metrics
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-xs text-red-400">
          {error}
        </div>
      )}

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <RefreshCw className="h-6 w-6 text-indigo-500 animate-spin" />
        </div>
      ) : data ? (
        <div className="space-y-6">
          {/* Attention Panel */}
          {data.attention_needed && (
            <div className="flex items-start gap-4 rounded-2xl border border-amber-500/30 bg-background/50 backdrop-blur-md shadow-sm p-5 text-amber-500">
              <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-500 shrink-0">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <div>
                <span className="text-sm font-extrabold tracking-tight block mb-1">Needs Attention</span>
                <span className="text-xs font-semibold text-muted-foreground leading-relaxed">
                  {data.attention_reason?.split(' | ').join(' • ')}
                </span>
              </div>
            </div>
          )}

          {/* KPIs */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <KpiCard title="Profile Views" icon={Eye} metric={data.kpis.profile_views} color="indigo" />
            <KpiCard title="Search Impressions" icon={Search} metric={data.kpis.search_impressions} color="sky" />
            <KpiCard title="Maps Views" icon={MapPin} metric={data.kpis.maps_views} color="rose" />
            <KpiCard title="Phone Calls" icon={Phone} metric={data.kpis.phone_calls} color="emerald" />
            <KpiCard title="Website Clicks" icon={Globe} metric={data.kpis.website_clicks} color="purple" />
            <KpiCard title="Directions Requests" icon={Navigation} metric={data.kpis.direction_requests} color="amber" />
            <KpiCard
              title="Avg Rating"
              icon={Star}
              color="gold"
              hideDelta
              metric={{ current: data.reputation.avg_rating ?? 0, prior: 0, percentage_change: null }}
              formatValue={(n) => (n > 0 ? n.toFixed(1) : '—')}
              subtitle="Current Google rating"
            />
            <KpiCard
              title="Reviews / Day"
              icon={Zap}
              color="pink"
              metric={data.reputation.review_velocity_per_day}
              formatValue={(n) => n.toFixed(1)}
              valueSuffix="/day"
            />
          </div>

          {/* Conversion Quality */}
          <ConversionQuality kpis={data.kpis} />

          {/* Daily Trend chart with toggleable metrics + hover tooltip */}
          <div className="glass-panel border-border/40 rounded-2xl p-4 sm:p-6 shadow-sm overflow-hidden">
            <div className="flex flex-col gap-4 mb-6 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h3 className="text-base font-bold text-foreground">Daily Performance Trend</h3>
                <p className="text-xs text-muted-foreground mt-0.5">Toggle metrics to compare · hover for daily values</p>
              </div>
              <TrendLegend selected={selectedMetrics} onToggle={toggleMetric} />
            </div>
            <div className="h-72 w-full flex items-center justify-center">
              {data.trends.length > 0 ? (
                <TrendChart trends={data.trends} selected={selectedMetrics} />
              ) : (
                <span className="text-sm text-muted-foreground">No daily points synced yet.</span>
              )}
            </div>
          </div>

          {/* Search composition */}
          <SearchComposition trends={data.trends} />

          {/* Platform & Device impressions breakdown */}
          {data.platform_device && <PlatformDeviceImpressions data={data.platform_device} />}

          {/* Sentiment / SLA / Themes */}
          <ReputationGrid
            sentiment={data.sentiment}
            sla={data.sla}
            topIssues={data.top_issue_categories}
            scopeLabel="This location"
          />

          {/* Period comparison */}
          <PeriodComparison kpis={data.kpis} />
        </div>
      ) : (
        <div className="h-64 flex items-center justify-center text-xs text-muted-foreground">
          Could not load details.
        </div>
      )}
    </div>
  )
}
