'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Eye,
  Search,
  MapPin,
  Phone,
  Globe,
  Navigation,
  Calendar,
  AlertTriangle,
  RefreshCw,
  Smile,
  MessageSquare,
  Frown,
  Clock,
  Heart,
  Compass
} from 'lucide-react'
import Link from 'next/link'

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
  click_through_rate: number | null
  call_conversion_rate: number | null
  direction_conversion_rate: number | null
  avg_sentiment_score: number | null
}

interface LeaderboardLocation {
  location_id: number
  location_name: string
  profile_views: number
  search_impressions: number
  reviews_count: number
  avg_rating: number | null
}

interface SentimentBreakdown {
  positive: number
  neutral: number
  negative: number
  positive_percentage: number
  neutral_percentage: number
  negative_percentage: number
  avg_sentiment_score: number | null
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

interface InsightsOverviewData {
  kpis: OverviewKPIs
  trends: DailyMetricPoint[]
  leaderboard: LeaderboardLocation[]
  attention_locations_count: number
  sentiment: SentimentBreakdown | null
  sla: SLAMetricsSummary | null
  top_issue_categories: IssueCategorySummary[]
}

// Static Tailwind classes — dynamic `text-${color}-400` strings get purged in
// production builds, so the KPI icon tints must be spelled out literally here.
const KPI_ICON_CLASSES: Record<string, string> = {
  indigo: 'text-indigo-400',
  sky: 'text-sky-400',
  rose: 'text-rose-400',
  emerald: 'text-emerald-400',
  purple: 'text-purple-400',
  amber: 'text-amber-400',
}

// Plottable daily metrics. `color` is a hex value because it feeds SVG strokes
// (which Tailwind classes can't reach) and the legend swatches.
type TrendMetricKey =
  | 'profile_views'
  | 'search_impressions'
  | 'maps_views'
  | 'phone_calls'
  | 'website_clicks'
  | 'direction_requests'
  | 'reviews_received'

const TREND_METRICS: { key: TrendMetricKey; label: string; color: string }[] = [
  { key: 'profile_views', label: 'Profile Views', color: '#818cf8' },
  { key: 'search_impressions', label: 'Search Impressions', color: '#38bdf8' },
  { key: 'maps_views', label: 'Maps Views', color: '#fb7185' },
  { key: 'phone_calls', label: 'Phone Calls', color: '#34d399' },
  { key: 'website_clicks', label: 'Website Clicks', color: '#c084fc' },
  { key: 'direction_requests', label: 'Directions', color: '#fbbf24' },
  { key: 'reviews_received', label: 'Reviews', color: '#f472b6' },
]

// Multi-metric daily line chart with hover crosshair + tooltip. Pulled out as
// its own component so it can hold hover state.
function TrendChart({
  trends,
  selected,
}: {
  trends: DailyMetricPoint[]
  selected: Set<TrendMetricKey>
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  if (!trends || trends.length === 0) return null

  const width = 800
  const height = 280
  const paddingLeft = 50
  const paddingRight = 20
  const paddingTop = 20
  const paddingBottom = 40

  const activeMetrics = TREND_METRICS.filter((m) => selected.has(m.key))

  const maxVal = Math.max(
    ...trends.flatMap((t) => activeMetrics.map((m) => t[m.key])),
    10
  )

  const getX = (index: number) => {
    const step = (width - paddingLeft - paddingRight) / (trends.length - 1 || 1)
    return paddingLeft + index * step
  }
  const getY = (val: number) =>
    height - paddingBottom - (val / maxVal) * (height - paddingTop - paddingBottom)

  const buildPath = (key: TrendMetricKey) =>
    trends
      .map((t, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(t[key])}`)
      .join(' ')

  // X Axis ticks (show up to 6 labels)
  const tickCount = Math.min(trends.length, 6)
  const ticks: number[] = []
  for (let i = 0; i < tickCount; i++) {
    const index = Math.round((i * (trends.length - 1)) / (tickCount - 1 || 1))
    if (trends[index] !== undefined && !ticks.includes(index)) ticks.push(index)
  }

  const hovered = hoverIdx !== null ? trends[hoverIdx] : null

  return (
    <div className="relative w-full h-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full text-muted-foreground"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {/* Horizontal Grid lines */}
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
                strokeOpacity={0.07}
                strokeWidth={1}
              />
              <text
                x={paddingLeft - 10}
                y={y + 4}
                className="text-[10px] font-medium fill-muted-foreground"
                textAnchor="end"
              >
                {val.toLocaleString()}
              </text>
            </g>
          )
        })}

        {/* X Axis Date Labels */}
        {ticks.map((idx) => {
          const t = trends[idx]
          const x = getX(idx)
          const d = new Date(t.date)
          const dateLabel = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          return (
            <text
              key={idx}
              x={x}
              y={height - 15}
              className="text-[10px] font-medium fill-muted-foreground"
              textAnchor="middle"
            >
              {dateLabel}
            </text>
          )
        })}

        {/* Metric lines */}
        {activeMetrics.map((m) => (
          <path
            key={m.key}
            d={buildPath(m.key)}
            fill="none"
            stroke={m.color}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}

        {/* Hover crosshair + points */}
        {hoverIdx !== null && (
          <g>
            <line
              x1={getX(hoverIdx)}
              y1={paddingTop}
              x2={getX(hoverIdx)}
              y2={height - paddingBottom}
              stroke="currentColor"
              strokeOpacity={0.2}
              strokeWidth={1}
            />
            {activeMetrics.map((m) => (
              <circle
                key={m.key}
                cx={getX(hoverIdx)}
                cy={getY(trends[hoverIdx][m.key])}
                r={3.5}
                fill={m.color}
                stroke="var(--background, #fff)"
                strokeWidth={1.5}
              />
            ))}
          </g>
        )}

        {/* Invisible hover hit-targets per data point */}
        {trends.map((t, i) => {
          const step = (width - paddingLeft - paddingRight) / (trends.length || 1)
          return (
            <rect
              key={i}
              x={getX(i) - step / 2}
              y={paddingTop}
              width={step}
              height={height - paddingTop - paddingBottom}
              fill="transparent"
              onMouseEnter={() => setHoverIdx(i)}
            />
          )
        })}
      </svg>

      {/* Tooltip */}
      {hovered && (
        <div
          className="pointer-events-none absolute top-2 z-10 rounded-lg border border-border bg-background/95 backdrop-blur px-3 py-2 shadow-lg"
          style={{
            left: `${(getX(hoverIdx!) / width) * 100}%`,
            transform:
              getX(hoverIdx!) > width / 2 ? 'translateX(-105%)' : 'translateX(5%)',
          }}
        >
          <div className="text-[11px] font-bold text-foreground mb-1">
            {new Date(hovered.date).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </div>
          <div className="space-y-0.5">
            {activeMetrics.map((m) => (
              <div key={m.key} className="flex items-center gap-2 text-[11px]">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: m.color }}
                />
                <span className="text-muted-foreground">{m.label}</span>
                <span className="ml-auto font-bold text-foreground">
                  {hovered[m.key].toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Sentiment / SLA / Themes cards. Shared by the single-location and
// "All Locations" (organization-wide) reputation views.
function ReputationGrid({
  sentiment,
  sla,
  topIssues,
  scopeLabel,
}: {
  sentiment: SentimentBreakdown
  sla: SLAMetricsSummary
  topIssues: IssueCategorySummary[]
  scopeLabel: string
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Customer Sentiment */}
      <div className="glass-panel p-6 flex flex-col justify-between">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Smile className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            Customer Sentiment
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · positive vs negative tags</p>
        </div>
        <div className="my-4 space-y-3">
          <div className="flex justify-between items-center text-xs">
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1"><Smile className="h-3.5 w-3.5" />Positive</span>
            <span className="text-foreground font-bold">{sentiment.positive_percentage.toFixed(0)}%</span>
          </div>
          <div className="flex justify-between items-center text-xs">
            <span className="text-gray-600 dark:text-gray-400 font-semibold flex items-center gap-1"><MessageSquare className="h-3.5 w-3.5" />Neutral</span>
            <span className="text-foreground font-bold">{sentiment.neutral_percentage.toFixed(0)}%</span>
          </div>
          <div className="flex justify-between items-center text-xs">
            <span className="text-rose-600 dark:text-rose-400 font-semibold flex items-center gap-1"><Frown className="h-3.5 w-3.5" />Negative</span>
            <span className="text-foreground font-bold">{sentiment.negative_percentage.toFixed(0)}%</span>
          </div>
        </div>
        <div className="w-full h-2 rounded-full overflow-hidden flex bg-muted/40">
          <div className="bg-emerald-400" style={{ width: `${sentiment.positive_percentage}%` }} />
          <div className="bg-gray-400" style={{ width: `${sentiment.neutral_percentage}%` }} />
          <div className="bg-rose-400" style={{ width: `${sentiment.negative_percentage}%` }} />
        </div>
        {sentiment.avg_sentiment_score !== null && sentiment.avg_sentiment_score !== undefined && (
          <div className="mt-3 flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground">Sentiment score</span>
            <span className={`font-bold ${sentiment.avg_sentiment_score > 0.1 ? 'text-emerald-600 dark:text-emerald-400' : sentiment.avg_sentiment_score < -0.1 ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'}`}>
              {sentiment.avg_sentiment_score > 0 ? '+' : ''}{sentiment.avg_sentiment_score.toFixed(2)} <span className="text-muted-foreground font-normal">/ 1.0</span>
            </span>
          </div>
        )}
      </div>

      {/* SLA Summary */}
      <div className="glass-panel p-6 flex flex-col justify-between">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            SLA Performance
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · reply speeds and statuses</p>
        </div>
        <div className="my-4 grid grid-cols-2 gap-4">
          <div className="bg-muted/30 p-3 rounded-lg text-center border border-border/30">
            <span className="text-[10px] uppercase font-bold text-muted-foreground block">Response Rate</span>
            <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 block">
              {sla.response_rate.toFixed(0)}%
            </span>
          </div>
          <div className="bg-muted/30 p-3 rounded-lg text-center border border-border/30">
            <span className="text-[10px] uppercase font-bold text-muted-foreground block">Avg Reply Time</span>
            <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 block">
              {sla.avg_response_time_hours !== null ? `${sla.avg_response_time_hours.toFixed(1)}h` : '—'}
            </span>
          </div>
        </div>
        <div className="text-[10px] text-muted-foreground text-center">
          Total Reviews: {sla.total_reviews} • Replied: {sla.replied_reviews}
        </div>
      </div>

      {/* Customer Themes */}
      <div className="glass-panel p-6">
        <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
          <Heart className="h-4 w-4 text-rose-600 dark:text-rose-400" />
          Customer Themes
        </h4>
        <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · recurring issue categories</p>
        <div className="mt-4 space-y-2 max-h-36 overflow-y-auto">
          {topIssues.length > 0 ? (
            topIssues.map((item, idx) => (
              <div key={idx} className="flex justify-between items-center text-xs border-b border-border/20 pb-1.5">
                <span className="text-muted-foreground font-semibold capitalize">{item.category}</span>
                <span className="text-foreground font-bold">{item.count} tags</span>
              </div>
            ))
          ) : (
            <span className="text-xs text-muted-foreground block text-center py-6">No recurring themes found.</span>
          )}
        </div>
      </div>
    </div>
  )
}

export default function InsightsPage() {
  const [range, setRange] = useState('30') // '7', '30', '90', 'custom'
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [lbSort, setLbSort] = useState<{ key: keyof LeaderboardLocation; dir: 'asc' | 'desc' }>({ key: 'profile_views', dir: 'desc' })
  const [selectedMetrics, setSelectedMetrics] = useState<Set<TrendMetricKey>>(
    new Set<TrendMetricKey>(['profile_views', 'search_impressions'])
  )
  const [locations, setLocations] = useState<any[]>([])
  const [selectedLocation, setSelectedLocation] = useState<string>('all')
  const [data, setData] = useState<InsightsOverviewData | null>(null)
  const [locationData, setLocationData] = useState<any | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [syncState, setSyncState] = useState<any>({
    insights_sync_in_progress: false,
    last_insights_sync_status: 'never_synced',
    last_insights_sync_at: null
  })

  useEffect(() => {
    fetchLocations()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    fetchOverviewData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [range, selectedLocation, customStart, customEnd])

  useEffect(() => {
    // Check initial sync status on mount
    fetchSyncStatus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    let interval: NodeJS.Timeout
    if (syncState.insights_sync_in_progress) {
      interval = setInterval(fetchSyncStatus, 5000) // Poll every 5 seconds when active
    }
    return () => {
      if (interval) clearInterval(interval)
    }
  }, [syncState.insights_sync_in_progress])

  const fetchLocations = async () => {
    try {
      const locs = await api.get<any[]>('/locations/')
      setLocations(locs)
    } catch (err: any) {
      console.error('Failed to load locations for filter:', err)
    }
  }

  const fetchSyncStatus = async () => {
    try {
      const statusRes = await api.get<any>('/insights/sync-status')
      setSyncState((prev: any) => {
        // If it was in progress but now finished, reload the data
        if (prev.insights_sync_in_progress && !statusRes.insights_sync_in_progress) {
          fetchOverviewData()
        }
        return statusRes
      })
    } catch (err: any) {
      console.error('Failed to fetch insights sync status:', err)
    }
  }

  const handleSyncNow = async () => {
    setError('')
    setSuccess('')
    try {
      let res: any
      if (selectedLocation === 'all') {
        res = await api.post('/insights/sync-all?force=true&scope=daily')
      } else {
        res = await api.post(`/insights/locations/${selectedLocation}/sync?scope=daily`)
      }
      if (res?.status === 'AlreadyRunning') {
        setSuccess('A sync is already in progress. Data will refresh automatically when complete.')
      } else {
        setSuccess('Synchronization started in the background.')
        // Optimistically mark as syncing; polling will confirm
        setSyncState((prev: any) => ({ ...prev, insights_sync_in_progress: true }))
      }
    } catch (err: any) {
      setError(err.message || 'Failed to trigger synchronization.')
    }
  }



  const fetchOverviewData = async () => {
    let startStr = ''
    let endStr = ''

    if (range === 'custom') {
      // Wait for a complete, valid custom range before hitting the API.
      if (!customStart || !customEnd) return
      if (customStart > customEnd) {
        setError('Start date must be on or before end date.')
        return
      }
      startStr = customStart
      endStr = customEnd
    } else {
      const yesterday = new Date()
      yesterday.setDate(yesterday.getDate() - 1)
      endStr = yesterday.toISOString().split('T')[0]

      const start = new Date()
      start.setDate(yesterday.getDate() - parseInt(range))
      startStr = start.toISOString().split('T')[0]
    }

    setLoading(true)
    setError('')
    try {

      if (selectedLocation === 'all') {
        const res = await api.get<InsightsOverviewData>(
          `/insights/overview?start_date=${startStr}&end_date=${endStr}`
        )
        setData(res)
        setLocationData(null)
      } else {
        const res = await api.get<any>(
          `/insights/locations/${selectedLocation}?start_date=${startStr}&end_date=${endStr}`
        )
        setLocationData(res)
        setData(null)
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load insights overview.')
    } finally {
      setLoading(false)
    }
  }


  // Helper component to render KPI Card
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
    const isFlat = metric.percentage_change === 0
    // prior === 0 with current > 0 yields a null delta from the API — that's new
    // activity, not "no data", so label it as such instead of a bare dash.
    const isNew = metric.percentage_change === null && metric.current > 0 && metric.prior === 0

    return (
      <div className="glass-panel p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-muted-foreground">{title}</span>
          <div className={`p-2 rounded-lg bg-muted/40 ${KPI_ICON_CLASSES[color] ?? 'text-indigo-400'}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
        <div className="mt-4 flex items-baseline justify-between">
          <span className="text-3xl font-extrabold text-foreground">
            {metric.current.toLocaleString()}
          </span>
          <div className="flex items-center gap-1">
            {metric.percentage_change !== null ? (
              <span
                className={`flex items-center text-xs font-bold ${
                  isPositive ? 'text-emerald-600 dark:text-emerald-400' : isNegative ? 'text-rose-600 dark:text-rose-400' : 'text-gray-600 dark:text-gray-400'
                }`}
              >
                {isFlat ? (
                  <Minus className="h-3 w-3 mr-0.5" />
                ) : isPositive ? (
                  <TrendingUp className="h-3 w-3 mr-0.5" />
                ) : (
                  <TrendingDown className="h-3 w-3 mr-0.5" />
                )}
                {Math.abs(metric.percentage_change).toFixed(1)}%
              </span>
            ) : isNew ? (
              <span className="flex items-center text-xs font-bold text-emerald-600 dark:text-emerald-400">
                <TrendingUp className="h-3 w-3 mr-0.5" />
                New
              </span>
            ) : (
              <span className="text-xs text-gray-500">—</span>
            )}
          </div>
        </div>
        <div className="mt-2 text-xs text-muted-foreground">
          vs prior period ({metric.prior.toLocaleString()})
        </div>
      </div>
    )
  }

  // Client-side leaderboard sort (≤10 rows). Clicking a header toggles direction.
  const sortLeaderboard = (rows: LeaderboardLocation[]) => {
    const { key, dir } = lbSort
    const mult = dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const av = a[key] ?? 0
      const bv = b[key] ?? 0
      if (typeof av === 'string' || typeof bv === 'string') {
        return String(av).localeCompare(String(bv)) * mult
      }
      return ((av as number) - (bv as number)) * mult
    })
  }
  const toggleLbSort = (key: keyof LeaderboardLocation) => {
    setLbSort((prev) => prev.key === key ? { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' })
  }
  const LbSortIcon = ({ k }: { k: keyof LeaderboardLocation }) => {
    if (lbSort.key !== k) return <span className="opacity-30">↕</span>
    return <span>{lbSort.dir === 'desc' ? '↓' : '↑'}</span>
  }

  const toggleMetric = (key: TrendMetricKey) => {
    setSelectedMetrics((prev) => {
      const next = new Set(prev)
      if (next.has(key)) {
        // Keep at least one metric plotted.
        if (next.size > 1) next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  return (
    <div className="w-full flex flex-col">
        <main className="flex-1 mx-auto max-w-7xl w-full px-4 py-8 sm:px-6 lg:px-8">
          {/* Header */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-foreground">Performance Insights</h1>
              <div className="flex items-center gap-3 mt-1.5 flex-wrap">
                {syncState.insights_sync_in_progress ? (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-100 dark:bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-200 dark:border-indigo-500/20">
                    <RefreshCw className="h-3 w-3 animate-spin" />
                    Updating insights in background...
                  </span>
                ) : syncState.last_insights_sync_at ? (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/40 text-[11px] font-medium text-muted-foreground">
                    <Clock className="h-3 w-3 mr-0.5" />
                    Last updated: {new Date(syncState.last_insights_sync_at).toLocaleString()}
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-muted/40 text-[11px] font-medium text-muted-foreground">
                    No sync records found
                  </span>
                )}
                {syncState.last_insights_sync_status === 'failed' && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-rose-500/10 text-[11px] font-semibold text-rose-600 dark:text-rose-400 border border-rose-500/20">
                    Sync failed — showing latest cached data
                  </span>
                )}
              </div>
            </div>

            
            <div className="flex items-center gap-3 flex-wrap sm:flex-nowrap">
              {/* Location Dropdown Filter */}
              <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-muted/20">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <select
                  value={selectedLocation}
                  onChange={(e) => setSelectedLocation(e.target.value)}
                  className="bg-transparent text-xs font-semibold text-foreground outline-none border-none cursor-pointer max-w-[200px]"
                >
                  <option value="all" className="bg-background text-foreground">All Locations</option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id.toString()} className="bg-background text-foreground">
                      {loc.location_name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Date Range Selector */}
              <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-muted/20">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <select
                  value={range}
                  onChange={(e) => setRange(e.target.value)}
                  className="bg-transparent text-xs font-semibold text-foreground outline-none border-none cursor-pointer"
                >
                  <option value="7" className="bg-background text-foreground">Last 7 Days</option>
                  <option value="30" className="bg-background text-foreground">Last 30 Days</option>
                  <option value="90" className="bg-background text-foreground">Last 90 Days</option>
                  <option value="custom" className="bg-background text-foreground">Custom Range…</option>
                </select>
              </div>

              {/* Custom date inputs (only when Custom Range is chosen) */}
              {range === 'custom' && (
                <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 bg-muted/20">
                  <input
                    type="date"
                    value={customStart}
                    max={customEnd || undefined}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="bg-transparent text-xs font-semibold text-foreground outline-none border-none cursor-pointer"
                    aria-label="Start date"
                  />
                  <span className="text-xs text-muted-foreground">→</span>
                  <input
                    type="date"
                    value={customEnd}
                    min={customStart || undefined}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="bg-transparent text-xs font-semibold text-foreground outline-none border-none cursor-pointer"
                    aria-label="End date"
                  />
                </div>
              )}
              
              <button
                onClick={fetchOverviewData}
                disabled={loading}
                className="p-2 rounded-lg border border-border bg-muted/20 text-muted-foreground hover:text-foreground transition-colors"
                title="Refresh Metrics"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              </button>

               <button
                onClick={handleSyncNow}
                disabled={syncState.insights_sync_in_progress || loading}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold transition-colors disabled:opacity-50"
                title={selectedLocation === 'all' ? "Sync All Locations from Google" : "Force Sync from Google"}
              >
                {syncState.insights_sync_in_progress ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <TrendingUp className="h-3 w-3" />
                )}
                {selectedLocation === 'all' ? 'Sync All' : 'Sync Now'}
              </button>

            </div>
          </div>

          {/* Success Alert */}
          {success && (
            <div className="mb-6 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-600 dark:text-emerald-400">
              {success}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-400">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex h-96 items-center justify-center">
              <RefreshCw className="h-8 w-8 text-indigo-500 animate-spin" />
            </div>
          ) : (data || locationData) ? (
            (() => {
              const activeData = data || locationData;
              return (
                <div className="space-y-8">
                  {/* Attention banner */}
                  {selectedLocation === 'all' ? (
                    data && data.attention_locations_count > 0 && (
                      <div className="flex items-center gap-3 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/10 p-4 text-amber-600 dark:text-amber-300">
                        <AlertTriangle className="h-5 w-5 flex-shrink-0" />
                        <div className="text-sm font-medium">
                          {data.attention_locations_count} {data.attention_locations_count === 1 ? 'location needs' : 'locations need'} operational attention. Visit individual locations to investigate.
                        </div>
                      </div>
                    )
                  ) : (
                    locationData && locationData.attention_needed && (
                      <div className="flex items-start gap-3 rounded-lg border border-amber-200 dark:border-amber-500/30 bg-amber-100 dark:bg-amber-500/10 p-4 text-amber-600 dark:text-amber-300">
                        <AlertTriangle className="h-5 w-5 flex-shrink-0 mt-0.5" />
                        <div>
                          <span className="text-sm font-bold block mb-1">Needs Attention</span>
                          <span className="text-xs text-amber-700 dark:text-amber-200 leading-relaxed">
                            {locationData.attention_reason?.split(' | ').join(' • ')}
                          </span>
                        </div>
                      </div>
                    )
                  )}

                  {/* Top Row: Metrics Grid */}
                  <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                    <KpiCard title="Profile Views" icon={Eye} metric={activeData.kpis.profile_views} color="indigo" />
                    <KpiCard title="Search Impressions" icon={Search} metric={activeData.kpis.search_impressions} color="sky" />
                    <KpiCard title="Maps Views" icon={MapPin} metric={activeData.kpis.maps_views} color="rose" />
                    <KpiCard title="Phone Calls" icon={Phone} metric={activeData.kpis.phone_calls} color="emerald" />
                    <KpiCard title="Website Clicks" icon={Globe} metric={activeData.kpis.website_clicks} color="purple" />
                    <KpiCard title="Directions Requests" icon={Navigation} metric={activeData.kpis.direction_requests} color="amber" />
                  </div>

                  {/* Conversion Quality — how often a profile view turns into an
                      action. Derived from the KPI totals already loaded. */}
                  {(() => {
                    const pv = activeData.kpis.profile_views.current
                    if (!pv) return null
                    const rate = (n: number) => `${((n / pv) * 100).toFixed(1)}%`
                    const items = [
                      { label: 'Click-through rate', help: 'Website clicks ÷ profile views', value: rate(activeData.kpis.website_clicks.current), icon: Globe },
                      { label: 'Call conversion', help: 'Phone calls ÷ profile views', value: rate(activeData.kpis.phone_calls.current), icon: Phone },
                      { label: 'Directions conversion', help: 'Directions ÷ profile views', value: rate(activeData.kpis.direction_requests.current), icon: Navigation },
                    ]
                    return (
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                        {items.map((it) => (
                          <div key={it.label} className="glass-panel p-4 flex items-center gap-3" title={it.help}>
                            <div className="p-2 rounded-lg bg-muted/40 text-indigo-400">
                              <it.icon className="h-4 w-4" />
                            </div>
                            <div>
                              <div className="text-lg font-extrabold text-foreground leading-none">{it.value}</div>
                              <div className="text-[11px] text-muted-foreground mt-1">{it.label}</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    )
                  })()}

                  {/* Middle Row: Trend Chart */}
                  <div className="glass-panel p-6">
                    <div className="flex flex-col gap-4 mb-6 sm:flex-row sm:items-start sm:justify-between">
                      <div>
                        <h3 className="text-base font-bold text-foreground">Daily Performance Trend</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">Toggle metrics to compare · hover for daily values</p>
                      </div>
                      {/* Clickable legend doubles as a metric toggle */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {TREND_METRICS.map((m) => {
                          const active = selectedMetrics.has(m.key)
                          return (
                            <button
                              key={m.key}
                              onClick={() => toggleMetric(m.key)}
                              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-colors ${
                                active
                                  ? 'border-border bg-muted/40 text-foreground'
                                  : 'border-transparent bg-transparent text-muted-foreground/50 hover:text-muted-foreground'
                              }`}
                              title={active ? `Hide ${m.label}` : `Show ${m.label}`}
                            >
                              <span
                                className="h-2.5 w-2.5 rounded-full"
                                style={{ backgroundColor: active ? m.color : 'currentColor' }}
                              />
                              {m.label}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                    <div className="h-72 w-full flex items-center justify-center">
                      {activeData.trends.length > 0 ? (
                        <TrendChart trends={activeData.trends} selected={selectedMetrics} />
                      ) : (
                        <span className="text-sm text-muted-foreground">No historical records found for this range.</span>
                      )}
                    </div>
                  </div>

                  {/* Search composition — direct vs discovery vs branded/chain.
                      This data ships in every trends point but was never shown. */}
                  {(() => {
                    const direct = activeData.trends.reduce((s: number, t: DailyMetricPoint) => s + (t.searches_direct || 0), 0)
                    const indirect = activeData.trends.reduce((s: number, t: DailyMetricPoint) => s + (t.searches_indirect || 0), 0)
                    const chain = activeData.trends.reduce((s: number, t: DailyMetricPoint) => s + (t.searches_chain || 0), 0)
                    const totalSearches = direct + indirect + chain
                    if (totalSearches === 0) return null
                    const segs = [
                      { label: 'Direct', help: 'Searched your business name or address', value: direct, color: '#818cf8' },
                      { label: 'Discovery', help: 'Searched a category, product, or service', value: indirect, color: '#34d399' },
                      { label: 'Branded', help: 'Searched a related brand or chain', value: chain, color: '#fbbf24' },
                    ]
                    return (
                      <div className="glass-panel p-6">
                        <div className="flex items-center gap-1.5 mb-1">
                          <Compass className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                          <h3 className="text-base font-bold text-foreground">How Customers Found You</h3>
                        </div>
                        <p className="text-xs text-muted-foreground mb-4">Search composition across the selected period</p>
                        <div className="w-full h-3 rounded-full overflow-hidden flex bg-muted/40">
                          {segs.map((s) => (
                            <div
                              key={s.label}
                              style={{ width: `${(s.value / totalSearches) * 100}%`, backgroundColor: s.color }}
                              title={`${s.label}: ${s.value.toLocaleString()} (${((s.value / totalSearches) * 100).toFixed(1)}%)`}
                            />
                          ))}
                        </div>
                        <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
                          {segs.map((s) => (
                            <div key={s.label} className="flex flex-col">
                              <div className="flex items-center gap-1.5">
                                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
                                <span className="text-xs font-semibold text-foreground">{s.label}</span>
                                <span className="text-xs text-muted-foreground ml-auto font-bold">
                                  {((s.value / totalSearches) * 100).toFixed(0)}%
                                </span>
                              </div>
                              <span className="text-[11px] text-muted-foreground mt-0.5">{s.help}</span>
                              <span className="text-[11px] text-muted-foreground/70">{s.value.toLocaleString()} searches</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )
                  })()}

                  {/* Organization-wide reputation snapshot (All Locations) */}
                  {selectedLocation === 'all' && data && data.sentiment && data.sla && (
                    <ReputationGrid
                      sentiment={data.sentiment}
                      sla={data.sla}
                      topIssues={data.top_issue_categories}
                      scopeLabel="Across all locations"
                    />
                  )}

                  {/* Bottom Grid */}
                  {selectedLocation === 'all' && data ? (
                    <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                      {/* Leaderboard */}
                      <div className="glass-panel p-6">
                        <h3 className="text-base font-bold text-foreground mb-4">Locations Leaderboard</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="border-b border-border text-muted-foreground font-semibold">
                                <th className="pb-3"><button onClick={() => toggleLbSort('location_name')} className="inline-flex items-center gap-1 hover:text-foreground">Location <LbSortIcon k="location_name" /></button></th>
                                <th className="pb-3 text-right"><button onClick={() => toggleLbSort('profile_views')} className="inline-flex items-center gap-1 hover:text-foreground ml-auto">Views <LbSortIcon k="profile_views" /></button></th>
                                <th className="pb-3 text-right"><button onClick={() => toggleLbSort('search_impressions')} className="inline-flex items-center gap-1 hover:text-foreground ml-auto">Impressions <LbSortIcon k="search_impressions" /></button></th>
                                <th className="pb-3 text-right"><button onClick={() => toggleLbSort('avg_rating')} className="inline-flex items-center gap-1 hover:text-foreground ml-auto">Rating <LbSortIcon k="avg_rating" /></button></th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/40 font-medium">
                              {data.leaderboard.length > 0 ? (
                                sortLeaderboard(data.leaderboard).map((item, idx) => (
                                  <tr key={idx} className="hover:bg-muted/10 transition-colors">
                                    <td className="py-3 pr-2">
                                      <Link
                                        href={`/dashboard/locations/${item.location_id}`}
                                        className="text-foreground hover:underline hover:text-indigo-600 transition-colors"
                                      >
                                        {item.location_name}
                                      </Link>
                                    </td>
                                    <td className="py-3 text-right text-muted-foreground">
                                      {item.profile_views.toLocaleString()}
                                    </td>
                                    <td className="py-3 text-right text-muted-foreground">
                                      {item.search_impressions.toLocaleString()}
                                    </td>
                                    <td className="py-3 text-right text-muted-foreground">
                                      {item.avg_rating !== null ? (
                                        <span className="text-amber-600 dark:text-amber-400">★ {item.avg_rating.toFixed(1)}</span>
                                      ) : (
                                        '—'
                                      )}
                                    </td>
                                  </tr>
                                ))
                              ) : (
                                <tr>
                                  <td colSpan={4} className="py-4 text-center text-muted-foreground">No locations recorded.</td>
                                </tr>
                              )}
                            </tbody>
                          </table>
                        </div>
                      </div>

                      {/* MoM comparisons */}
                      <div className="glass-panel p-6">
                        <h3 className="text-base font-bold text-foreground mb-4">Period Comparison</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="border-b border-border text-muted-foreground font-semibold">
                                <th className="pb-3">Metric</th>
                                <th className="pb-3 text-right">Current Period</th>
                                <th className="pb-3 text-right">Prior Period</th>
                                <th className="pb-3 text-right">MoM Delta</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/40 font-medium">
                              {[
                                { name: 'Profile Views', current: data.kpis.profile_views.current, prior: data.kpis.profile_views.prior, delta: data.kpis.profile_views.percentage_change },
                                { name: 'Search Impressions', current: data.kpis.search_impressions.current, prior: data.kpis.search_impressions.prior, delta: data.kpis.search_impressions.percentage_change },
                                { name: 'Maps Views', current: data.kpis.maps_views.current, prior: data.kpis.maps_views.prior, delta: data.kpis.maps_views.percentage_change },
                                { name: 'Phone Calls', current: data.kpis.phone_calls.current, prior: data.kpis.phone_calls.prior, delta: data.kpis.phone_calls.percentage_change },
                                { name: 'Website Clicks', current: data.kpis.website_clicks.current, prior: data.kpis.website_clicks.prior, delta: data.kpis.website_clicks.percentage_change },
                                { name: 'Directions Requests', current: data.kpis.direction_requests.current, prior: data.kpis.direction_requests.prior, delta: data.kpis.direction_requests.percentage_change },
                              ].map((row, idx) => {
                                const isPos = row.delta !== null && row.delta > 0
                                const isNeg = row.delta !== null && row.delta < 0
                                return (
                                  <tr key={idx} className="hover:bg-muted/10 transition-colors">
                                    <td className="py-3 text-foreground">{row.name}</td>
                                    <td className="py-3 text-right text-muted-foreground">{row.current.toLocaleString()}</td>
                                    <td className="py-3 text-right text-muted-foreground">{row.prior.toLocaleString()}</td>
                                    <td className={`py-3 text-right font-bold ${isPos ? 'text-emerald-600 dark:text-emerald-400' : isNeg ? 'text-rose-600 dark:text-rose-400' : 'text-gray-600 dark:text-gray-400'}`}>
                                      {row.delta !== null ? `${isPos ? '+' : ''}${row.delta.toFixed(1)}%` : '—'}
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  ) : (locationData ? (
                    <div className="space-y-8">
                      {/* Sentiment, SLA, and Customer Themes side-by-side */}
                      <ReputationGrid
                        sentiment={locationData.sentiment}
                        sla={locationData.sla}
                        topIssues={locationData.top_issue_categories}
                        scopeLabel="This location"
                      />

                      {/* Period Comparison for Single Location */}
                      <div className="glass-panel p-6">
                        <h3 className="text-base font-bold text-foreground mb-4">Period Comparison</h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs border-collapse">
                            <thead>
                              <tr className="border-b border-border text-muted-foreground font-semibold">
                                <th className="pb-3">Metric</th>
                                <th className="pb-3 text-right">Current Period</th>
                                <th className="pb-3 text-right">Prior Period</th>
                                <th className="pb-3 text-right">MoM Delta</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/40 font-medium">
                              {[
                                { name: 'Profile Views', current: locationData.kpis.profile_views.current, prior: locationData.kpis.profile_views.prior, delta: locationData.kpis.profile_views.percentage_change },
                                { name: 'Search Impressions', current: locationData.kpis.search_impressions.current, prior: locationData.kpis.search_impressions.prior, delta: locationData.kpis.search_impressions.percentage_change },
                                { name: 'Maps Views', current: locationData.kpis.maps_views.current, prior: locationData.kpis.maps_views.prior, delta: locationData.kpis.maps_views.percentage_change },
                                { name: 'Phone Calls', current: locationData.kpis.phone_calls.current, prior: locationData.kpis.phone_calls.prior, delta: locationData.kpis.phone_calls.percentage_change },
                                { name: 'Website Clicks', current: locationData.kpis.website_clicks.current, prior: locationData.kpis.website_clicks.prior, delta: locationData.kpis.website_clicks.percentage_change },
                                { name: 'Directions Requests', current: locationData.kpis.direction_requests.current, prior: locationData.kpis.direction_requests.prior, delta: locationData.kpis.direction_requests.percentage_change },
                              ].map((row, idx) => {
                                const isPos = row.delta !== null && row.delta > 0
                                const isNeg = row.delta !== null && row.delta < 0
                                return (
                                  <tr key={idx} className="hover:bg-muted/10 transition-colors">
                                    <td className="py-3 text-foreground">{row.name}</td>
                                    <td className="py-3 text-right text-muted-foreground">{row.current.toLocaleString()}</td>
                                    <td className="py-3 text-right text-muted-foreground">{row.prior.toLocaleString()}</td>
                                    <td className={`py-3 text-right font-bold ${isPos ? 'text-emerald-600 dark:text-emerald-400' : isNeg ? 'text-rose-600 dark:text-rose-400' : 'text-gray-600 dark:text-gray-400'}`}>
                                      {row.delta !== null ? `${isPos ? '+' : ''}${row.delta.toFixed(1)}%` : '—'}
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </div>
                  ) : null)}
                </div>
              )
            })()
          ) : (
            <div className="flex h-96 items-center justify-center">
              <span className="text-muted-foreground">Could not load analytics.</span>
            </div>
          )}
        </main>
      </div>
  )
}
