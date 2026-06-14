'use client'

import { useEffect, useState } from 'react'
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
  type OverviewKPIs,
  type DailyMetricPoint,
  type SentimentBreakdown,
  type SLAMetricsSummary,
  type IssueCategorySummary,
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
}

export function InsightsTab({ locationId }: { locationId: number }) {
  const [range, setRange] = useState('30')
  const [data, setData] = useState<LocationInsightsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [selectedMetrics, setSelectedMetrics] = useState<Set<TrendMetricKey>>(
    new Set<TrendMetricKey>(['profile_views', 'search_impressions'])
  )

  useEffect(() => {
    fetchLocationInsights()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range])

  const fetchLocationInsights = async () => {
    setLoading(true)
    setError('')
    try {
      const today = new Date()
      const endStr = today.toISOString().split('T')[0]
      const start = new Date()
      start.setDate(today.getDate() - parseInt(range))
      const startStr = start.toISOString().split('T')[0]

      const res = await api.get<LocationInsightsResponse>(
        `/insights/locations/${locationId}?start_date=${startStr}&end_date=${endStr}`
      )
      setData(res)
    } catch (err: any) {
      setError(err.message || 'Failed to load insights.')
    } finally {
      setLoading(false)
    }
  }

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
      setTimeout(fetchLocationInsights, 2000)
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
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-4">
        <div>
          <h2 className="text-lg font-bold text-foreground">Location Analytics</h2>
          {data?.last_insights_sync_at && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Last synchronized: {new Date(data.last_insights_sync_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex flex-1 items-center gap-2 border border-border rounded-lg px-2.5 min-h-[44px] py-1.5 sm:flex-none sm:min-h-0 bg-muted/20">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={range}
              onChange={(e) => setRange(e.target.value)}
              className="w-full bg-transparent text-xs font-semibold text-foreground outline-none border-none cursor-pointer sm:w-auto"
            >
              <option value="7">Last 7 Days</option>
              <option value="30">Last 30 Days</option>
              <option value="90">Last 90 Days</option>
            </select>
          </div>

          <Button
            size="sm"
            variant="outline"
            onClick={triggerManualSync}
            disabled={syncing || loading}
            className="min-h-[44px] sm:h-8 sm:min-h-0 text-xs bg-indigo-600 border-indigo-500 hover:bg-indigo-700 text-white font-semibold"
          >
            <RefreshCw className={`mr-1.5 h-3 w-3 ${syncing ? 'animate-spin' : ''}`} />
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
            <div className="flex items-start gap-3 rounded-xl border border-amber-200 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/10 p-4 text-amber-600 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <div>
                <span className="text-sm font-bold block mb-1">Needs Attention</span>
                <span className="text-xs text-amber-700 dark:text-amber-200 leading-relaxed">
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
          </div>

          {/* Conversion Quality */}
          <ConversionQuality kpis={data.kpis} />

          {/* Daily Trend chart with toggleable metrics + hover tooltip */}
          <div className="glass-panel p-4 sm:p-6">
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
