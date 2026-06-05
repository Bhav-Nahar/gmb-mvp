'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import {
  TrendingUp,
  TrendingDown,
  Eye,
  Search,
  MapPin,
  Phone,
  Globe,
  Navigation,
  Calendar,
  AlertTriangle,
  RefreshCw,
  Clock,
  Heart,
  Smile,
  Frown,
  MessageSquare
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'

interface InsightsMetricDelta {
  current: number
  prior: number
  percentage_change: number | null
}

interface OverviewKPIs {
  profile_views: InsightsMetricDelta
  search_impressions: InsightsMetricDelta
  maps_views: InsightsMetricDelta
  phone_calls: InsightsMetricDelta
  website_clicks: InsightsMetricDelta
  direction_requests: InsightsMetricDelta
}

interface DailyMetricPoint {
  date: string
  profile_views: number
  search_impressions: number
  maps_views: number
  phone_calls: number
  website_clicks: number
  direction_requests: number
  searches_direct: number
  searches_indirect: number
  searches_chain: number
  reviews_received: number
  avg_rating: number | null
}

interface SentimentBreakdown {
  positive: number
  neutral: number
  negative: number
  positive_percentage: number
  neutral_percentage: number
  negative_percentage: number
}

interface SLAMetricsSummary {
  total_reviews: number
  replied_reviews: number
  response_rate: number
  avg_response_time_hours: number | null
}

