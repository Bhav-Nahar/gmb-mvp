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
  Smile,
  MessageSquare,
  Frown,
  Clock,
  Heart
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
}

interface LeaderboardLocation {
  location_id: number
  location_name: string
  profile_views: number
  search_impressions: number
  reviews_count: number
  avg_rating: number | null
}

interface InsightsOverviewData {
  kpis: OverviewKPIs
  trends: DailyMetricPoint[]
  leaderboard: LeaderboardLocation[]
  attention_locations_count: number
}

export default function InsightsPage() {
  const [range, setRange] = useState('30') // '7', '30', '90'
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
  }, [range, selectedLocation])

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
        res = await api.post('/insights/sync-all?force=true')
      } else {
        res = await api.post(`/insights/locations/${selectedLocation}/sync`)
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
    setLoading(true)
    setError('')
    try {
      let startStr = ''
      const yesterday = new Date()
      yesterday.setDate(yesterday.getDate() - 1)
      const endStr = yesterday.toISOString().split('T')[0]
      
      const start = new Date()
      start.setDate(yesterday.getDate() - parseInt(range))
      startStr = start.toISOString().split('T')[0]

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
    
    return (
      <div className="glass-panel p-6 flex flex-col justify-between relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-sm font-semibold text-muted-foreground">{title}</span>
          <div className={`p-2 rounded-lg bg-muted/40 text-${color}-400`}>
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
        <div className="mt-2 text-xs text-muted-foreground">
          vs prior period ({metric.prior.toLocaleString()})
        </div>
      </div>
    )
  }

  // Interactive SVG graph constructor
  const renderSVGChart = (trends: DailyMetricPoint[]) => {
    if (!trends || trends.length === 0) return null

    const width = 800
    const height = 280
    const paddingLeft = 50
    const paddingRight = 20
    const paddingTop = 20
    const paddingBottom = 40

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

    // Paths
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

    // X Axis ticks (show up to 6 labels)
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
                className="text-[10px] text-right font-medium fill-muted-foreground"
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

        {/* Lines */}
        <path
          d={profilePath}
          fill="none"
          stroke="url(#profile-gradient)"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d={searchPath}
          fill="none"
          stroke="url(#search-gradient)"
          strokeWidth={3}
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Gradients */}
        <defs>
          <linearGradient id="profile-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#818cf8" />
            <stop offset="100%" stopColor="#c084fc" />
          </linearGradient>
          <linearGradient id="search-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>
      </svg>
    )
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
                </select>
              </div>
              
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

                  {/* Middle Row: Trend Chart */}
                  <div className="glass-panel p-6">
                    <div className="flex items-center justify-between mb-6">
                      <div>
                        <h3 className="text-base font-bold text-foreground">Views vs. Search Impressions</h3>
                        <p className="text-xs text-muted-foreground mt-0.5">Daily time-series distribution</p>
                      </div>
                      <div className="flex items-center gap-4 text-xs font-semibold">
                        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-indigo-400" />Profile Views</span>
                        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-sky-400" />Search Impressions</span>
                      </div>
                    </div>
                    <div className="h-72 w-full flex items-center justify-center">
                      {activeData.trends.length > 0 ? (
                        renderSVGChart(activeData.trends)
                      ) : (
                        <span className="text-sm text-muted-foreground">No historical records found for this range.</span>
                      )}
                    </div>
                  </div>

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
                                <th className="pb-3">Location</th>
                                <th className="pb-3 text-right">Views</th>
                                <th className="pb-3 text-right">Impressions</th>
                                <th className="pb-3 text-right">Rating</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border/40 font-medium">
                              {data.leaderboard.length > 0 ? (
                                data.leaderboard.map((item, idx) => (
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
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        {/* Customer Sentiment */}
                        <div className="glass-panel p-6 flex flex-col justify-between">
                          <div>
                            <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                              <Smile className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                              Customer Sentiment
                            </h4>
                            <p className="text-[10px] text-muted-foreground mt-0.5">Breakdown of positive vs negative tags</p>
                          </div>
                          
                          <div className="my-4 space-y-3">
                            <div className="flex justify-between items-center text-xs">
                              <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1"><Smile className="h-3.5 w-3.5" />Positive</span>
                              <span className="text-foreground font-bold">{locationData.sentiment.positive_percentage.toFixed(0)}%</span>
                            </div>
                            <div className="flex justify-between items-center text-xs">
                              <span className="text-gray-600 dark:text-gray-400 font-semibold flex items-center gap-1"><MessageSquare className="h-3.5 w-3.5" />Neutral</span>
                              <span className="text-foreground font-bold">{locationData.sentiment.neutral_percentage.toFixed(0)}%</span>
                            </div>
                            <div className="flex justify-between items-center text-xs">
                              <span className="text-rose-600 dark:text-rose-400 font-semibold flex items-center gap-1"><Frown className="h-3.5 w-3.5" />Negative</span>
                              <span className="text-foreground font-bold">{locationData.sentiment.negative_percentage.toFixed(0)}%</span>
                            </div>
                          </div>

                          <div className="w-full h-2 rounded-full overflow-hidden flex bg-muted/40">
                            <div className="bg-emerald-400" style={{ width: `${locationData.sentiment.positive_percentage}%` }} />
                            <div className="bg-gray-400" style={{ width: `${locationData.sentiment.neutral_percentage}%` }} />
                            <div className="bg-rose-400" style={{ width: `${locationData.sentiment.negative_percentage}%` }} />
                          </div>
                        </div>

                        {/* SLA Summary */}
                        <div className="glass-panel p-6 flex flex-col justify-between">
                          <div>
                            <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                              <Clock className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
                              SLA Performance
                            </h4>
                            <p className="text-[10px] text-muted-foreground mt-0.5">Reviews reply speeds and statuses</p>
                          </div>

                          <div className="my-4 grid grid-cols-2 gap-4">
                            <div className="bg-muted/30 p-3 rounded-lg text-center border border-border/30">
                              <span className="text-[10px] uppercase font-bold text-muted-foreground block">Response Rate</span>
                              <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 block">
                                {locationData.sla.response_rate.toFixed(0)}%
                              </span>
                            </div>
                            <div className="bg-muted/30 p-3 rounded-lg text-center border border-border/30">
                              <span className="text-[10px] uppercase font-bold text-muted-foreground block">Avg Reply Time</span>
                              <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 block">
                                {locationData.sla.avg_response_time_hours !== null 
                                  ? `${locationData.sla.avg_response_time_hours.toFixed(1)}h` 
                                  : '—'
                                }
                              </span>
                            </div>
                          </div>

                          <div className="text-[10px] text-muted-foreground text-center">
                            Total Reviews: {locationData.sla.total_reviews} • Replied: {locationData.sla.replied_reviews}
                          </div>
                        </div>

                        {/* Customer Themes */}
                        <div className="glass-panel p-6">
                          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
                            <Heart className="h-4 w-4 text-rose-600 dark:text-rose-400" />
                            Customer Themes
                          </h4>
                          <p className="text-[10px] text-muted-foreground mt-0.5">Recurring issue categories</p>
                          
                          <div className="mt-4 space-y-2 max-h-36 overflow-y-auto">
                            {locationData.top_issue_categories.length > 0 ? (
                              locationData.top_issue_categories.map((item: any, idx: number) => (
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
