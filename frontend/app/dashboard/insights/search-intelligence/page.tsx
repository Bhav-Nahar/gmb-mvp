'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Search, Download, Plus, Trash2, BarChart2, AlertCircle, RefreshCw,
  TrendingUp, TrendingDown, Info, MapPin, Calendar, ChevronUp, ChevronDown, ChevronsUpDown
} from 'lucide-react'
import { format, startOfMonth, subMonths } from 'date-fns'
import { toast } from 'sonner'
import Link from 'next/link'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog'
import { api } from '@/lib/api'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'
import { Skeleton } from '@/components/ui/skeleton'
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

export default function SearchIntelligencePage() {
  const [locations, setLocations] = useState<any[]>([])
  const [selectedLocation, setSelectedLocation] = useState<string>('all')
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
    let qs = `start_period=${format(start, 'yyyy-MM-dd')}&end_period=${format(end, 'yyyy-MM-dd')}`
    if (selectedLocation !== 'all') qs += `&location_id=${selectedLocation}`
    return qs
  }, [months, selectedLocation])

  const fetchLocations = async () => {
    try { setLocations(await api.get<any[]>('/locations/')) } catch { /* non-fatal */ }
  }

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

  useEffect(() => { fetchLocations(); fetchBrandTerms(); fetchSyncStatus() }, [])
  useEffect(() => { setPage(1) }, [selectedLocation, months, isBrandFilter, search, sort])
  useEffect(() => { fetchSummary() }, [fetchSummary])
  useEffect(() => { fetchKeywords() }, [fetchKeywords])

  useEffect(() => {
    if (!syncState.insights_sync_in_progress) return
    const t = setInterval(fetchSyncStatus, 5000)
    return () => clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [syncState.insights_sync_in_progress])

  const handleSync = async () => {
    try {
      const res: any = await api.post('/insights/sync-all?force=true&scope=keywords')
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
  const rawComparison: any[] = summary?.location_comparison ?? []
  const maxTrend = Math.max(1, ...trends.map(t => t.total))

  // Client-side sort for the location comparison table.
  const [cmpSort, setCmpSort] = useState<{ key: 'location_name' | 'impressions' | 'mom_growth'; dir: 'asc' | 'desc' }>({ key: 'impressions', dir: 'desc' })
  const comparison = [...rawComparison].sort((a, b) => {
    const mult = cmpSort.dir === 'asc' ? 1 : -1
    const av = a[cmpSort.key] ?? (cmpSort.key === 'location_name' ? '' : 0)
    const bv = b[cmpSort.key] ?? (cmpSort.key === 'location_name' ? '' : 0)
    if (typeof av === 'string' || typeof bv === 'string') return String(av).localeCompare(String(bv)) * mult
    return ((av as number) - (bv as number)) * mult
  })
  const toggleCmpSort = (key: 'location_name' | 'impressions' | 'mom_growth') =>
    setCmpSort((prev) => prev.key === key ? { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' })
  const CmpSortIcon = ({ k }: { k: 'location_name' | 'impressions' | 'mom_growth' }) =>
    cmpSort.key !== k ? <span className="opacity-30">↕</span> : <span>{cmpSort.dir === 'desc' ? '↓' : '↑'}</span>

  // Clicking a column header sorts by it; clicking the active column flips
  // direction. Only backend-sortable columns (keyword, impressions) are wired.
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

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      const branded = payload.find((p: any) => p.dataKey === 'branded')?.value || 0
      const discovery = payload.find((p: any) => p.dataKey === 'non_branded')?.value || 0
      const total = payload.find((p: any) => p.dataKey === 'total')?.value || 0
      
      const formattedDate = new Date(label + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
      
      return (
        <div className="glass-panel p-4 shadow-xl border border-border/50 text-sm">
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
              <span className="font-extrabold text-foreground">{total.toLocaleString()}</span>
            </div>
          </div>
        </div>
      )
    }
    return null
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col gap-4 lg:flex-row lg:justify-between lg:items-center">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">Search Intelligence</h1>
          <p className="text-muted-foreground mt-1">Discover how customers find your business on Google.</p>
          {syncState.insights_sync_in_progress ? (
            <span className="inline-flex items-center gap-1.5 mt-2 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-700">
              <RefreshCw className="h-3 w-3 animate-spin" /> Updating data in background…
            </span>
          ) : syncState.last_insights_sync_at ? (
            <span className="text-[11px] text-muted-foreground mt-2 block">
              Last updated: {new Date(syncState.last_insights_sync_at).toLocaleString()}
            </span>
          ) : null}
        </div>
        <div className="grid grid-cols-2 sm:flex items-center gap-3 sm:flex-wrap">
          <Button variant="outline" onClick={handleSync} disabled={syncState.insights_sync_in_progress} className="gap-2 w-full sm:w-auto min-h-[44px] sm:min-h-0">
            <RefreshCw className={`w-4 h-4 ${syncState.insights_sync_in_progress ? 'animate-spin' : ''}`} /> Sync Now
          </Button>
          <Button variant="outline" onClick={handleExport} disabled={exporting} className="gap-2 w-full sm:w-auto min-h-[44px] sm:min-h-0">
            <Download className="w-4 h-4" /> {exporting ? 'Exporting…' : 'Export CSV'}
          </Button>
          <Dialog>
            <DialogTrigger render={
              <Button className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white col-span-2 w-full sm:w-auto min-h-[44px] sm:min-h-0">
                <BarChart2 className="w-4 h-4" /> Brand Terms
              </Button>
            } />
            <DialogContent className="sm:max-w-md">
              <DialogHeader><DialogTitle>Brand Terms Management</DialogTitle></DialogHeader>
              <div className="space-y-4 py-2">
                <p className="text-xs text-muted-foreground">Keywords containing any of these terms are classified as Brand searches.</p>
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

      {/* Filters */}
      <div className="flex gap-3 overflow-x-auto sm:flex-wrap sm:items-center sm:overflow-visible pb-1 sm:pb-0 [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
        <div className="relative group shrink-0">
          <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
            <MapPin className="h-4 w-4 text-indigo-500 group-hover:text-indigo-400 transition-colors" />
          </div>
          <select value={selectedLocation} onChange={(e) => setSelectedLocation(e.target.value)}
            className="pl-9 pr-8 py-2.5 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl text-xs font-bold text-foreground outline-none cursor-pointer shadow-sm hover:shadow-md hover:border-indigo-500/30 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/50 transition-all appearance-none min-w-[160px] max-w-[200px]">
            <option value="all" className="bg-background font-semibold">All Locations</option>
            {locations.map((l) => <option key={l.id} value={String(l.id)} className="bg-background">{l.location_name}</option>)}
          </select>
          <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
            <span className="text-[10px] opacity-50">▼</span>
          </div>
        </div>
        <div className="relative group shrink-0">
          <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
            <Calendar className="h-4 w-4 text-emerald-500 group-hover:text-emerald-400 transition-colors" />
          </div>
          <select value={months} onChange={(e) => setMonths(parseInt(e.target.value))}
            className="pl-9 pr-8 py-2.5 bg-background/50 backdrop-blur-md border border-border/60 rounded-xl text-xs font-bold text-foreground outline-none cursor-pointer shadow-sm hover:shadow-md hover:border-emerald-500/30 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/50 transition-all appearance-none">
            {RANGE_OPTIONS.map((r) => <option key={r.value} value={r.value} className="bg-background font-semibold">{r.label}</option>)}
          </select>
          <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
            <span className="text-[10px] opacity-50">▼</span>
          </div>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.12)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.05)] transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <Search className="w-24 h-24" />
          </div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 relative z-10">Total Impressions</p>
          <h3 className="text-3xl font-extrabold text-foreground tracking-tight relative z-10">
            <AnimatedNumber value={kpis?.total_impressions ?? 0} />
          </h3>
          <div className="mt-2 relative z-10"><Delta v={kpis?.impressions_mom ?? null} /> <span className="text-xs text-muted-foreground ml-1">vs prior period</span></div>
        </div>
        
        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.12)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.05)] transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <BarChart2 className="w-24 h-24" />
          </div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1 relative z-10">
            Keywords Tracked
            <span title="Google only reports keywords above a privacy threshold; low-volume terms may be hidden." className="cursor-help">
              <Info className="h-3 w-3" />
            </span>
          </p>
          <h3 className="text-3xl font-extrabold text-foreground tracking-tight relative z-10">
            <AnimatedNumber value={kpis?.keywords_tracked ?? 0} />
          </h3>
          <p className="mt-2 text-xs text-muted-foreground relative z-10">unique terms in period</p>
        </div>

        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.12)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.05)] transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <TrendingUp className="w-24 h-24" />
          </div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 relative z-10">Branded Impressions</p>
          <h3 className="text-3xl font-extrabold text-indigo-600 dark:text-indigo-400 tracking-tight relative z-10">
            {kpis?.branded_pct ?? 0}%
          </h3>
          <p className="mt-2 text-xs text-muted-foreground relative z-10">
            {(kpis?.branded_impressions ?? 0).toLocaleString()} impressions
          </p>
        </div>

        <div className="glass-panel rounded-xl p-6 relative overflow-hidden group hover:shadow-[0_8px_30px_rgb(0,0,0,0.12)] dark:hover:shadow-[0_8px_30px_rgba(255,255,255,0.05)] transition-all duration-300 transform hover:-translate-y-1">
          <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none group-hover:scale-110 transition-transform duration-500">
            <Search className="w-24 h-24" />
          </div>
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 relative z-10">Non-Branded (Discovery)</p>
          <h3 className="text-3xl font-extrabold text-emerald-600 dark:text-emerald-400 tracking-tight relative z-10">
            {kpis?.non_branded_pct ?? 0}%
          </h3>
          <p className="mt-2 text-xs text-muted-foreground relative z-10">
            {(kpis?.non_branded_impressions ?? 0).toLocaleString()} impressions
          </p>
        </div>
      </div>

      {/* Trend chart */}
      <div className="glass-panel rounded-xl p-6 shadow-sm border border-border/60">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <div>
            <h3 className="text-base font-bold text-foreground">Visibility Trend</h3>
            <p className="text-xs text-muted-foreground">Monthly impressions — branded vs discovery</p>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-indigo-500 shadow-sm" />Branded</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-400 shadow-sm" />Discovery</span>
          </div>
        </div>
        
        {loading ? (
          <div className="h-64 flex flex-col items-center justify-center space-y-4">
            <Skeleton className="h-48 w-full rounded-lg" />
            <div className="flex justify-between w-full">
              {[1, 2, 3, 4, 5, 6].map(i => <Skeleton key={i} className="h-4 w-12" />)}
            </div>
          </div>
        ) : trends.length === 0 ? (
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
                <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
                <Bar dataKey="branded" stackId="a" fill="#6366f1" radius={[0, 0, 4, 4]} animationDuration={1000} />
                <Bar dataKey="non_branded" stackId="a" fill="#34d399" radius={[4, 4, 0, 0]} animationDuration={1000} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Location comparison (All Locations only) */}
      {selectedLocation === 'all' && comparison.length > 0 && (
        <div className="glass-panel border border-border/60 rounded-xl p-6 shadow-sm">
          <h3 className="text-base font-bold text-foreground mb-4">Location Comparison</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-muted-foreground font-semibold">
                  <th className="pb-3"><button onClick={() => toggleCmpSort('location_name')} className="inline-flex items-center gap-1 hover:text-foreground">Location <CmpSortIcon k="location_name" /></button></th>
                  <th className="pb-3 text-right"><button onClick={() => toggleCmpSort('impressions')} className="inline-flex items-center gap-1 hover:text-foreground ml-auto">Impressions <CmpSortIcon k="impressions" /></button></th>
                  <th className="pb-3 text-right"><button onClick={() => toggleCmpSort('mom_growth')} className="inline-flex items-center gap-1 hover:text-foreground ml-auto">vs Prior <CmpSortIcon k="mom_growth" /></button></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-medium">
                {comparison.map((c) => (
                  <tr key={c.location_id} className="hover:bg-muted/10 transition-colors">
                    <td className="py-3 pr-2">
                      <Link href={`/dashboard/locations/${c.location_id}`} className="text-foreground hover:underline hover:text-indigo-600 transition-colors">
                        {c.location_name}
                      </Link>
                    </td>
                    <td className="py-3 text-right text-muted-foreground">{c.impressions.toLocaleString()}</td>
                    <td className="py-3 text-right"><Delta v={c.mom_growth} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Top keywords */}
      <div className="glass-panel border border-border/60 rounded-xl overflow-hidden shadow-sm">
        <div className="p-5 border-b border-border/60 bg-muted/20 flex flex-col sm:flex-row gap-4 sm:items-center justify-between">
          <div className="relative w-full max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input placeholder="Search keywords…" value={search} onChange={(e) => setSearch(e.target.value)} className="pl-9" />
          </div>
          <div className="flex flex-wrap sm:flex-nowrap items-center gap-2">
            <select className="h-11 sm:h-10 flex-1 min-w-[140px] sm:flex-none px-3 rounded-md border border-input bg-background text-sm"
              value={isBrandFilter === null ? 'all' : isBrandFilter ? 'brand' : 'non-brand'}
              onChange={(e) => { const v = e.target.value; setIsBrandFilter(v === 'all' ? null : v === 'brand') }}>
              <option value="all">All Keywords</option>
              <option value="brand">Branded Only</option>
              <option value="non-brand">Discovery Only</option>
            </select>
            <select className="h-11 sm:h-10 flex-1 min-w-[140px] sm:flex-none px-3 rounded-md border border-input bg-background text-sm"
              value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="impressions_desc">Impressions ↓</option>
              <option value="impressions_asc">Impressions ↑</option>
              <option value="keyword_asc">Keyword A–Z</option>
              <option value="keyword_desc">Keyword Z–A</option>
            </select>
          </div>
        </div>

        <div className="p-6">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-border/60 text-muted-foreground font-semibold">
                  <th className="pb-3">
                    <button onClick={() => handleHeaderSort('keyword')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors">
                      Keyword <SortIcon col="keyword" />
                    </button>
                  </th>
                  <th className="pb-3 text-right">
                    <button onClick={() => handleHeaderSort('impressions')} className="inline-flex items-center gap-1 hover:text-foreground transition-colors ml-auto">
                      Impressions <SortIcon col="impressions" />
                    </button>
                  </th>
                  <th className="pb-3 text-right">vs Prior</th>
                  <th className="pb-3 text-right">Category</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-medium">
                {loading ? (
                  Array.from({ length: 5 }).map((_, i) => (
                    <tr key={i} className="animate-pulse">
                      <td className="py-4"><Skeleton className="h-4 w-32" /></td>
                      <td className="py-4 text-right"><Skeleton className="h-4 w-12 ml-auto" /></td>
                      <td className="py-4 text-right"><Skeleton className="h-4 w-16 ml-auto" /></td>
                      <td className="py-4 text-right"><Skeleton className="h-6 w-20 rounded-full ml-auto" /></td>
                    </tr>
                  ))
                ) : error ? (
                  <tr><td colSpan={4} className="py-12 text-center">
                    <div className="flex flex-col items-center gap-2 text-muted-foreground">
                      <AlertCircle className="h-6 w-6 text-amber-500" />
                      <p className="text-foreground">Couldn&apos;t load search keywords</p>
                    <button onClick={fetchKeywords} className="text-sm font-medium text-indigo-600 hover:underline">Retry</button>
                  </div>
                </td></tr>
              ) : keywords.length === 0 ? (
                <tr><td colSpan={4} className="py-12 text-center text-muted-foreground">
                  No keywords found. Try a wider date range or click <span className="font-semibold">Sync Now</span>.
                </td></tr>
              ) : (
                keywords.map((kw: any, idx) => (
                  <tr key={idx} className="hover:bg-muted/10 transition-colors">
                    <td className="py-3 text-foreground break-words max-w-[200px]">{kw.keyword}</td>
                    <td className="py-3 text-right text-muted-foreground">{(kw.impressions ?? 0).toLocaleString()}</td>
                    <td className="py-3 text-right">
                      <span title={`Prior period: ${(kw.impressions_prior ?? 0).toLocaleString()} impressions`}>
                        {kw.mom_growth === null && (kw.impressions_prior ?? 0) === 0 && (kw.impressions ?? 0) > 0 ? (
                          <span className="inline-flex items-center text-xs font-bold text-emerald-600 dark:text-emerald-400">
                            <TrendingUp className="h-3 w-3 mr-0.5" /> New
                          </span>
                        ) : (
                          <Delta v={kw.mom_growth ?? null} />
                        )}
                      </span>
                    </td>
                    <td className="py-3 text-right">
                      {kw.is_brand_term
                        ? <Badge className="bg-indigo-100 text-indigo-700 border-indigo-200 shadow-none">Brand</Badge>
                        : <Badge variant="outline" className="text-muted-foreground shadow-none">Discovery</Badge>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        </div>

        <div className="p-4 border-t border-border/60 flex items-center justify-between bg-muted/20">
          <p className="text-sm text-muted-foreground">
            Showing <span className="font-semibold">{total === 0 ? 0 : Math.min((page - 1) * PAGE_SIZE + 1, total)}</span> to <span className="font-semibold">{Math.min(page * PAGE_SIZE, total)}</span> of <span className="font-semibold">{total}</span>
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1 || loading} className="min-h-[44px] sm:min-h-0">Previous</Button>
            <Button variant="outline" size="sm" onClick={() => setPage(p => p + 1)} disabled={page * PAGE_SIZE >= total || loading} className="min-h-[44px] sm:min-h-0">Next</Button>
          </div>
        </div>
      </div>
    </div>
  )
}
