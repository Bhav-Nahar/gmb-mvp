'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Search, Download, Plus, Trash2, BarChart2, AlertCircle, RefreshCw,
  TrendingUp, TrendingDown, Info, Calendar, ChevronUp, ChevronDown, ChevronsUpDown
} from 'lucide-react'
import { format, startOfMonth, subMonths } from 'date-fns'
import { toast } from 'sonner'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'
import { InfoHint } from '@/components/ui/InfoHint'
import { METRIC_HELP } from '@/lib/metric-help'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

const RANGE_OPTIONS = [
  { label: 'Last 1 Month', value: 1 },
  { label: 'Last 3 Months', value: 3 },
  { label: 'Last 6 Months', value: 6 },
  { label: 'Last 12 Months', value: 12 },
]
const PAGE_SIZE = 50

// Per-location Search Intelligence — same keyword endpoints as the org-wide
// page (which already accept &location_id=), scoped to a single storefront.
export function SearchIntelligenceTab({ locationId }: { locationId: number }) {
  const [months, setMonths] = useState(3)
  const [isBrandFilter, setIsBrandFilter] = useState<boolean | null>(null)
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState('impressions_desc')
  const [page, setPage] = useState(1)

  const [summary, setSummary] = useState<any | null>(null)
  const [keywords, setKeywords] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [brandTerms, setBrandTerms] = useState<any[]>([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [newBrandTerm, setNewBrandTerm] = useState('')
  const [syncState, setSyncState] = useState<any>({ insights_sync_in_progress: false, last_insights_sync_at: null })

  // Month window: end = last complete month, start = end - (months-1).
  const periodParams = useCallback(() => {
    const end = startOfMonth(subMonths(new Date(), 1))
    const start = subMonths(end, months - 1)
    return `start_period=${format(start, 'yyyy-MM-dd')}&end_period=${format(end, 'yyyy-MM-dd')}&location_id=${locationId}`
  }, [months, locationId])

  const fetchBrandTerms = async () => {
    try { setBrandTerms(await api.get<any[]>('/insights/brand-terms')) } catch (e) { console.error(e) }
  }

  const fetchSummary = useCallback(async () => {
    try {
      setSummary(await api.get(`/insights/keywords/summary?${periodParams()}`))
    } catch { setSummary(null) }
  }, [periodParams])

  const fetchKeywords = useCallback(async () => {
    setLoading(true); setError(false)
    try {
      const [sortBy, sortDir] = sort.split('_')
      let url = `/insights/keywords?${periodParams()}&page=${page}&page_size=${PAGE_SIZE}&sort_by=${sortBy}&sort_desc=${sortDir === 'desc'}`
      if (search) url += `&search=${encodeURIComponent(search)}`
      if (isBrandFilter !== null) url += `&is_brand=${isBrandFilter}`
      const res: any = await api.get(url)
      setKeywords(res?.items ?? [])
      setTotal(res?.total ?? 0)
    } catch {
      setError(true); setKeywords([]); setTotal(0)
      toast.error('Failed to load keywords')
    } finally { setLoading(false) }
  }, [periodParams, page, sort, search, isBrandFilter])

  const fetchSyncStatus = async () => {
    try {
      const st = await api.get<any>('/insights/sync-status')
      setSyncState((prev: any) => {
        if (prev.insights_sync_in_progress && !st.insights_sync_in_progress) {
          fetchSummary(); fetchKeywords()
        }
        return st
      })
    } catch (e) { console.error(e) }
  }

  useEffect(() => { fetchBrandTerms(); fetchSyncStatus() }, [])
  useEffect(() => { setPage(1) }, [months, isBrandFilter, search, sort])
  useEffect(() => { fetchSummary() }, [fetchSummary])
  useEffect(() => { fetchKeywords() }, [fetchKeywords])

  useEffect(() => {
    if (!syncState.insights_sync_in_progress) return
    const t = setInterval(() => {
      if (document.visibilityState !== 'hidden') fetchSyncStatus()
    }, 5000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncState.insights_sync_in_progress])

  const handleSync = async () => {
    try {
      const res: any = await api.post(`/insights/locations/${locationId}/sync?scope=keywords`)
      if (res?.status === 'AlreadyRunning') {
        toast.info('A sync is already running. Data refreshes when it finishes.')
      } else {
        toast.success('Sync started — keyword data refreshes when it completes.')
      }
      setSyncState((prev: any) => ({ ...prev, insights_sync_in_progress: true }))
    } catch {
      toast.error('Failed to start sync')
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      let qs = periodParams()
      if (search) qs += `&search=${encodeURIComponent(search)}`
      if (isBrandFilter !== null) qs += `&is_brand=${isBrandFilter}`
      const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
      const resp = await fetch(`${base}/insights/keywords/export?${qs}`, { credentials: 'include' })
      if (!resp.ok) throw new Error('Export failed')
      const blob = await resp.blob()
      const objUrl = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl; a.download = 'search_keywords.csv'
      document.body.appendChild(a); a.click(); a.remove()
      URL.revokeObjectURL(objUrl)
    } catch {
      toast.error('Failed to export CSV')
    } finally { setExporting(false) }
  }

  const handleAddBrandTerm = async () => {
    if (!newBrandTerm.trim()) return
    try {
      await api.post('/insights/brand-terms', { term: newBrandTerm.trim() })
      toast.success('Brand term added')
      setNewBrandTerm('')
      await fetchBrandTerms(); fetchSummary(); fetchKeywords()
    } catch (err: any) {
      toast.error(err?.message || 'Failed to add brand term')
    }
  }

  const handleDeleteBrandTerm = async (id: number) => {
    try {
      await api.delete(`/insights/brand-terms/${id}`)
      toast.success('Brand term deleted')
      await fetchBrandTerms(); fetchSummary(); fetchKeywords()
    } catch {
      toast.error('Failed to delete brand term')
    }
  }

  const kpis = summary?.kpis
  const trends: any[] = summary?.trends ?? []
  const maxTrend = Math.max(1, ...trends.map(t => t.total))

  const [sortCol, sortDir] = sort.split('_')
  const handleHeaderSort = (col: 'keyword' | 'impressions') => {
    if (sortCol === col) setSort(`${col}_${sortDir === 'desc' ? 'asc' : 'desc'}`)
    else setSort(`${col}_desc`)
  }
  const SortIcon = ({ col }: { col: 'keyword' | 'impressions' }) => {
    if (sortCol !== col) return <ChevronsUpDown className="h-3 w-3 opacity-40" />
    return sortDir === 'desc' ? <ChevronDown className="h-3 w-3" /> : <ChevronUp className="h-3 w-3" />
  }

  const Delta = ({ v }: { v: number | null }) => {
    if (v === null || v === undefined) return <span className="text-xs text-gray-400">—</span>
    const pos = v > 0, neg = v < 0
    return (
      <span className={`inline-flex items-center text-xs font-bold ${pos ? 'text-emerald-600' : neg ? 'text-rose-600' : 'text-gray-500'}`}>
        {pos ? <TrendingUp className="h-3 w-3 mr-0.5" /> : neg ? <TrendingDown className="h-3 w-3 mr-0.5" /> : null}
        {pos ? '+' : ''}{v.toFixed(1)}%
      </span>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-6">
        <div>
          <h2 className="text-xl font-extrabold tracking-tight text-foreground">Search Intelligence</h2>
          <p className="text-[11px] font-bold text-muted-foreground mt-1">How customers find this location on Google.</p>
          {syncState.insights_sync_in_progress ? (
            <span className="inline-flex items-center gap-1.5 mt-2 px-2.5 py-1 rounded-lg text-[10px] font-extrabold uppercase tracking-widest bg-indigo-500/10 text-indigo-500">
              <RefreshCw className="h-3 w-3 animate-spin" /> Updating data in background…
            </span>
          ) : syncState.last_insights_sync_at ? (
            <span className="text-[10px] font-bold text-muted-foreground mt-2 block">
              Last updated: {new Date(syncState.last_insights_sync_at).toLocaleString()}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex flex-1 items-center gap-2 border border-border/50 rounded-xl px-3 min-h-[44px] py-2 sm:flex-none sm:min-h-0 bg-background/50 backdrop-blur-md shadow-sm">
            <Calendar className="h-4 w-4 text-muted-foreground" />
            <select value={months} onChange={(e) => setMonths(parseInt(e.target.value))}
              className="w-full bg-transparent text-xs font-bold text-foreground outline-none cursor-pointer sm:w-auto">
              {RANGE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
            </select>
          </div>
          <Button size="sm" onClick={handleSync} disabled={syncState.insights_sync_in_progress} className="gap-2 flex-1 min-h-[44px] sm:h-9 sm:flex-none sm:min-h-0 text-xs bg-indigo-500 hover:bg-indigo-400 text-white font-bold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all rounded-xl">
            <RefreshCw className={`w-3.5 h-3.5 ${syncState.insights_sync_in_progress ? 'animate-spin' : ''}`} /> Sync Now
          </Button>
          <Button variant="outline" size="sm" onClick={handleExport} disabled={exporting} className="gap-2 flex-1 min-h-[44px] sm:h-9 sm:flex-none sm:min-h-0 text-xs font-bold shadow-sm hover:shadow hover:-translate-y-0.5 transition-all rounded-xl bg-background/50 backdrop-blur-md">
            <Download className="w-3.5 h-3.5" /> {exporting ? 'Exporting…' : 'Export CSV'}
          </Button>
          <Dialog>
            <DialogTrigger render={
              <Button size="sm" className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-500 hover:from-indigo-400 hover:to-purple-400 text-white w-full min-h-[44px] sm:h-9 sm:w-auto sm:min-h-0 text-xs font-bold shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all rounded-xl">
                <BarChart2 className="w-4 h-4" /> Brand Terms
              </Button>
            } />
            <DialogContent className="sm:max-w-md">
              <DialogHeader><DialogTitle>Brand Terms Management</DialogTitle></DialogHeader>
              <div className="space-y-4 py-2">
                <p className="text-xs text-muted-foreground">Keywords containing any of these terms are classified as Brand searches (applies across all locations).</p>
                <div className="flex items-center gap-2">
                  <Input
                    placeholder="Enter brand term (e.g. your business name)…"
                    value={newBrandTerm}
                    onChange={(e) => setNewBrandTerm(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAddBrandTerm()}
                  />
                  <Button onClick={handleAddBrandTerm} size="icon"><Plus className="h-4 w-4" /></Button>
                </div>
                <div className="space-y-2 max-h-[300px] overflow-y-auto pr-2">
                  {brandTerms.map((bt: any) => (
                    <div key={bt.id} className="flex justify-between items-center p-3 bg-muted/30 rounded-lg border border-border/50">
                      <span className="font-medium text-sm">{bt.term}</span>
                      <Button variant="ghost" size="icon" onClick={() => handleDeleteBrandTerm(bt.id)} className="h-8 w-8 text-red-500 hover:bg-red-50">
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                  {brandTerms.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-4">No brand terms configured.</p>
                  )}
                </div>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
        <div className="glass-panel border-border/40 rounded-2xl p-6 relative overflow-hidden shadow-sm group hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <Search className="w-24 h-24" />
          </div>
          <p className="flex items-center gap-1.5 text-[10px] font-extrabold text-muted-foreground uppercase tracking-widest mb-3 relative z-10">
            Total Impressions
            <InfoHint text={METRIC_HELP['Total Impressions']} />
          </p>
          <h3 className="text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight relative z-10">
            <AnimatedNumber value={kpis?.total_impressions ?? 0} />
          </h3>
          <div className="mt-4 relative z-10"><Delta v={kpis?.impressions_mom ?? null} /> <span className="text-[10px] font-bold text-muted-foreground ml-1 uppercase tracking-widest">vs prior period</span></div>
        </div>

        <div className="glass-panel border-border/40 rounded-2xl p-6 relative overflow-hidden shadow-sm group hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <BarChart2 className="w-24 h-24" />
          </div>
          <p className="text-[10px] font-extrabold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-1.5 relative z-10">
            Keywords Tracked
            <InfoHint text={METRIC_HELP['Keywords Tracked']} />
          </p>
          <h3 className="text-3xl sm:text-4xl font-extrabold text-foreground tracking-tight relative z-10">
            <AnimatedNumber value={kpis?.keywords_tracked ?? 0} />
          </h3>
          <p className="mt-4 text-[10px] font-bold text-muted-foreground uppercase tracking-widest relative z-10">unique terms in period</p>
        </div>

        <div className="glass-panel border-border/40 rounded-2xl p-6 relative overflow-hidden shadow-sm group hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <TrendingUp className="w-24 h-24 text-indigo-500" />
          </div>
          <p className="flex items-center gap-1.5 text-[10px] font-extrabold text-muted-foreground uppercase tracking-widest mb-3 relative z-10">
            Branded Impressions
            <InfoHint text={METRIC_HELP['Branded Impressions']} />
          </p>
          <h3 className="text-3xl sm:text-4xl font-extrabold text-indigo-500 tracking-tight relative z-10">
            <AnimatedNumber value={kpis?.branded_pct ?? 0} />%
          </h3>
          <p className="mt-4 text-[10px] font-bold text-muted-foreground uppercase tracking-widest relative z-10">{(kpis?.branded_impressions ?? 0).toLocaleString()} impressions</p>
        </div>

        <div className="glass-panel border-border/40 rounded-2xl p-6 relative overflow-hidden shadow-sm group hover:shadow-lg transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <Search className="w-24 h-24 text-emerald-500" />
          </div>
          <p className="flex items-center gap-1.5 text-[10px] font-extrabold text-muted-foreground uppercase tracking-widest mb-3 relative z-10">
            Non-Branded (Discovery)
            <InfoHint text={METRIC_HELP['Non-Branded (Discovery)']} />
          </p>
          <h3 className="text-3xl sm:text-4xl font-extrabold text-emerald-500 tracking-tight relative z-10">
            <AnimatedNumber value={kpis?.non_branded_pct ?? 0} />%
          </h3>
          <p className="mt-4 text-[10px] font-bold text-muted-foreground uppercase tracking-widest relative z-10">{(kpis?.non_branded_impressions ?? 0).toLocaleString()} impressions</p>
        </div>
      </div>

      {/* Trend chart */}
      <div className="glass-panel border-border/40 rounded-2xl p-6 shadow-sm border border-border/60">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <div>
            <h3 className="flex items-center gap-1.5 text-base font-bold text-foreground">
              Visibility Trend
              <InfoHint text={METRIC_HELP['Visibility Trend']} />
            </h3>
            <p className="text-xs text-muted-foreground mt-1">Monthly impressions — branded vs discovery</p>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-indigo-500 shadow-sm" />Branded</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-400 shadow-sm" />Discovery</span>
          </div>
        </div>
        
        {trends.length === 0 ? (
          <div className="h-64 flex items-center justify-center text-sm text-muted-foreground">No trend data for this range.</div>
        ) : (
          <div className="h-72 w-full mt-4 -ml-4">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={trends} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" className="text-border/40" />
                <XAxis 
                  dataKey="month" 
                  tickFormatter={(val) => new Date(val + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', year: '2-digit' })}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11 }}
                  className="text-muted-foreground"
                  dy={10}
                />
                <YAxis 
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 11 }}
                  tickFormatter={(val) => val.toLocaleString()}
                  className="text-muted-foreground"
                  dx={-10}
                />
                <Tooltip 
                  content={({ active, payload, label }: any) => {
                    if (active && payload && payload.length) {
                      const branded = payload.find((p: any) => p.dataKey === 'branded')?.value || 0
                      const discovery = payload.find((p: any) => p.dataKey === 'non_branded')?.value || 0
                      const totalVal = payload.find((p: any) => p.dataKey === 'total')?.value || (branded + discovery)
                      
                      const formattedDate = new Date(label + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
                      
                      return (
                        <div className="glass-panel p-4 shadow-xl border border-border/50 text-sm rounded-xl">
                          <p className="font-bold text-foreground mb-3 pb-2 border-b border-border/50">{formattedDate}</p>
                          <div className="space-y-2">
                            <div className="flex items-center justify-between gap-6">
                              <span className="flex items-center gap-2 text-muted-foreground">
                                <span className="h-2.5 w-2.5 rounded-sm bg-indigo-500 shadow-sm" />
                                Branded
                              </span>
                              <span className="font-bold text-foreground">{branded.toLocaleString()}</span>
                            </div>
                            <div className="flex items-center justify-between gap-6">
                              <span className="flex items-center gap-2 text-muted-foreground">
                                <span className="h-2.5 w-2.5 rounded-sm bg-emerald-400 shadow-sm" />
                                Discovery
                              </span>
                              <span className="font-bold text-foreground">{discovery.toLocaleString()}</span>
                            </div>
                            <div className="pt-2 mt-2 border-t border-border/50 flex items-center justify-between gap-6">
                              <span className="font-semibold text-foreground">Total</span>
                              <span className="font-extrabold text-foreground">{totalVal.toLocaleString()}</span>
                            </div>
                          </div>
                        </div>
                      )
                    }
                    return null
                  }} 
                  cursor={{ fill: 'transparent' }} 
                />
                <Bar dataKey="branded" stackId="a" fill="#6366f1" radius={[0, 0, 4, 4]} animationDuration={1000} />
                <Bar dataKey="non_branded" stackId="a" fill="#34d399" radius={[4, 4, 0, 0]} animationDuration={1000} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Top keywords */}
      <div className="glass-panel border-border/40 rounded-2xl overflow-hidden shadow-sm">
        <div className="p-6 border-b border-border/40 bg-muted/10 flex flex-col sm:flex-row gap-4 sm:items-center justify-between">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search keywords…" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-10 h-11 bg-background/50 border-border/50 rounded-xl" />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <select className="h-11 px-4 rounded-xl border border-border/50 bg-background/50 text-xs font-bold shadow-sm"
              value={isBrandFilter === null ? 'all' : isBrandFilter ? 'brand' : 'non-brand'}
              onChange={(e) => { const v = e.target.value; setIsBrandFilter(v === 'all' ? null : v === 'brand') }}>
              <option value="all">All Keywords</option>
              <option value="brand">Branded Only</option>
              <option value="non-brand">Discovery Only</option>
            </select>
            <select className="h-11 px-4 rounded-xl border border-border/50 bg-background/50 text-xs font-bold shadow-sm"
              value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="impressions_desc">Impressions ↓</option>
              <option value="impressions_asc">Impressions ↑</option>
              <option value="keyword_asc">Keyword A–Z</option>
              <option value="keyword_desc">Keyword Z–A</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-[10px] font-extrabold tracking-widest text-muted-foreground uppercase bg-muted/20 border-b border-border/40">
              <tr>
                <th className="px-6 py-4">
                  <button onClick={() => handleHeaderSort('keyword')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                    Keyword <SortIcon col="keyword" />
                  </button>
                </th>
                <th className="px-6 py-4 text-right">
                  <button onClick={() => handleHeaderSort('impressions')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors ml-auto">
                    Impressions <SortIcon col="impressions" />
                  </button>
                </th>
                <th className="px-6 py-4 text-right">vs Prior</th>
                <th className="px-6 py-4 text-right">Category</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={4} className="px-6 py-16 text-center text-muted-foreground">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                    <p className="text-xs font-bold uppercase tracking-widest">Loading intelligence data…</p>
                  </div>
                </td></tr>
              ) : error ? (
                <tr><td colSpan={4} className="px-6 py-16 text-center">
                  <div className="flex flex-col items-center gap-3 text-muted-foreground">
                    <div className="p-3 bg-red-500/10 rounded-2xl text-red-500">
                      <AlertCircle className="h-6 w-6" />
                    </div>
                    <p className="font-extrabold text-foreground">Couldn&apos;t load search keywords</p>
                    <button onClick={fetchKeywords} className="text-xs font-bold text-indigo-500 hover:underline uppercase tracking-widest">Retry</button>
                  </div>
                </td></tr>
              ) : keywords.length === 0 ? (
                <tr><td colSpan={4} className="px-6 py-16 text-center text-muted-foreground text-sm font-semibold">
                  No keywords found. Try a wider date range or click <span className="font-extrabold text-foreground">Sync Now</span>.
                </td></tr>
              ) : (
                keywords.map((kw: any, idx) => (
                  <tr key={idx} className="border-b border-border/30 hover:bg-muted/30 transition-colors">
                    <td className="px-6 py-5 font-bold text-foreground">{kw.keyword}</td>
                    <td className="px-6 py-5 text-right font-extrabold text-indigo-500">{(kw.impressions ?? 0).toLocaleString()}</td>
                    <td className="px-6 py-5 text-right">
                      <span title={`Prior period: ${(kw.impressions_prior ?? 0).toLocaleString()} impressions`}>
                        {kw.mom_growth === null && (kw.impressions_prior ?? 0) === 0 && (kw.impressions ?? 0) > 0 ? (
                          <span className="inline-flex items-center text-[10px] uppercase tracking-widest font-extrabold text-emerald-500 bg-emerald-500/10 px-2 py-0.5 rounded">
                            <TrendingUp className="h-3 w-3 mr-1" /> New
                          </span>
                        ) : (
                          <Delta v={kw.mom_growth ?? null} />
                        )}
                      </span>
                    </td>
                    <td className="px-6 py-5 text-right">
                      {kw.is_brand_term
                        ? <Badge className="bg-indigo-500/10 text-indigo-500 border-indigo-500/20 shadow-none uppercase font-extrabold tracking-widest text-[9px] px-2 py-0.5">Brand</Badge>
                        : <Badge variant="outline" className="text-muted-foreground border-border/50 shadow-none uppercase font-extrabold tracking-widest text-[9px] px-2 py-0.5">Discovery</Badge>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="p-4 border-t border-border/40 flex items-center justify-between bg-muted/10">
          <p className="text-sm text-muted-foreground">
            Showing <span className="font-semibold">{total === 0 ? 0 : Math.min((page - 1) * PAGE_SIZE + 1, total)}</span> to <span className="font-semibold">{Math.min(page * PAGE_SIZE, total)}</span> of <span className="font-semibold">{total}</span>
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || loading}>Previous</Button>
            <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page * PAGE_SIZE >= total || loading}>Next</Button>
          </div>
        </div>
      </div>
    </div>
  )
}
