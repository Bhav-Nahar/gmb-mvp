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
        <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 min-h-[44px] sm:min-h-0 bg-muted/20 shrink-0">
          <MapPin className="h-4 w-4 text-muted-foreground" />
          <select value={selectedLocation} onChange={(e) => setSelectedLocation(e.target.value)}
            className="bg-transparent text-sm font-medium outline-none cursor-pointer max-w-[200px]">
            <option value="all">All Locations</option>
            {locations.map((l) => <option key={l.id} value={String(l.id)}>{l.location_name}</option>)}
          </select>
        </div>
        <div className="flex items-center gap-2 border border-border rounded-lg px-3 py-2 min-h-[44px] sm:min-h-0 bg-muted/20 shrink-0">
          <Calendar className="h-4 w-4 text-muted-foreground" />
          <select value={months} onChange={(e) => setMonths(parseInt(e.target.value))}
            className="bg-transparent text-sm font-medium outline-none cursor-pointer">
            {RANGE_OPTIONS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <div className="bg-card rounded-xl p-6 border border-border/60 shadow-sm">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Total Impressions</p>
          <h3 className="text-3xl font-extrabold text-foreground">{(kpis?.total_impressions ?? 0).toLocaleString()}</h3>
          <div className="mt-2"><Delta v={kpis?.impressions_mom ?? null} /> <span className="text-xs text-muted-foreground">vs prior period</span></div>
        </div>
        <div className="bg-card rounded-xl p-6 border border-border/60 shadow-sm">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2 flex items-center gap-1">
            Keywords Tracked
            <span title="Google only reports keywords above a privacy threshold; low-volume terms may be hidden." className="cursor-help">
              <Info className="h-3 w-3" />
            </span>
          </p>
          <h3 className="text-3xl font-extrabold text-foreground">{(kpis?.keywords_tracked ?? 0).toLocaleString()}</h3>
          <p className="mt-2 text-xs text-muted-foreground">unique terms in period</p>
        </div>
        <div className="bg-card rounded-xl p-6 border border-border/60 shadow-sm">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Branded Impressions</p>
          <h3 className="text-3xl font-extrabold text-indigo-600">{(kpis?.branded_pct ?? 0)}%</h3>
          <p className="mt-2 text-xs text-muted-foreground">{(kpis?.branded_impressions ?? 0).toLocaleString()} impressions</p>
        </div>
        <div className="bg-card rounded-xl p-6 border border-border/60 shadow-sm">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Non-Branded (Discovery)</p>
          <h3 className="text-3xl font-extrabold text-emerald-600">{(kpis?.non_branded_pct ?? 0)}%</h3>
          <p className="mt-2 text-xs text-muted-foreground">{(kpis?.non_branded_impressions ?? 0).toLocaleString()} impressions</p>
        </div>
      </div>

      {/* Trend chart */}
      <div className="bg-card border border-border/60 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <div>
            <h3 className="text-base font-bold text-foreground">Visibility Trend</h3>
            <p className="text-xs text-muted-foreground">Monthly impressions — branded vs discovery</p>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-indigo-500" />Branded</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-400" />Discovery</span>
          </div>
        </div>
        {trends.length === 0 ? (
          <div className="h-56 flex items-center justify-center text-sm text-muted-foreground">No trend data for this range.</div>
        ) : (
          <div className="flex gap-3">
            {/* Y-axis scale */}
            <div className="flex flex-col justify-between h-56 py-1 text-[10px] text-muted-foreground text-right w-10 shrink-0">
              {[1, 0.75, 0.5, 0.25, 0].map((p) => (
                <span key={p}>{Math.round(maxTrend * p).toLocaleString()}</span>
              ))}
            </div>
            {/* Plot area with gridlines */}
            <div className="relative flex-1">
              <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
                {[0, 1, 2, 3, 4].map((i) => <div key={i} className="border-t border-border/40" />)}
              </div>
              <div className="relative flex items-end justify-around gap-2 sm:gap-3 h-56">
                {trends.map((t) => {
                  const brandedH = (t.branded / maxTrend) * 100
                  const discoveryH = (t.non_branded / maxTrend) * 100
                  return (
                    <div key={t.month} className="flex flex-col items-center flex-1 h-full justify-end group">
                      {t.total > 0 && (
                        <span className="text-[10px] font-semibold text-foreground mb-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {t.total.toLocaleString()}
                        </span>
                      )}
                      <div
                        className="w-full max-w-[44px] mx-auto flex flex-col justify-end rounded-t-md overflow-hidden cursor-default"
                        style={{ height: t.total > 0 ? `${Math.max(brandedH + discoveryH, 2)}%` : '2px' }}
                        title={
                          t.total > 0
                            ? `${new Date(t.month + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}\nBranded: ${t.branded.toLocaleString()}\nDiscovery: ${t.non_branded.toLocaleString()}\nTotal: ${t.total.toLocaleString()}`
                            : `${new Date(t.month + 'T00:00:00').toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}: no data`
                        }
                      >
                        {t.total > 0 ? (
                          <>
                            <div className="bg-indigo-500 transition-all" style={{ height: `${(brandedH / (brandedH + discoveryH || 1)) * 100}%` }} />
                            <div className="bg-emerald-400 transition-all" style={{ height: `${(discoveryH / (brandedH + discoveryH || 1)) * 100}%` }} />
                          </>
                        ) : (
                          <div className="bg-border/60 h-full" />
                        )}
                      </div>
                      <span className="text-[10px] text-muted-foreground mt-2 whitespace-nowrap">
                        {new Date(t.month + 'T00:00:00').toLocaleDateString(undefined, { month: 'short', year: '2-digit' })}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Location comparison (All Locations only) */}
      {selectedLocation === 'all' && comparison.length > 0 && (
        <div className="bg-card border border-border/60 rounded-xl p-6 shadow-sm">
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
      <div className="bg-card border border-border/60 rounded-xl overflow-hidden shadow-sm">
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
                  <tr><td colSpan={4} className="py-12 text-center text-muted-foreground">
                    <div className="flex flex-col items-center gap-3">
                      <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                      <p>Loading intelligence data…</p>
                    </div>
                  </td></tr>
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
