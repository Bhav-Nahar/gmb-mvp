'use client'

import { useState, useMemo } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { useComparisonDashboard, ComparisonFilters, GroupRow } from '@/hooks/useComparisonDashboard'
import { BarChart2, Download, Filter, RefreshCw, TrendingUp, TrendingDown, Trophy, AlertTriangle, ArrowUp, ArrowDown } from 'lucide-react'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell } from 'recharts'
import { api } from '@/lib/api'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'
import { InfoHint } from '@/components/ui/InfoHint'
import { METRIC_HELP, helpFor } from '@/lib/metric-help'
import { Skeleton } from '@/components/ui/skeleton'
const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#ec4899', '#84cc16', '#f97316', '#14b8a6', '#a855f7', '#3b82f6']

// metric key -> label. Sum metrics support per-location normalization.
const SUM_METRICS = ['profile_views', 'phone_calls', 'website_clicks', 'direction_requests', 'search_impressions', 'reviews_received'] as const
const RATE_METRICS = ['avg_rating', 'avg_sentiment_score', 'response_rate', 'avg_response_time_hours', 'click_through_rate', 'call_conversion_rate', 'direction_conversion_rate', 'avg_rank', 'solv'] as const
// metrics shown as a percentage (vs hours / score / rank, which are absolute floats)
const PCT_METRICS = ['response_rate', 'click_through_rate', 'call_conversion_rate', 'direction_conversion_rate'] as const
const LABELS: Record<string, string> = {
  profile_views: 'Profile Views', phone_calls: 'Calls', website_clicks: 'Website Clicks',
  direction_requests: 'Directions', search_impressions: 'Impressions', reviews_received: 'Reviews',
  avg_rating: 'Avg Rating', avg_sentiment_score: 'Sentiment', response_rate: 'Response Rate',
  avg_response_time_hours: 'Resp. Time (h)', click_through_rate: 'CTR',
  call_conversion_rate: 'Call Conv.', direction_conversion_rate: 'Dir. Conv.',
  avg_rank: 'Avg Rank', solv: 'SoLV',
  searches_direct: 'Direct', searches_indirect: 'Discovery', searches_chain: 'Branded',
  positive_review_count: 'Positive', neutral_review_count: 'Neutral', negative_review_count: 'Negative',
}
const CHART_METRICS = SUM_METRICS

const fmt = (n: number | null | undefined, rate = false) => {
  if (n === null || n === undefined) return '—'
  if (rate) return `${n.toFixed(1)}%`
  return n >= 1000 ? n.toLocaleString() : `${Math.round(n * 10) / 10}`
}
const pct = (cur: number, prev: number | null | undefined) => {
  if (prev === null || prev === undefined || prev === 0) return null
  return ((cur - prev) / prev) * 100
}

