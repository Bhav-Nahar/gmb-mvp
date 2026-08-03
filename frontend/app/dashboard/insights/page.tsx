'use client'

import { useEffect, useState, Suspense } from 'react'
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
  Compass,
  Trophy,
  Star,
  Zap
} from 'lucide-react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { generateMockInsightsData } from '@/lib/mock-insights'
import { PlatformDeviceImpressions, KpiCard as SharedKpiCard, type PlatformDeviceBreakdown, type ReputationVelocity } from '@/components/insights/InsightsShared'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'
import { InfoHint } from '@/components/ui/InfoHint'
import { METRIC_HELP, helpFor } from '@/lib/metric-help'
import { Skeleton } from '@/components/ui/skeleton'
import { ReportPrintHeader, ExportPdfButton } from '@/components/reports/ReportExport'
import { toDateStr, daysBefore } from '@/lib/utils'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell
} from 'recharts'

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
  platform_device: PlatformDeviceBreakdown
  reputation: ReputationVelocity
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

// Multi-metric daily line chart with area gradients + custom tooltip.
function TrendChart({
  trends,
  selected,
}: {
  trends: DailyMetricPoint[]
  selected: Set<TrendMetricKey>
}) {
  if (!trends || trends.length === 0) return null

  const activeMetrics = TREND_METRICS.filter((m) => selected.has(m.key))

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-lg border border-border bg-background/95 backdrop-blur px-3 py-2 shadow-lg">
          <div className="text-[11px] font-bold text-foreground mb-1">
            {new Date(label).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </div>
          <div className="space-y-0.5">
            {payload.map((entry: any, index: number) => (
              <div key={index} className="flex items-center gap-2 text-[11px]">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                <span className="text-muted-foreground">{entry.name}</span>
                <span className="ml-auto font-bold text-foreground">
                  {entry.value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )
    }
    return null
  }

  // Format date for x-axis
  const formatXAxis = (tickItem: string) => {
    return new Date(tickItem).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  return (
    <div className="w-full h-full relative" style={{ minHeight: '300px' }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={trends}
          margin={{ top: 20, right: 20, left: -20, bottom: 0 }}
        >
          <defs>
            {activeMetrics.map((m) => (
              <linearGradient key={`color-${m.key}`} id={`color-${m.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={m.color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={m.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" strokeOpacity={0.07} />
          <XAxis 
            dataKey="date" 
            tickFormatter={formatXAxis} 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: 'var(--muted-foreground)', fontSize: 10, fontWeight: 500 }}
            dy={10}
            minTickGap={30}
          />
          <YAxis 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: 'var(--muted-foreground)', fontSize: 10, fontWeight: 500 }}
            tickFormatter={(val) => val.toLocaleString()}
          />
          <RechartsTooltip content={<CustomTooltip />} cursor={{ stroke: 'currentColor', strokeOpacity: 0.2, strokeWidth: 1 }} />
          {activeMetrics.map((m) => (
            <Area
              key={m.key}
              type="monotone"
              dataKey={m.key}
              name={m.label}
              stroke={m.color}
              strokeWidth={2.5}
              fillOpacity={1}
              fill={`url(#color-${m.key})`}
              activeDot={{ r: 4, strokeWidth: 1.5, stroke: 'var(--background)' }}
              animationDuration={1500}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
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
  const pieData = [
    { name: 'Positive', value: sentiment.positive_percentage, color: '#34d399' },
    { name: 'Neutral', value: sentiment.neutral_percentage, color: '#9ca3af' },
    { name: 'Negative', value: sentiment.negative_percentage, color: '#fb7185' }
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Customer Sentiment */}
      <div className="glass-panel p-6 flex flex-col justify-between relative overflow-hidden group hover:shadow-lg transition-all duration-300">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Smile className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            Brand Sentiment
            <InfoHint text={METRIC_HELP['Sentiment']} />
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} • Tone analysis</p>
        </div>
        
        <div className="flex flex-col items-center justify-center flex-1 py-4">
          <div className="relative w-40 h-24 overflow-hidden mb-2">
            <ResponsiveContainer width="100%" height="200%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="100%"
                  startAngle={180}
                  endAngle={0}
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                  stroke="none"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute bottom-0 left-0 right-0 text-center flex flex-col">
              <span className="text-2xl font-extrabold text-foreground">
                {sentiment.positive_percentage.toFixed(0)}%
              </span>
              <span className="text-[10px] font-bold text-emerald-500">Positive</span>
            </div>
          </div>
        </div>

        {sentiment.avg_sentiment_score !== null && sentiment.avg_sentiment_score !== undefined && (
          <div className="mt-2 flex items-center justify-between text-xs sm:text-[11px] pt-3 border-t border-border/40">
            <span className="text-muted-foreground">Avg Sentiment</span>
            <span className={`font-bold ${sentiment.avg_sentiment_score > 0.1 ? 'text-emerald-600 dark:text-emerald-400' : sentiment.avg_sentiment_score < -0.1 ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'}`}>
              {sentiment.avg_sentiment_score > 0 ? '+' : ''}{sentiment.avg_sentiment_score.toFixed(2)} <span className="text-muted-foreground font-normal">/ 1.0</span>
            </span>
          </div>
        )}
      </div>

      {/* SLA Summary */}
      <div className="glass-panel p-6 flex flex-col justify-between group hover:shadow-lg transition-all duration-300">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            Response SLA
            <InfoHint text={METRIC_HELP['Response SLA']} />
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} • Engagement speed</p>
        </div>
        
        <div className="my-6 grid grid-cols-2 gap-4">
          <div className="bg-gradient-to-br from-indigo-500/10 to-transparent p-4 rounded-xl text-center border border-indigo-500/20">
            <span className="flex items-center justify-center gap-1 text-[10px] uppercase font-bold text-indigo-600/80 dark:text-indigo-400/80 mb-1">
              Response Rate
              <InfoHint text={METRIC_HELP['Response rate']} />
            </span>
            <span className="text-2xl font-extrabold text-indigo-600 dark:text-indigo-400 flex items-center justify-center gap-1">
              <AnimatedNumber value={sla.response_rate} />%
            </span>
          </div>
          <div className="bg-gradient-to-br from-indigo-500/10 to-transparent p-4 rounded-xl text-center border border-indigo-500/20">
            <span className="text-[10px] uppercase font-bold text-indigo-600/80 dark:text-indigo-400/80 block mb-1">Avg Reply Time</span>
            <span className="text-2xl font-extrabold text-indigo-600 dark:text-indigo-400 flex items-center justify-center gap-1">
              {sla.avg_response_time_hours !== null ? <AnimatedNumber value={sla.avg_response_time_hours} /> : '—'}
              {sla.avg_response_time_hours !== null && <span className="text-sm">h</span>}
            </span>
          </div>
        </div>
        
        <div className="text-[11px] text-muted-foreground flex justify-between items-center pt-3 border-t border-border/40 font-medium">
          <span>Total Reviews: <strong>{sla.total_reviews}</strong></span>
          <span>Replied: <strong>{sla.replied_reviews}</strong></span>
        </div>
      </div>

      {/* Customer Themes */}
      <div className="glass-panel p-6 group hover:shadow-lg transition-all duration-300">
        <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
          <Heart className="h-4 w-4 text-rose-600 dark:text-rose-400" />
          Key Themes
          <InfoHint text={METRIC_HELP['Themes']} />
        </h4>
        <p className="text-[10px] text-muted-foreground mt-0.5 mb-4">{scopeLabel} • Trending topics</p>
        
        <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto pr-2 custom-scrollbar">
          {topIssues.length > 0 ? (
            topIssues.map((item, idx) => (
              <div 
                key={idx} 
                className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/40 border border-border/50 text-xs hover:bg-muted/60 hover:border-border transition-colors cursor-default"
              >
                <span className="font-semibold text-foreground capitalize">{item.category}</span>
                <span className="text-[10px] bg-background px-1.5 py-0.5 rounded text-muted-foreground font-bold">{item.count}</span>
              </div>
            ))
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center py-6 text-muted-foreground">
              <MessageSquare className="h-6 w-6 mb-2 opacity-20" />
              <span className="text-xs">No recurring themes found.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function InsightsContent() {
  const searchParams = useSearchParams()
  const isOnboarding = searchParams?.get('onboarding') === 'true'
  
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
      // Poll every 5 seconds when active; skip while the tab is hidden
      interval = setInterval(() => {
        if (document.visibilityState !== 'hidden') fetchSyncStatus()
      }, 5000)
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
      // Count back from the END date, not from today. The old code did
      // `start.setDate(yesterday.getDate() - range)` — day-OF-MONTH of yesterday
      // applied to a Date still sitting in today's month. On the 1st, yesterday is
      // in the previous month, so e.g. 1 Aug + range 7 produced start = 24 Aug against
      // end = 31 Jul and the API rejected it with "start_date must be on or before
      // end_date"; longer ranges silently returned the wrong window instead.
      const end = daysBefore(new Date(), 1)
      endStr = toDateStr(end)
      startStr = toDateStr(daysBefore(end, parseInt(range)))
    }

    setLoading(true)
    setError('')
    try {

      if (selectedLocation === 'all') {
        let resData: InsightsOverviewData;
        if (isOnboarding) {
          resData = generateMockInsightsData();
        } else {
          resData = await api.get<InsightsOverviewData>(
            `/insights/overview?start_date=${startStr}&end_date=${endStr}`
          );
        }
        setData(resData)
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
      <div className="glass-panel p-6 flex flex-col justify-between relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.12)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.05)] transition-all duration-300 transform hover:-translate-y-1">
        <div className="absolute top-0 right-0 p-10 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
          <Icon className="w-24 h-24" />
        </div>
        <div className="flex items-center justify-between relative z-10">
          <span className="flex items-center gap-1.5 text-sm font-semibold text-muted-foreground">
            {title}
            {helpFor(title) && <InfoHint text={helpFor(title)!} />}
          </span>
          <div className={`p-2 rounded-xl bg-muted/40 shadow-sm border border-border/50 group-hover:scale-110 transition-transform duration-300 ${KPI_ICON_CLASSES[color] ?? 'text-indigo-400'}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
        <div className="mt-4 flex items-baseline justify-between relative z-10">
          <span className="text-3xl font-extrabold text-foreground tracking-tight">
            <AnimatedNumber value={metric.current} />
          </span>
          <div className="flex items-center gap-1">
            {metric.percentage_change !== null ? (
              <span
                className={`flex items-center text-[11px] px-1.5 py-0.5 rounded-full font-bold shadow-sm ${
                  isPositive ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' : 
                  isNegative ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20' : 
                  'bg-gray-500/10 text-gray-600 dark:text-gray-400 border border-gray-500/20'
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
              <span className="flex items-center text-[11px] px-1.5 py-0.5 rounded-full font-bold shadow-sm bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                <TrendingUp className="h-3 w-3 mr-0.5" />
                New
              </span>
            ) : (
              <span className="text-xs text-gray-500 px-1.5">—</span>
            )}
          </div>
        </div>
        <div className="mt-2 text-xs text-muted-foreground relative z-10">
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

  // "All Locations · Last 30 Days" — the scope line under the report title, so a
  // client reading the PDF knows what period and which store it covers.
  const scopeName = selectedLocation === 'all'
    ? 'All Locations'
    : locations.find((l) => l.id.toString() === selectedLocation)?.location_name || 'Location'
  const periodLabel = range === 'custom'
    ? (customStart && customEnd ? `${customStart} → ${customEnd}` : 'Custom range')
    : `Last ${range} Days`
  const reportSubtitle = `${scopeName} · ${periodLabel}`

  return (
    <div className="w-full flex flex-col">
        <main className="report-print flex-1 mx-auto max-w-7xl w-full px-4 py-8 sm:px-6 lg:px-8">
          {/* Masthead for the PDF only — replaces the on-screen header below, which is
              all filters and sync buttons and has no place in a client's report. */}
          <ReportPrintHeader title="Performance Report" subtitle={reportSubtitle} />

          {/* Header */}
          <div className="no-print flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-8">
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">Intelligence Hub</h1>
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

            
            <div className="flex items-center gap-2 sm:gap-3 flex-wrap sm:flex-nowrap">
              {/* Location Dropdown Filter */}
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                  <MapPin className="h-4 w-4 text-indigo-500 group-hover:text-indigo-400 transition-colors" />
                </div>
                <select
                  value={selectedLocation}
                  onChange={(e) => setSelectedLocation(e.target.value)}
                  className="pl-9 pr-8 py-2.5 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl text-xs font-bold text-foreground outline-none cursor-pointer shadow-sm hover:shadow-md hover:border-indigo-500/30 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/50 transition-all appearance-none min-w-[160px] max-w-[200px]"
                >
                  <option value="all" className="bg-background text-foreground font-semibold">All Locations</option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id.toString()} className="bg-background text-foreground">
                      {loc.location_name}
                    </option>
                  ))}
                </select>
                <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
                  <span className="text-[10px] opacity-50">▼</span>
                </div>
              </div>

              {/* Date Range Selector */}
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                  <Calendar className="h-4 w-4 text-emerald-500 group-hover:text-emerald-400 transition-colors" />
                </div>
                <select
                  value={range}
                  onChange={(e) => setRange(e.target.value)}
                  className="pl-9 pr-8 py-2.5 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl text-xs font-bold text-foreground outline-none cursor-pointer shadow-sm hover:shadow-md hover:border-emerald-500/30 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/50 transition-all appearance-none"
                >
                  <option value="7" className="bg-background text-foreground font-semibold">Last 7 Days</option>
                  <option value="30" className="bg-background text-foreground font-semibold">Last 30 Days</option>
                  <option value="90" className="bg-background text-foreground font-semibold">Last 90 Days</option>
                  <option value="custom" className="bg-background text-foreground font-semibold">Custom Range…</option>
                </select>
                <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
                  <span className="text-[10px] opacity-50">▼</span>
                </div>
              </div>

              {/* Custom date inputs */}
              {range === 'custom' && (
                <div className="flex items-center gap-2 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl px-3 py-2 shadow-sm hover:shadow-md transition-all">
                  <input
                    type="date"
                    value={customStart}
                    max={customEnd || undefined}
                    onChange={(e) => setCustomStart(e.target.value)}
                    className="bg-transparent text-xs font-bold text-foreground outline-none border-none cursor-pointer"
                    aria-label="Start date"
                  />
                  <span className="text-xs text-muted-foreground font-bold opacity-50">→</span>
                  <input
                    type="date"
                    value={customEnd}
                    min={customStart || undefined}
                    onChange={(e) => setCustomEnd(e.target.value)}
                    className="bg-transparent text-xs font-bold text-foreground outline-none border-none cursor-pointer"
                    aria-label="End date"
                  />
                </div>
              )}

              <button
                onClick={fetchOverviewData}
                disabled={loading}
                className="h-10 w-10 flex items-center justify-center rounded-xl border border-border/60 bg-background/50 backdrop-blur-md text-muted-foreground hover:text-foreground hover:shadow-md hover:border-border transition-all active:scale-95 disabled:opacity-50 disabled:active:scale-100"
                title="Refresh Metrics"
              >
                <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin text-indigo-500' : ''}`} />
              </button>

               <button
                onClick={handleSyncNow}
                disabled={syncState.insights_sync_in_progress || loading}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white text-xs font-extrabold shadow-[0_4px_14px_0_rgb(79,70,229,0.39)] hover:shadow-[0_6px_20px_rgba(79,70,229,0.23)] hover:-translate-y-0.5 transition-all active:scale-95 disabled:opacity-50 disabled:hover:shadow-[0_4px_14px_0_rgb(79,70,229,0.39)] disabled:hover:-translate-y-0 disabled:active:scale-100"
                title={selectedLocation === 'all' ? "Sync All Locations from Google" : "Force Sync from Google"}
              >
                {syncState.insights_sync_in_progress ? (
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <TrendingUp className="h-3.5 w-3.5" />
                )}
                {selectedLocation === 'all' ? 'Sync All' : 'Sync Now'}
              </button>

              <ExportPdfButton className="h-10 rounded-xl" />

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
            <div className="space-y-8 animate-in fade-in duration-500">
              {/* Skeleton Metrics Grid */}
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i} className="glass-panel p-6 flex flex-col justify-between relative h-36">
                    <div className="flex justify-between items-center mb-4">
                      <Skeleton className="h-4 w-24" />
                      <Skeleton className="h-8 w-8 rounded-xl" />
                    </div>
                    <Skeleton className="h-8 w-16 mb-2" />
                    <Skeleton className="h-3 w-32" />
                  </div>
                ))}
              </div>
              {/* Skeleton Chart */}
              <div className="glass-panel p-6 h-96 flex flex-col">
                <div className="flex justify-between items-center mb-6">
                  <div>
                    <Skeleton className="h-5 w-40 mb-2" />
                    <Skeleton className="h-3 w-64" />
                  </div>
                  <div className="flex gap-2">
                    <Skeleton className="h-8 w-24 rounded-full" />
                    <Skeleton className="h-8 w-24 rounded-full" />
                  </div>
                </div>
                <Skeleton className="flex-1 w-full rounded-xl" />
              </div>
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
                          {data.attention_locations_count} {data.attention_locations_count === 1 ? 'location requires' : 'locations require'} urgent attention. Click through to resolve issues.
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
                    {activeData.reputation && (
                      <>
                        <SharedKpiCard
                          title="Avg Rating"
                          icon={Star}
                          color="gold"
                          hideDelta
                          metric={{ current: activeData.reputation.avg_rating ?? 0, prior: 0, percentage_change: null }}
                          formatValue={(n) => (n > 0 ? n.toFixed(1) : '—')}
                          subtitle={
                            selectedLocation === 'all'
                              ? `Across ${activeData.reputation.rated_location_count} location${activeData.reputation.rated_location_count === 1 ? '' : 's'}`
                              : 'Current Google rating'
                          }
                        />
                        <SharedKpiCard
                          title="Reviews / Day"
                          icon={Zap}
                          color="pink"
                          metric={activeData.reputation.review_velocity_per_day}
                          formatValue={(n) => n.toFixed(1)}
                          valueSuffix="/day"
                        />
                      </>
                    )}
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
                          <div key={it.label} className="glass-panel p-4 flex items-center gap-3">
                            <div className="p-2 rounded-lg bg-muted/40 text-indigo-400">
                              <it.icon className="h-4 w-4" />
                            </div>
                            <div>
                              <div className="text-lg font-extrabold text-foreground leading-none">{it.value}</div>
                              <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground mt-1">
                                {it.label}
                                <InfoHint text={it.help} />
                              </div>
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
                        <h3 className="flex items-center gap-1.5 text-base font-bold text-foreground">
                          Growth Velocity
                          <InfoHint text={METRIC_HELP['Growth Velocity']} />
                        </h3>
                        <p className="text-xs text-muted-foreground mt-0.5">Isolate metrics to uncover trends • Hover to inspect daily data</p>
                      </div>
                      {/* Clickable legend doubles as a metric toggle */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {TREND_METRICS.map((m) => {
                          const active = selectedMetrics.has(m.key)
                          return (
                            <button
                              key={m.key}
                              onClick={() => toggleMetric(m.key)}
                              className={`flex items-center gap-1.5 px-3 py-1.5 sm:px-2.5 sm:py-1 rounded-full text-xs sm:text-[11px] font-semibold border transition-colors ${
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
                          <h3 className="text-base font-bold text-foreground">Traffic Acquisition</h3>
                          <InfoHint text={METRIC_HELP['Traffic Acquisition']} />
                        </div>
                        <p className="text-xs text-muted-foreground mb-4">Breakdown of customer discovery channels</p>
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
                              <span className="text-xs sm:text-[11px] text-muted-foreground mt-0.5">{s.help}</span>
                              <span className="text-xs sm:text-[11px] text-muted-foreground/70">{s.value.toLocaleString()} searches</span>
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

                  {/* Platform & Device impressions breakdown */}
                  {selectedLocation === 'all' && data && data.platform_device && (
                    <PlatformDeviceImpressions data={data.platform_device} />
                  )}

                  {/* Bottom Grid */}
                  {selectedLocation === 'all' && data ? (
                    <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
                      {/* Leaderboard */}
                      <div className="glass-panel p-6 flex flex-col h-full">
                        <div className="flex items-center justify-between mb-6 flex-wrap gap-4">
                          <h3 className="text-base font-bold text-foreground flex items-center gap-2">
                            <Trophy className="h-5 w-5 text-amber-500" />
                            Global Leaderboard
                          </h3>
                          <div className="flex gap-1.5 text-[11px] font-bold bg-muted/40 p-1 rounded-lg border border-border/50">
                            <button onClick={() => toggleLbSort('profile_views')} className={`px-3 py-1.5 rounded-md transition-all ${lbSort.key === 'profile_views' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Views {lbSort.key === 'profile_views' && (lbSort.dir === 'desc' ? '↓' : '↑')}</button>
                            <button onClick={() => toggleLbSort('search_impressions')} className={`px-3 py-1.5 rounded-md transition-all ${lbSort.key === 'search_impressions' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Impressions {lbSort.key === 'search_impressions' && (lbSort.dir === 'desc' ? '↓' : '↑')}</button>
                            <button onClick={() => toggleLbSort('avg_rating')} className={`px-3 py-1.5 rounded-md transition-all ${lbSort.key === 'avg_rating' ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Rating {lbSort.key === 'avg_rating' && (lbSort.dir === 'desc' ? '↓' : '↑')}</button>
                          </div>
                        </div>

                        <div className="space-y-3 flex-grow overflow-y-auto pr-2">
                          {data.leaderboard.length > 0 ? (() => {
                            const sortedLb = sortLeaderboard(data.leaderboard)
                            const maxVal = Math.max(...sortedLb.map(loc => loc[lbSort.key === 'location_name' || lbSort.key === 'avg_rating' ? 'profile_views' : lbSort.key] as number), 1)
                            
                            return sortedLb.map((item, idx) => {
                              const rank = idx + 1
                              const isFirst = rank === 1
                              const isSecond = rank === 2
                              const isThird = rank === 3
                              
                              let rankBadge = (
                                <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs bg-muted text-muted-foreground shrink-0 border border-border/50 shadow-sm">
                                  {rank}
                                </div>
                              )
                              if (isFirst) rankBadge = <div className="w-8 h-8 rounded-full flex items-center justify-center text-lg shadow-[0_0_15px_rgba(251,191,36,0.3)] bg-gradient-to-br from-amber-200 to-amber-500 text-amber-950 shrink-0">🥇</div>
                              if (isSecond) rankBadge = <div className="w-8 h-8 rounded-full flex items-center justify-center text-lg shadow-[0_0_15px_rgba(148,163,184,0.2)] bg-gradient-to-br from-slate-200 to-slate-400 text-slate-900 shrink-0">🥈</div>
                              if (isThird) rankBadge = <div className="w-8 h-8 rounded-full flex items-center justify-center text-lg shadow-[0_0_15px_rgba(251,146,60,0.2)] bg-gradient-to-br from-orange-200 to-orange-500 text-orange-950 shrink-0">🥉</div>

                              const barWidth = `${((item[lbSort.key === 'location_name' || lbSort.key === 'avg_rating' ? 'profile_views' : lbSort.key] as number) / maxVal) * 100}%`

                              return (
                                <Link
                                  key={idx}
                                  href={`/dashboard/locations/${item.location_id}`}
                                  className="group flex items-center justify-between p-3 rounded-xl bg-card border border-border hover:border-primary/40 hover:shadow-md transition-all duration-300 relative overflow-hidden"
                                >
                                  {/* Background Bar */}
                                  <div 
                                    className="absolute inset-y-0 left-0 bg-primary/5 transition-all duration-700 ease-out z-0" 
                                    style={{ width: barWidth }} 
                                  />
                                  
                                  <div className="flex items-center gap-3.5 z-10 min-w-0 flex-grow">
                                    {rankBadge}
                                    <div className="min-w-0">
                                      <h4 className="font-extrabold text-foreground text-sm truncate group-hover:text-primary transition-colors">
                                        {item.location_name}
                                      </h4>
                                      <div className="flex items-center gap-3 mt-1 text-[11px] text-muted-foreground font-semibold">
                                        <span className="flex items-center gap-1" title="Profile Views"><Eye className="w-3 h-3 text-indigo-400" /> {item.profile_views.toLocaleString()}</span>
                                        <span className="flex items-center gap-1" title="Search Impressions"><Search className="w-3 h-3 text-sky-400" /> {item.search_impressions.toLocaleString()}</span>
                                      </div>
                                    </div>
                                  </div>

                                  <div className="z-10 shrink-0 ml-4 flex flex-col items-end justify-center">
                                    {item.avg_rating !== null ? (
                                      <div className={`px-2.5 py-1 rounded-full text-[10px] font-black flex items-center gap-1 ${
                                        item.avg_rating >= 4.5 ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20' : 
                                        item.avg_rating >= 3.5 ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20' : 
                                        'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                                      }`}>
                                        <Star className="w-3 h-3 fill-current drop-shadow-sm" />
                                        {item.avg_rating.toFixed(1)}
                                      </div>
                                    ) : (
                                      <span className="text-[10px] font-bold text-muted-foreground px-2 py-1 bg-muted/40 rounded-full border border-border/50">New</span>
                                    )}
                                    <span className="text-[10px] font-medium text-muted-foreground mt-1.5">{item.reviews_count} reviews</span>
                                  </div>
                                </Link>
                              )
                            })
                          })() : (
                            <div className="py-12 text-center text-muted-foreground text-sm glass-panel rounded-xl">
                              No locations recorded.
                            </div>
                          )}
                        </div>
                      </div>

                      {/* MoM comparisons */}
                      <div className="glass-panel p-6">
                        <h3 className="flex items-center gap-1.5 text-base font-bold text-foreground mb-4">
                          Period Comparison
                          <InfoHint text={METRIC_HELP['Period Comparison']} />
                        </h3>
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

                      {/* Platform & Device impressions breakdown */}
                      {locationData.platform_device && (
                        <PlatformDeviceImpressions data={locationData.platform_device} />
                      )}

                      {/* Period Comparison for Single Location */}
                      <div className="glass-panel p-6">
                        <h3 className="flex items-center gap-1.5 text-base font-bold text-foreground mb-4">
                          Period Comparison
                          <InfoHint text={METRIC_HELP['Period Comparison']} />
                        </h3>
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

export default function InsightsPage() {
  return (
    <Suspense fallback={null}>
      <InsightsContent />
    </Suspense>
  )
}