interface IssueCategorySummary {
  category: string
  count: number
}

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

  useEffect(() => {
    fetchLocationInsights()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range])

  const fetchLocationInsights = async () => {
    setLoading(true)
    setError('')
    try {
      let startStr = ''
      const today = new Date()
      const endStr = today.toISOString().split('T')[0]
      
      const start = new Date()
      start.setDate(today.getDate() - parseInt(range))
      startStr = start.toISOString().split('T')[0]

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
      // Refresh after a short delay
      setTimeout(fetchLocationInsights, 2000)
    } catch (err: any) {
      toast.error(err.message || 'Failed to queue sync task.')
    } finally {
      setSyncing(false)
    }
  }

  const KpiCard = ({
    title,
    icon: Icon,
    metric,
    color
  }: {
    title: string
    icon: any
    metric: InsightsMetricDelta
    color: string
  }) => {
    const isPositive = metric.percentage_change !== null && metric.percentage_change > 0
    const isNegative = metric.percentage_change !== null && metric.percentage_change < 0
    
    return (
      <div className="bg-muted/10 border border-border/40 rounded-xl p-5 flex flex-col justify-between relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{title}</span>
          <div className={`p-1.5 rounded-lg bg-muted/40 text-${color}-400`}>
            <Icon className="h-4.5 w-4.5" />
          </div>
        </div>
        <div className="mt-3 flex items-baseline justify-between">
          <span className="text-2xl font-extrabold text-white">
            {metric.current.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            {metric.percentage_change !== null ? (
              <span
                className={`flex items-center text-xs font-extrabold ${
                  isPositive ? 'text-emerald-400' : isNegative ? 'text-rose-400' : 'text-gray-400'
                }`}
              >
                {isPositive ? (
                  <TrendingUp className="h-3 w-3 mr-0.5" />
                ) : (
                  <TrendingDown className="h-3 w-3 mr-0.5" />
                )}
                {Math.abs(metric.percentage_change).toFixed(1)}%
              </span>
            ) : (
              <span className="text-xs text-gray-500">—</span>
            )}
          </div>
        </div>
      </div>
    )
  }

  // Custom SVG Trend Line Chart
  const renderSVGChart = (trends: DailyMetricPoint[]) => {
    if (!trends || trends.length === 0) return null

    const width = 800
    const height = 240
    const paddingLeft = 45
    const paddingRight = 15
    const paddingTop = 15
    const paddingBottom = 30

    const maxVal = Math.max(
      ...trends.map(t => Math.max(t.profile_views, t.search_impressions)),
      10
    )

    const getX = (index: number) => {
      const step = (width - paddingLeft - paddingRight) / (trends.length - 1 || 1)
      return paddingLeft + index * step
    }

    const getY = (val: number) => {
      return height - paddingBottom - (val / maxVal) * (height - paddingTop - paddingBottom)
    }

    let profilePath = ''
    let searchPath = ''
    
    trends.forEach((t, i) => {
      const x = getX(i)
      const yP = getY(t.profile_views)
      const yS = getY(t.search_impressions)
      
      if (i === 0) {
        profilePath = `M ${x} ${yP}`
        searchPath = `M ${x} ${yS}`
      } else {
        profilePath += ` L ${x} ${yP}`
        searchPath += ` L ${x} ${yS}`
      }
    })

    const tickCount = Math.min(trends.length, 6)
    const ticks = []
    for (let i = 0; i < tickCount; i++) {
      const index = Math.round((i * (trends.length - 1)) / (tickCount - 1))
      if (trends[index]) {
        ticks.push(index)
      }
    }

    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full text-muted-foreground">
        {[0, 0.25, 0.5, 0.75, 1].map((p, idx) => {
          const val = Math.round(maxVal * p)
          const y = getY(val)
          return (
            <g key={idx}>
              <line
                x1={paddingLeft}
                y1={y}
                x2={width - paddingRight}
                y2={y}
                stroke="currentColor"
                strokeOpacity={0.06}
                strokeWidth={1}
              />
              <text
                x={paddingLeft - 8}
                y={y + 3}
                className="text-[9px] font-semibold fill-muted-foreground"
                textAnchor="end"
              >
                {val.toLocaleString()}
              </text>
            </g>
          )
        })}

        {ticks.map((idx) => {
          const t = trends[idx]
          const x = getX(idx)
          const d = new Date(t.date)
          const dateLabel = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          return (
            <text
              key={idx}
              x={x}
              y={height - 10}
              className="text-[9px] font-semibold fill-muted-foreground"
              textAnchor="middle"
            >
              {dateLabel}
            </text>
          )
        })}

        <path d={profilePath} fill="none" stroke="#818cf8" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        <path d={searchPath} fill="none" stroke="#38bdf8" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    )
  }

  return (
    <div className="space-y-6">
      {/* Subheader Filters */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-4">
        <div>
          <h2 className="text-lg font-bold text-white">Location Analytics</h2>
          {data?.last_insights_sync_at && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Last synchronized: {new Date(data.last_insights_sync_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 border border-border rounded-lg px-2.5 py-1.5 bg-muted/20">
            <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
            <select
              value={range}
              onChange={(e) => setRange(e.target.value)}
              className="bg-transparent text-xs font-semibold text-white outline-none border-none cursor-pointer"
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
            className="h-8 text-xs bg-indigo-600 border-indigo-500 hover:bg-indigo-700 text-white font-semibold"
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
            <div className="flex items-start gap-3 rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-amber-300">
              <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
              <div>
                <span className="text-sm font-bold block mb-1">Needs Attention</span>
                <span className="text-xs text-amber-200 leading-relaxed">
                  {data.attention_reason?.split(' | ').join(' • ')}
                </span>
              </div>
            </div>
          )}

          {/* KPIs */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
            <KpiCard title="Profile Views" icon={Eye} metric={data.kpis.profile_views} color="indigo" />
            <KpiCard title="Search Impressions" icon={Search} metric={data.kpis.search_impressions} color="sky" />
            <KpiCard title="Maps Views" icon={MapPin} metric={data.kpis.maps_views} color="rose" />
            <KpiCard title="Phone Calls" icon={Phone} metric={data.kpis.phone_calls} color="emerald" />
            <KpiCard title="Website Clicks" icon={Globe} metric={data.kpis.website_clicks} color="purple" />
            <KpiCard title="Directions Requests" icon={Navigation} metric={data.kpis.direction_requests} color="amber" />
          </div>

          {/* Daily Trend SVG */}
          <div className="bg-muted/10 border border-border/40 rounded-xl p-5">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h4 className="text-sm font-bold text-white">Daily Metrics Distribution</h4>
                <p className="text-[10px] text-muted-foreground mt-0.5">Profile views vs search impressions</p>
              </div>
              <div className="flex gap-3 text-[10px] font-bold">
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-indigo-400" />Views</span>
                <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-sky-400" />Search</span>
              </div>
            </div>
            <div className="h-60 w-full flex items-center justify-center">
              {data.trends.length > 0 ? (
                renderSVGChart(data.trends)
              ) : (
                <span className="text-xs text-muted-foreground">No daily points synced yet.</span>
              )}
            </div>
          </div>

          {/* Bottom Row Details Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Sentiment Breakdown */}
            <div className="bg-muted/10 border border-border/40 rounded-xl p-5 flex flex-col justify-between">
              <div>
                <h4 className="text-sm font-bold text-white flex items-center gap-1.5"><Smile className="h-4 w-4 text-emerald-400" />Customer Sentiment</h4>
                <p className="text-[10px] text-muted-foreground mt-0.5">Breakdown of positive vs negative tags</p>
              </div>
              
              <div className="my-4 space-y-3">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-emerald-400 font-semibold flex items-center gap-1"><Smile className="h-3.5 w-3.5" />Positive</span>
                  <span className="text-white font-bold">{data.sentiment.positive_percentage.toFixed(0)}%</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-400 font-semibold flex items-center gap-1"><MessageSquare className="h-3.5 w-3.5" />Neutral</span>
                  <span className="text-white font-bold">{data.sentiment.neutral_percentage.toFixed(0)}%</span>
                </div>
                <div className="flex justify-between items-center text-xs">
                  <span className="text-rose-400 font-semibold flex items-center gap-1"><Frown className="h-3.5 w-3.5" />Negative</span>
                  <span className="text-white font-bold">{data.sentiment.negative_percentage.toFixed(0)}%</span>
                </div>
              </div>

              {/* Stacked bar diagram */}
              <div className="w-full h-2 rounded-full overflow-hidden flex bg-muted/40">
                <div className="bg-emerald-400" style={{ width: `${data.sentiment.positive_percentage}%` }} />
                <div className="bg-gray-400" style={{ width: `${data.sentiment.neutral_percentage}%` }} />
                <div className="bg-rose-400" style={{ width: `${data.sentiment.negative_percentage}%` }} />
              </div>
            </div>

            {/* SLA Summary */}
            <div className="bg-muted/10 border border-border/40 rounded-xl p-5 flex flex-col justify-between">
              <div>
                <h4 className="text-sm font-bold text-white flex items-center gap-1.5"><Clock className="h-4 w-4 text-indigo-400" />SLA Performance</h4>
                <p className="text-[10px] text-muted-foreground mt-0.5">Reviews reply speeds and statuses</p>
              </div>

              <div className="my-4 grid grid-cols-2 gap-4">
                <div className="bg-muted/30 p-3 rounded-lg text-center">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground block">Response Rate</span>
                  <span className="text-lg font-extrabold text-indigo-400 mt-1 block">
                    {data.sla.response_rate.toFixed(0)}%
                  </span>
                </div>
                <div className="bg-muted/30 p-3 rounded-lg text-center">
                  <span className="text-[10px] uppercase font-bold text-muted-foreground block">Avg Reply Time</span>
                  <span className="text-lg font-extrabold text-indigo-400 mt-1 block">
                    {data.sla.avg_response_time_hours !== null 
                      ? `${data.sla.avg_response_time_hours.toFixed(1)}h` 
                      : '—'
                    }
                  </span>
                </div>
              </div>

              <div className="text-[10px] text-muted-foreground text-center">
                Total Reviews: {data.sla.total_reviews} • Replied: {data.sla.replied_reviews}
              </div>
            </div>

            {/* Top Issue Categories */}
            <div className="bg-muted/10 border border-border/40 rounded-xl p-5">
              <h4 className="text-sm font-bold text-white flex items-center gap-1.5"><Heart className="h-4 w-4 text-rose-400" />Customer Themes</h4>
              <p className="text-[10px] text-muted-foreground mt-0.5">Recurring issue categories</p>
              
              <div className="mt-4 space-y-2 max-h-40 overflow-y-auto">
                {data.top_issue_categories.length > 0 ? (
                  data.top_issue_categories.map((item, idx) => (
                    <div key={idx} className="flex justify-between items-center text-xs border-b border-border/20 pb-1.5">
                      <span className="text-muted-foreground font-semibold capitalize">{item.category}</span>
                      <span className="text-white font-bold">{item.count} tags</span>
                    </div>
                  ))
                ) : (
                  <span className="text-xs text-muted-foreground block text-center py-6">No recurring themes found.</span>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="h-64 flex items-center justify-center text-xs text-muted-foreground">
          Could not load details.
        </div>
      )}
    </div>
  )
}