function Delta({ value }: { value: number | null }) {
  if (value === null) return <span className="text-muted-foreground/50 text-xs">—</span>
  const up = value >= 0
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-bold ${up ? 'text-emerald-500' : 'text-red-500'}`}>
      {up ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}{Math.abs(value).toFixed(0)}%
    </span>
  )
}

export default function ComparisonDashboardPage() {
  const { user } = useAuth()
  const orgId = user?.organization_id

  const [filters, setFilters] = useState<ComparisonFilters>({
    group_type: 'CITY',
    start_date: new Date(Date.now() - 30 * 864e5).toISOString().split('T')[0],
    end_date: new Date().toISOString().split('T')[0],
    group_ids: [],
  })
  const [metric, setMetric] = useState<string>('profile_views')
  const [perLocation, setPerLocation] = useState(true)
  const [sortKey, setSortKey] = useState<string>('profile_views')
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [exporting, setExporting] = useState(false)

  const { loading, error, breakdown, series, availableGroups, refresh } = useComparisonDashboard(orgId, filters, metric)

  // value with optional per-location normalization (sum metrics only)
  const val = (row: GroupRow, key: string): number | null => {
    const raw = (row as any)[key]
    if (raw === null || raw === undefined) return null
    if (perLocation && (SUM_METRICS as readonly string[]).includes(key) && row.locations_count > 0) {
      return raw / row.locations_count
    }
    return raw
  }
  const isRate = (key: string) => (RATE_METRICS as readonly string[]).includes(key)
  const isPct = (key: string) => (PCT_METRICS as readonly string[]).includes(key)

  // org averages per metric (mean across groups) for the "vs avg" column
  const orgAvg = useMemo(() => {
    const out: Record<string, number> = {}
    for (const k of [...SUM_METRICS, ...RATE_METRICS]) {
      const vals = breakdown.map(r => val(r, k)).filter((v): v is number => v !== null)
      out[k] = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : 0
    }
    return out
  }, [breakdown, perLocation])

  const sorted = useMemo(() => {
    const rows = [...breakdown]
    rows.sort((a, b) => {
      const av = val(a, sortKey) ?? -Infinity, bv = val(b, sortKey) ?? -Infinity
      return sortDir === 'desc' ? bv - av : av - bv
    })
    return rows
  }, [breakdown, sortKey, sortDir, perLocation])

  // KPI band: org totals + period delta
  const totals = useMemo(() => {
    const sum = (k: string, prev = false) =>
      breakdown.reduce((acc, r) => acc + (((prev ? r.previous[k] : (r as any)[k]) as number) || 0), 0)
    return SUM_METRICS.map(k => ({ key: k, cur: sum(k), delta: pct(sum(k), sum(k, true)) }))
  }, [breakdown])

  // Auto-insights
  const insights = useMemo(() => {
    if (!breakdown.length) return null
    const byMetric = [...breakdown].sort((a, b) => (val(b, metric) ?? 0) - (val(a, metric) ?? 0))
    const top = byMetric[0]
    const improved = [...breakdown]
      .map(r => ({ r, d: pct((r as any)[metric], r.previous[metric]) }))
      .filter(x => x.d !== null)
      .sort((a, b) => (b.d! - a.d!))[0]
    const attention = [...breakdown]
      .filter(r => r.response_rate !== null)
      .sort((a, b) => (a.response_rate! - b.response_rate!))[0]
    return { top, improved, attention }
  }, [breakdown, metric, perLocation])

  // chart: wide format by date
  const chartData = useMemo(() => {
    const dates = Array.from(new Set(series.flatMap(s => s.points.map(p => p.date)))).sort()
    return dates.map(d => {
      const o: any = { date: d }
      series.forEach(s => { o[s.group_name] = s.points.find(p => p.date === d)?.value ?? null })
      return o
    })
  }, [series])

  const setSort = (k: string) => {
    if (sortKey === k) setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
    else { setSortKey(k); setSortDir('desc') }
  }

  const handleExport = async () => {
    if (!orgId) return
    setExporting(true)
    try {
      const p = new URLSearchParams({ group_type: filters.group_type, start_date: filters.start_date, end_date: filters.end_date })
      ;(filters.group_ids || []).forEach(id => p.append('group_ids', id))
      const res = await api.post(`/comparison/export?${p.toString()}`) as any
      // Poll until the worker finishes, then trigger the download.
      for (let i = 0; i < 30; i++) {
        await new Promise(r => setTimeout(r, 1500))
        const st = await api.get<any>(`/comparison/export/${res.export_id}`)
        if (st.status === 'completed') { window.open(st.download_url, '_blank'); return }
        if (st.status === 'failed') { alert('Export failed. Please try again.'); return }
      }
      alert('Export is taking longer than expected — check back shortly.')
    } catch (e) {
      console.error(e)
      alert('Could not start export. Please try again.')
    } finally { setExporting(false) }
  }

  const toggleGroup = (id: string) =>
    setFilters(prev => {
      const cur = prev.group_ids || []
      return { ...prev, group_ids: cur.includes(id) ? cur.filter(g => g !== id) : [...cur, id] }
    })

  if (loading && !breakdown.length) return <div className="p-8 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>
  if (error) return <div className="p-8 text-red-500 text-center font-semibold">{error}</div>

  const noun = filters.group_type.toLowerCase().replace('_', ' ')
  const isGroup = filters.group_type === 'CUSTOM_GROUP'  // only custom groups carry rank/SoLV
  const tableCols = [
    'profile_views', 'phone_calls', 'website_clicks', 'direction_requests',
    'click_through_rate', 'call_conversion_rate', 'avg_rating', 'avg_sentiment_score',
    'response_rate', 'avg_response_time_hours',
    ...(isGroup ? ['avg_rank', 'solv'] : []),
  ]

  const truncated = series.length > 12

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="glass-panel p-4 shadow-xl border border-border/50 text-sm min-w-[200px]">
          <p className="font-bold text-foreground mb-3 pb-2 border-b border-border/50">{label}</p>
          <div className="space-y-2">
            {payload.map((entry: any, index: number) => (
              <div key={index} className="flex items-center justify-between gap-6">
                <span className="flex items-center gap-2 text-muted-foreground font-semibold">
                  <span className="h-2.5 w-2.5 rounded-sm shadow-sm" style={{ backgroundColor: entry.color }} />
                  {entry.name}
                </span>
                <span className="font-bold text-foreground">
                  {typeof entry.value === 'number' && !Number.isInteger(entry.value) ? entry.value.toFixed(1) : entry.value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {loading && breakdown.length > 0 && (
        <div className="fixed top-0 inset-x-0 h-0.5 bg-primary/70 animate-pulse z-50" />
      )}
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3"><BarChart2 className="h-8 w-8 text-primary" /> Comparison</h1>
          <p className="text-muted-foreground mt-1">Compare {noun}s side by side — metrics, trends and what needs attention.</p>
        </div>
        <div className="flex items-center gap-2 self-start">
          <button
            onClick={async () => { const { synced } = await refresh(); if (synced) alert('Sync started — Google data is being pulled in the background. Reload in a minute to see updated numbers.'); }}
            disabled={loading} title="Pull the latest data from Google and recompute"
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white shadow-[0_4px_14px_0_rgb(79,70,229,0.39)] hover:shadow-[0_6px_20px_rgba(79,70,229,0.23)] rounded-xl text-sm font-bold transition-all active:scale-95 disabled:opacity-50 disabled:active:scale-100 disabled:hover:shadow-[0_4px_14px_0_rgb(79,70,229,0.39)]">
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Sync &amp; Refresh
          </button>
          <button onClick={handleExport} disabled={exporting} className="flex items-center gap-2 px-4 py-2 bg-background/50 backdrop-blur-md border border-border/60 text-foreground shadow-sm hover:shadow-md hover:border-border rounded-xl text-sm font-bold transition-all active:scale-95 disabled:opacity-50 disabled:active:scale-100">
            {exporting ? <RefreshCw className="h-4 w-4 animate-spin text-indigo-500" /> : <Download className="h-4 w-4 text-indigo-500" />} Export CSV
          </button>
        </div>
      </div>

      {/* Controls */}
      <div className="glass-panel rounded-xl p-4 flex flex-wrap items-end gap-4 shadow-sm border-border/60">
        <div className="flex flex-col gap-1.5 relative group">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1 ml-1"><Filter className="h-3 w-3 text-indigo-500" /> Group by</label>
          <select className="pl-3 pr-8 py-2 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl text-xs font-bold text-foreground outline-none cursor-pointer shadow-sm hover:shadow-md hover:border-indigo-500/30 focus:border-indigo-500 transition-all appearance-none" value={filters.group_type}
            onChange={e => setFilters(p => ({ ...p, group_type: e.target.value as any, group_ids: [] }))}>
            <option value="CITY" className="bg-background">City</option><option value="STATE" className="bg-background">State</option>
            <option value="REGION" className="bg-background">Region</option>
          </select>
          <div className="absolute inset-y-0 right-0 top-5 flex items-center pr-3 pointer-events-none"><span className="text-[10px] opacity-50">▼</span></div>
        </div>
        <div className="flex flex-col gap-1.5 relative group">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1">Metric</label>
          <select className="pl-3 pr-8 py-2 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl text-xs font-bold text-foreground outline-none cursor-pointer shadow-sm hover:shadow-md hover:border-indigo-500/30 focus:border-indigo-500 transition-all appearance-none" value={metric} onChange={e => { setMetric(e.target.value); setSortKey(e.target.value) }}>
            {CHART_METRICS.map(m => <option key={m} value={m} className="bg-background">{LABELS[m]}</option>)}
          </select>
          <div className="absolute inset-y-0 right-0 top-5 flex items-center pr-3 pointer-events-none"><span className="text-[10px] opacity-50">▼</span></div>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground ml-1">Date range</label>
          <div className="flex items-center gap-2 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl px-2 py-1 shadow-sm hover:shadow-md transition-all">
            <input type="date" value={filters.start_date} max={filters.end_date} onChange={e => setFilters(p => ({ ...p, start_date: e.target.value }))} className="bg-transparent border-none text-xs font-bold text-foreground outline-none cursor-pointer p-1" />
            <span className="text-xs font-bold text-muted-foreground opacity-50">→</span>
            <input type="date" value={filters.end_date} min={filters.start_date} max={new Date().toISOString().split('T')[0]} onChange={e => setFilters(p => ({ ...p, end_date: e.target.value }))} className="bg-transparent border-none text-xs font-bold text-foreground outline-none cursor-pointer p-1" />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm font-bold ml-auto cursor-pointer select-none text-muted-foreground hover:text-foreground transition-colors">
          <input type="checkbox" checked={perLocation} onChange={e => setPerLocation(e.target.checked)} className="h-4 w-4 rounded border-border/60 text-indigo-600 focus:ring-indigo-500/50" />
          Per-location average
        </label>
      </div>

      {/* Compare-specific chips */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground bg-muted/40 px-2 py-1 rounded-md">Filter:</span>
        {availableGroups.length === 0 && <span className="text-sm text-muted-foreground">No {noun}s found.</span>}
        {availableGroups.map(g => {
          const active = (filters.group_ids || []).includes(g.id)
          return <button key={g.id} onClick={() => toggleGroup(g.id)}
            className={`text-xs px-3 py-1.5 rounded-full border transition-all shadow-sm hover:shadow-md ${active ? 'bg-indigo-600 text-white border-indigo-600 font-bold scale-105' : 'bg-background/50 backdrop-blur-md text-foreground border-border/60 hover:border-indigo-500/50 font-semibold hover:-translate-y-0.5'}`}>{g.name}</button>
        })}
      </div>

      {/* KPI band */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        {totals.map(t => (
          <div key={t.key} className="glass-panel border border-border/60 rounded-xl p-5 relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.12)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.05)] transition-all duration-300 transform hover:-translate-y-1">
            <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-muted-foreground relative z-10">
              {LABELS[t.key]}
              {helpFor(LABELS[t.key]) && <InfoHint text={helpFor(LABELS[t.key])!} />}
            </p>
            <p className="text-2xl font-extrabold mt-1 tracking-tight text-foreground relative z-10">
              {isPct(t.key) || isRate(t.key) ? fmt(t.cur, isPct(t.key)) : <AnimatedNumber value={t.cur} />}
            </p>
            <div className="mt-1.5 relative z-10"><Delta value={t.delta} /></div>
          </div>
        ))}
      </div>

      {/* Insight callouts */}
      {insights && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="glass-panel border-emerald-500/30 rounded-xl p-5 relative overflow-hidden group hover:-translate-y-1 hover:shadow-lg transition-all duration-300">
            <Trophy className="absolute -right-4 -bottom-4 h-24 w-24 text-emerald-500/10 group-hover:scale-110 group-hover:text-emerald-500/20 transition-all duration-500" />
            <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-600 flex items-center gap-1.5 relative z-10"><Trophy className="h-3.5 w-3.5" /> Top performer</p>
            <p className="text-xl font-extrabold mt-1 text-foreground relative z-10">{insights.top.group_name}</p>
            <p className="text-sm font-semibold text-muted-foreground relative z-10">{fmt(val(insights.top, metric), isPct(metric))} {LABELS[metric]}{perLocation && !isRate(metric) ? ' / location' : ''}</p>
          </div>
          <div className="glass-panel border-indigo-500/30 rounded-xl p-5 relative overflow-hidden group hover:-translate-y-1 hover:shadow-lg transition-all duration-300">
            <TrendingUp className="absolute -right-4 -bottom-4 h-24 w-24 text-indigo-500/10 group-hover:scale-110 group-hover:text-indigo-500/20 transition-all duration-500" />
            <p className="text-[10px] font-bold uppercase tracking-wider text-indigo-600 flex items-center gap-1.5 relative z-10"><TrendingUp className="h-3.5 w-3.5" /> Most improved</p>
            {insights.improved ? <>
              <p className="text-xl font-extrabold mt-1 text-foreground relative z-10">{insights.improved.r.group_name}</p>
              <p className="text-sm font-semibold text-muted-foreground flex items-center gap-1 relative z-10"><Delta value={insights.improved.d} /> {LABELS[metric]} vs prev period</p>
            </> : <p className="text-sm font-semibold text-muted-foreground mt-1 relative z-10">No prior-period data</p>}
          </div>
          <div className="glass-panel border-amber-500/30 rounded-xl p-5 relative overflow-hidden group hover:-translate-y-1 hover:shadow-lg transition-all duration-300">
            <AlertTriangle className="absolute -right-4 -bottom-4 h-24 w-24 text-amber-500/10 group-hover:scale-110 group-hover:text-amber-500/20 transition-all duration-500" />
            <p className="text-[10px] font-bold uppercase tracking-wider text-amber-600 flex items-center gap-1.5 relative z-10"><AlertTriangle className="h-3.5 w-3.5" /> Needs attention</p>
            {insights.attention ? <>
              <p className="text-xl font-extrabold mt-1 text-foreground relative z-10">{insights.attention.group_name}</p>
              <p className="text-sm font-semibold text-muted-foreground relative z-10">Lowest response rate: {fmt(insights.attention.response_rate, true)}</p>
            </> : <p className="text-sm font-semibold text-muted-foreground mt-1 relative z-10">No review data</p>}
          </div>
        </div>
      )}

      {/* Ranking bar chart — current-period totals per group (no extra backend call) */}
      <div className="space-y-3">
        <h3 className="text-lg font-extrabold flex items-center gap-2">
          <BarChart2 className="h-5 w-5 text-indigo-500" /> {LABELS[metric]} by {noun}
          {helpFor(LABELS[metric]) && <InfoHint text={helpFor(LABELS[metric])!} />}
        </h3>
        <div className="h-[360px] glass-panel border-border/60 shadow-sm rounded-xl p-5">
          {sorted.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sorted.slice(0, 15).map(r => ({ name: r.group_name, value: val(r, metric) ?? 0 }))} layout="vertical" margin={{ left: 12, right: 24 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="currentColor" className="text-border/40" />
                <XAxis type="number" tick={{ fontSize: 11 }} className="text-muted-foreground" axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="name" width={110} tick={{ fontSize: 11 }} className="text-muted-foreground" axisLine={false} tickLine={false} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                <Bar dataKey="value" radius={[0, 4, 4, 0]} animationDuration={1000}>
                  {sorted.slice(0, 15).map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <div className="h-full flex items-center justify-center text-muted-foreground text-sm font-semibold">No data for this selection</div>}
        </div>
      </div>

      {/* Multi-series trend */}
      <div className="space-y-3">
        <h3 className="text-lg font-extrabold flex items-center gap-2"><TrendingUp className="h-5 w-5 text-indigo-500" /> {LABELS[metric]} over time
          {helpFor(LABELS[metric]) && <InfoHint text={helpFor(LABELS[metric])!} />}
          {truncated && <span className="text-xs font-semibold text-amber-600">· showing top 12 of {series.length} {noun}s</span>}</h3>
        <div className="h-[380px] glass-panel border-border/60 shadow-sm rounded-xl p-5">
          {chartData.length > 0 && series.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" className="text-border/40" />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} className="text-muted-foreground" axisLine={false} tickLine={false} dy={10} />
                <YAxis tick={{ fontSize: 11 }} className="text-muted-foreground" axisLine={false} tickLine={false} dx={-10} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: 12, fontWeight: 600, paddingTop: '10px' }} iconType="circle" />
                {series.slice(0, 12).map((s, i) => (
                  <Line key={s.group_name} type="monotone" dataKey={s.group_name} stroke={COLORS[i % COLORS.length]} strokeWidth={3} dot={{ r: 3, strokeWidth: 2 }} activeDot={{ r: 6 }} animationDuration={1000} connectNulls />
                ))}
              </LineChart>
            </ResponsiveContainer>
          ) : <div className="h-full flex items-center justify-center text-muted-foreground text-sm font-semibold">No trend data for this selection</div>}
        </div>
      </div>

      {/* Sentiment + search-intent breakdowns (from already-loaded data) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-3">
          <h3 className="text-base font-extrabold flex items-center gap-2">Review sentiment by {noun}</h3>
          <div className="h-[320px] glass-panel border-border/60 shadow-sm rounded-xl p-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sorted.slice(0, 12).map(r => ({ name: r.group_name, Positive: r.positive_review_count || 0, Neutral: r.neutral_review_count || 0, Negative: r.negative_review_count || 0 }))}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" className="text-border/40" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} className="text-muted-foreground" interval={0} angle={-25} textAnchor="end" height={60} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} className="text-muted-foreground" axisLine={false} tickLine={false} dx={-10} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                <Legend wrapperStyle={{ fontSize: 11, fontWeight: 600 }} iconType="circle" />
                <Bar dataKey="Positive" stackId="s" fill="#10b981" animationDuration={1000} radius={[0, 0, 4, 4]} />
                <Bar dataKey="Neutral" stackId="s" fill="#94a3b8" animationDuration={1000} />
                <Bar dataKey="Negative" stackId="s" fill="#ef4444" animationDuration={1000} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="space-y-3">
          <h3 className="text-base font-extrabold flex items-center gap-2">Search intent by {noun}</h3>
          <div className="h-[320px] glass-panel border-border/60 shadow-sm rounded-xl p-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sorted.slice(0, 12).map(r => ({ name: r.group_name, Branded: r.searches_chain || 0, Direct: r.searches_direct || 0, Discovery: r.searches_indirect || 0 }))}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" className="text-border/40" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} className="text-muted-foreground" interval={0} angle={-25} textAnchor="end" height={60} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11 }} className="text-muted-foreground" axisLine={false} tickLine={false} dx={-10} />
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                <Legend wrapperStyle={{ fontSize: 11, fontWeight: 600 }} iconType="circle" />
                <Bar dataKey="Direct" stackId="q" fill="#6366f1" animationDuration={1000} radius={[0, 0, 4, 4]} />
                <Bar dataKey="Discovery" stackId="q" fill="#06b6d4" animationDuration={1000} />
                <Bar dataKey="Branded" stackId="q" fill="#f59e0b" animationDuration={1000} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Comparison table */}
      <div className="space-y-3">
        <h3 className="text-lg font-extrabold flex items-center gap-2"><BarChart2 className="h-5 w-5 text-indigo-500" /> {noun.charAt(0).toUpperCase() + noun.slice(1)} breakdown</h3>
        <div className="glass-panel border-border/60 shadow-sm rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 border-b border-border/60">
              <tr>
                <th className="px-4 py-4 text-left font-bold text-muted-foreground">{noun}</th>
                <th className="px-3 py-4 text-right font-bold text-muted-foreground">
                  <span className="flex items-center justify-end gap-1.5">Locs<InfoHint text={METRIC_HELP['Locs']} /></span>
                </th>
                {tableCols.map(c => (
                  <th key={c} onClick={() => setSort(c)} className={`px-3 py-4 text-right font-bold cursor-pointer select-none whitespace-nowrap transition-colors hover:text-indigo-500 ${sortKey === c ? 'text-indigo-600' : 'text-muted-foreground'}`}>
                    <span className="inline-flex items-center gap-1.5">
                      {LABELS[c]}{sortKey === c ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
                      {helpFor(LABELS[c]) && <InfoHint text={helpFor(LABELS[c])!} />}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {loading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="animate-pulse">
                    <td className="px-4 py-4"><Skeleton className="h-4 w-32" /></td>
                    <td className="px-3 py-4"><Skeleton className="h-4 w-8 ml-auto" /></td>
                    {tableCols.map(c => (
                      <td key={c} className="px-3 py-4"><Skeleton className="h-4 w-12 ml-auto" /></td>
                    ))}
                  </tr>
                ))
              ) : sorted.length === 0 ? (
                <tr><td colSpan={tableCols.length + 2} className="px-4 py-12 text-center text-muted-foreground font-semibold">No data for this selection.</td></tr>
              ) : (
                sorted.map(row => (
                  <tr key={row.group_id} className="hover:bg-muted/30 transition-colors group">
                    <td className="px-4 py-3.5 font-bold text-foreground group-hover:text-indigo-600 transition-colors">{row.group_name}</td>
                    <td className="px-3 py-3.5 text-right font-semibold text-muted-foreground">{row.locations_count}</td>
                    {tableCols.map(c => {
                      const v = val(row, c)
                      const avg = orgAvg[c]
                      const vsAvg = (v !== null && avg) ? ((v - avg) / avg) * 100 : null
                      const rate = isPct(c)
                      return (
                        <td key={c} className="px-3 py-3.5 text-right whitespace-nowrap">
                          <span className="font-bold text-foreground">{fmt(v, rate)}</span>
                          {vsAvg !== null && Math.abs(vsAvg) >= 1 && (
                            <span className={`ml-2 text-[10px] font-extrabold px-1.5 py-0.5 rounded-md ${vsAvg >= 0 ? 'bg-emerald-500/10 text-emerald-600' : 'bg-red-500/10 text-red-600'}`}>
                              {vsAvg >= 0 ? '+' : ''}{vsAvg.toFixed(0)}%
                            </span>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-muted-foreground">% values in the table are vs the {noun} average. {perLocation ? 'Volume metrics shown per location.' : 'Showing raw totals.'}</p>
      </div>
    </div>
  )
}
