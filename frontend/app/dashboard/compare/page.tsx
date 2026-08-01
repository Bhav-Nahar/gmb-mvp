'use client'

import { useState, useEffect, useMemo } from 'react'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { 
  Trophy, 
  TrendingUp, 
  TrendingDown, 
  Minus, 
  Medal, 
  Search, 
  Download, 
  Info, 
  X, 
  ChevronDown, 
  ChevronUp,
  Star,
  Activity,
  MessageSquare,
  MapPin,
  RefreshCw
} from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'
import { InfoHint } from '@/components/ui/InfoHint'
import { METRIC_HELP } from '@/lib/metric-help'
import { Skeleton } from '@/components/ui/skeleton'

interface LocationSnapshot {
  location_id: number
  location_name: string
  period_label: string
  is_eligible: boolean
  ineligibility_reason: string | null
  composite_score: number | null
  rank: number | null
  previous_rank: number | null
  rank_movement: number | null
  cohort: string | null
  cohort_rank: number | null
  cohort_size: number | null
  streak_count: number
  most_improved_flag: boolean
  average_rating_raw: number | null
  review_velocity_raw: number | null
  health_score_raw: number | null
  review_volume_raw: number | null
  score_contributions: {
    average_rating?: number
    review_velocity?: number
    health_score?: number
    review_volume?: number
    response_rate?: number
  }
}

interface LeaderboardData {
  has_data: boolean
  period: string | null
  snapshot_version: string
  generated_at: string | null
  organization_benchmark: {
    average_rating_raw: number | null
    total_reviews: number | null
    health_score_raw: number | null
  }
  awards: {
    top_performer?: { location_id: number; location_name: string; composite_score: number }
    most_improved?: { location_id: number; location_name: string; rank_movement: number }
    highest_rated?: { location_id: number; location_name: string; average_rating_raw: number }
    highest_review_velocity?: { location_id: number; location_name: string; review_velocity_raw: number }
  }
  eligible_locations: LocationSnapshot[]
  ineligible_locations: LocationSnapshot[]
}

interface ExplainData {
  location_id: number
  current_period: string
  previous_period: string | null
  rank_movement: number | null
  from_rank: number | null
  to_rank: number | null
  deltas: Record<string, { from: number; to: number; change: number }> | null
  score_contribution_deltas: Record<string, number> | null
}

interface HistoryData {
  period_label: string
  composite_score: number | null
  rank: number | null
  is_eligible: boolean
}

interface NextAction {
  metric: string
  headline: string
  detail: string
  projected_composite_gain: number
  projected_composite_score: number
  current_cohort_rank: number | null
  projected_cohort_rank: number | null
}

interface NextActionData {
  has_data: boolean
  cohort?: string | null
  next_action: NextAction | null
}

export default function LeaderboardPage() {
  const { user } = useAuth()
  const [periods, setPeriods] = useState<string[]>([])
  const [selectedPeriod, setSelectedPeriod] = useState<string>('')
  const [data, setData] = useState<LeaderboardData | null>(null)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  
  const [viewMode, setViewMode] = useState<'table' | 'leaderboard'>('leaderboard')
  const [searchQuery, setSearchQuery] = useState('')
  const [showIneligible, setShowIneligible] = useState(false)
  
  // Drill-in state
  const [selectedLocation, setSelectedLocation] = useState<LocationSnapshot | null>(null)
  const [explainData, setExplainData] = useState<ExplainData | null>(null)
  const [historyData, setHistoryData] = useState<HistoryData[]>([])
  const [nextAction, setNextAction] = useState<NextAction | null>(null)
  const [drawerLoading, setDrawerLoading] = useState(false)

  const isAdmin = user?.role === 'Admin' || user?.role === 'Owner'

  useEffect(() => {
    loadPeriods()
  }, [])

  useEffect(() => {
    loadData()
  }, [selectedPeriod])

  const loadPeriods = async () => {
    try {
      const p = await api.get<string[]>('/leaderboard/periods')
      setPeriods(p || [])
      if (p && p.length > 0 && !selectedPeriod) {
        setSelectedPeriod(p[0])
      }
    } catch (err) {
      console.error(err)
    }
  }

  const handleSync = async () => {
    setSyncing(true)
    try {
      const url = selectedPeriod 
        ? `/leaderboard/generate?period=${selectedPeriod}` 
        : `/leaderboard/generate`
      await api.post(url)
      await loadPeriods()
      await loadData()
    } catch (err) {
      console.error(err)
    } finally {
      setSyncing(false)
    }
  }

  const loadData = async () => {
    setLoading(true)
    try {
      const url = selectedPeriod ? `/leaderboard?period=${selectedPeriod}` : '/leaderboard'
      const res = await api.get<LeaderboardData>(url)
      setData(res)
      if (res && res.period && !selectedPeriod) {
        setSelectedPeriod(res.period)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async (format: 'csv' | 'xlsx') => {
    try {
      const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
      const url = `${base}/leaderboard/export?format=${format}${selectedPeriod ? `&period=${selectedPeriod}` : ''}`
      const resp = await fetch(url, { credentials: 'include' })
      if (!resp.ok) throw new Error('Export failed')
      const blob = await resp.blob()
      const objUrl = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = objUrl
      a.download = `leaderboard_${selectedPeriod || 'export'}.${format}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      window.URL.revokeObjectURL(objUrl)
    } catch (err) {
      console.error(err)
    }
  }

  const openDrillIn = async (loc: LocationSnapshot) => {
    setSelectedLocation(loc)
    setExplainData(null)
    setHistoryData([])
    setNextAction(null)
    setDrawerLoading(true)
    try {
      const [explainRes, historyRes, actionRes] = await Promise.all([
        api.get<ExplainData>(`/leaderboard/${loc.location_id}/explain?period=${loc.period_label}`),
        api.get<HistoryData[]>(`/leaderboard/${loc.location_id}/history`),
        api.get<NextActionData>(`/leaderboard/${loc.location_id}/next-action?period=${loc.period_label}`)
      ])
      setExplainData(explainRes)
      setHistoryData(historyRes)
      setNextAction(actionRes?.next_action ?? null)
    } catch (err) {
      console.error(err)
    } finally {
      setDrawerLoading(false)
    }
  }

  const filteredEligible = useMemo(() => {
    if (!data?.eligible_locations) return []
    if (!searchQuery) return data.eligible_locations
    const q = searchQuery.toLowerCase()
    return data.eligible_locations.filter(l => l.location_name.toLowerCase().includes(q))
  }, [data, searchQuery])

  const filteredIneligible = useMemo(() => {
    if (!data?.ineligible_locations) return []
    if (!searchQuery) return data.ineligible_locations
    const q = searchQuery.toLowerCase()
    return data.ineligible_locations.filter(l => l.location_name.toLowerCase().includes(q))
  }, [data, searchQuery])

  const MovementIcon = ({ movement }: { movement: number | null }) => {
    if (movement === null) return <span className="text-xs font-bold text-muted-foreground bg-muted px-1.5 py-0.5 rounded">NEW</span>
    if (movement > 0) return <span className="flex items-center text-green-500"><TrendingUp className="h-4 w-4 mr-1" />{movement}</span>
    if (movement < 0) return <span className="flex items-center text-red-500"><TrendingDown className="h-4 w-4 mr-1" />{Math.abs(movement)}</span>
    return <span className="flex items-center text-muted-foreground"><Minus className="h-4 w-4 mr-1" /></span>
  }

  if (loading && !data) {
    return (
      <div className="p-6 max-w-7xl mx-auto space-y-8">
        <div className="flex justify-between">
          <Skeleton className="h-10 w-48 rounded-lg" />
          <div className="flex gap-3"><Skeleton className="h-10 w-32 rounded-lg" /><Skeleton className="h-10 w-24 rounded-lg" /></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="h-24 rounded-xl" /><Skeleton className="h-24 rounded-xl" /><Skeleton className="h-24 rounded-xl" />
        </div>
        <Skeleton className="h-40 rounded-xl" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Skeleton className="h-32 rounded-xl" /><Skeleton className="h-32 rounded-xl" /><Skeleton className="h-32 rounded-xl" />
        </div>
      </div>
    )
  }

  const isSmallOrg = data?.has_data && data.eligible_locations.length < 2

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight text-foreground flex items-center gap-3">
            <Trophy className="h-8 w-8 text-yellow-500" />
            Leaderboard
          </h1>
          <p className="text-muted-foreground mt-1 font-semibold">Gamified performance ranking across your network.</p>
        </div>
        
        <div className="flex items-center gap-3">
          {isAdmin && (
            <button 
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-indigo-500 hover:from-indigo-500 hover:to-indigo-400 text-white shadow-[0_4px_14px_0_rgb(79,70,229,0.39)] hover:shadow-[0_6px_20px_rgba(79,70,229,0.23)] rounded-lg text-sm font-bold transition-all active:scale-95 disabled:opacity-50 disabled:active:scale-100 disabled:hover:shadow-[0_4px_14px_0_rgb(79,70,229,0.39)]"
            >
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
          )}
          <div className="flex flex-col gap-1.5 relative group">
            <select
              className="appearance-none bg-background/50 backdrop-blur-md border border-border/60 shadow-sm rounded-lg text-sm font-bold pl-4 pr-10 py-2.5 text-foreground outline-none focus:border-indigo-500 hover:border-indigo-500/30 transition-all min-w-[150px] cursor-pointer"
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
            >
              <option value="" disabled>Select Period</option>
              {periods.map(p => <option key={p} value={p} className="bg-background">{p}</option>)}
            </select>
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none"><span className="text-[10px] opacity-50">▼</span></div>
          </div>
          <button 
            onClick={() => handleExport('csv')}
            disabled={!data?.has_data}
            className="flex items-center gap-2 px-4 py-2.5 bg-background/50 backdrop-blur-md border border-border/60 shadow-sm rounded-lg text-sm font-bold hover:bg-muted/50 hover:border-indigo-500/30 transition-all disabled:opacity-50"
          >
            <Download className="h-4 w-4" /> CSV
          </button>
          <button 
            onClick={() => handleExport('xlsx')}
            disabled={!data?.has_data}
            className="flex items-center gap-2 px-4 py-2.5 bg-background/50 backdrop-blur-md border border-border/60 shadow-sm rounded-lg text-sm font-bold hover:bg-muted/50 hover:border-indigo-500/30 transition-all disabled:opacity-50"
          >
            <Download className="h-4 w-4" /> XLSX
          </button>
        </div>
      </div>

      {!data?.has_data ? (
        <div className="bg-card border border-border rounded-xl p-12 text-center flex flex-col items-center justify-center">
          <Trophy className="h-12 w-12 text-muted-foreground/30 mb-4" />
          <h2 className="text-lg font-bold text-foreground">No Leaderboard Data</h2>
          <p className="text-muted-foreground mt-2 max-w-md mb-6">There are no snapshots generated for this period. Snapshots run at the beginning of each month.</p>
          {isAdmin && (
            <button 
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-2 px-6 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Generating...' : 'Generate Leaderboard'}
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Organization Benchmark Card */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="glass-panel border-border/60 rounded-xl p-5 flex items-center gap-5 shadow-sm group hover:-translate-y-0.5 transition-all">
              <div className="h-14 w-14 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
                <Star className="h-7 w-7 text-blue-500" />
              </div>
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-wider text-muted-foreground">Org Avg Rating</p>
                <p className="text-3xl font-black text-foreground mt-1">
                  {data.organization_benchmark.average_rating_raw != null ? <AnimatedNumber value={data.organization_benchmark.average_rating_raw} isFloat formatter={(v) => v.toFixed(2)} /> : 'N/A'}
                </p>
              </div>
            </div>
            <div className="glass-panel border-border/60 rounded-xl p-5 flex items-center gap-5 shadow-sm group hover:-translate-y-0.5 transition-all">
              <div className="h-14 w-14 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center shrink-0">
                <MessageSquare className="h-7 w-7 text-emerald-500" />
              </div>
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-wider text-muted-foreground">Total Reviews</p>
                <p className="text-3xl font-black text-foreground mt-1">
                  {data.organization_benchmark.total_reviews != null ? <AnimatedNumber value={data.organization_benchmark.total_reviews} /> : 'N/A'}
                </p>
              </div>
            </div>
            <div className="glass-panel border-border/60 rounded-xl p-5 flex items-center gap-5 shadow-sm group hover:-translate-y-0.5 transition-all">
              <div className="h-14 w-14 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center shrink-0">
                <Activity className="h-7 w-7 text-indigo-500" />
              </div>
              <div>
                <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wider text-muted-foreground">
                  Org Health Score
                  <InfoHint text={METRIC_HELP['Health Score']} />
                </p>
                <p className="text-3xl font-black text-foreground mt-1">
                  {data.organization_benchmark.health_score_raw != null ? <AnimatedNumber value={data.organization_benchmark.health_score_raw} isFloat formatter={(v) => v.toFixed(1)} /> : 'N/A'}
                </p>
              </div>
            </div>
          </div>

          {/* Awards Grid - Only render if awards exist */}
          {!isSmallOrg && data.awards && Object.values(data.awards).some(v => v !== undefined && v !== null) && (
            <div className="pt-4">
              <h3 className="text-lg font-extrabold mb-4 flex items-center gap-2"><Medal className="h-5 w-5 text-indigo-500"/> Monthly Awards</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {data.awards.top_performer && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.top_performer?.location_id)!)} className="relative overflow-hidden bg-gradient-to-br from-yellow-500/20 to-amber-600/10 backdrop-blur-md border border-yellow-500/30 rounded-xl p-5 cursor-pointer hover:-translate-y-1 hover:shadow-lg transition-all shadow-sm group">
                    <Trophy className="absolute -right-4 -bottom-4 h-24 w-24 text-yellow-500/10 transform group-hover:scale-110 transition-transform duration-500" />
                    <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest text-yellow-600 mb-2 relative z-10">
                      Top Performer
                      <InfoHint text={METRIC_HELP['Top Performer']} />
                    </p>
                    <p className="text-base font-black text-foreground truncate relative z-10">{data.awards.top_performer.location_name}</p>
                    <p className="text-xs font-semibold text-yellow-700/80 dark:text-yellow-500/80 mt-1 relative z-10">{data.awards.top_performer.composite_score?.toFixed(1)} pts</p>
                  </div>
                )}
                {data.awards.most_improved && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.most_improved?.location_id)!)} className="relative overflow-hidden bg-gradient-to-br from-emerald-500/20 to-teal-600/10 backdrop-blur-md border border-emerald-500/30 rounded-xl p-5 cursor-pointer hover:-translate-y-1 hover:shadow-lg transition-all shadow-sm group">
                    <TrendingUp className="absolute -right-4 -bottom-4 h-24 w-24 text-emerald-500/10 transform group-hover:scale-110 transition-transform duration-500" />
                    <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest text-emerald-600 mb-2 relative z-10">
                      Most Improved
                      <InfoHint text={METRIC_HELP['Most Improved']} />
                    </p>
                    <p className="text-base font-black text-foreground truncate relative z-10">{data.awards.most_improved.location_name}</p>
                    <p className="text-xs text-emerald-700 dark:text-emerald-500 font-bold flex items-center mt-1 relative z-10"><TrendingUp className="h-3 w-3 mr-1"/>{data.awards.most_improved.rank_movement} ranks</p>
                  </div>
                )}
                {data.awards.highest_rated && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.highest_rated?.location_id)!)} className="relative overflow-hidden bg-gradient-to-br from-blue-500/10 to-indigo-600/5 backdrop-blur-md border border-blue-500/20 rounded-xl p-5 cursor-pointer hover:-translate-y-1 hover:shadow-lg transition-all shadow-sm group">
                    <Star className="absolute -right-4 -bottom-4 h-24 w-24 text-blue-500/10 transform group-hover:scale-110 transition-transform duration-500" />
                    <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest text-blue-600 mb-2 relative z-10">
                      Highest Rated
                      <InfoHint text={METRIC_HELP['Highest Rated']} />
                    </p>
                    <p className="text-base font-black text-foreground truncate relative z-10">{data.awards.highest_rated.location_name}</p>
                    <p className="text-xs text-blue-700 dark:text-blue-500 font-bold mt-1 flex items-center relative z-10"><Star className="h-3 w-3 text-blue-600 mr-1"/> {data.awards.highest_rated.average_rating_raw?.toFixed(2)}</p>
                  </div>
                )}
                {data.awards.highest_review_velocity && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.highest_review_velocity?.location_id)!)} className="relative overflow-hidden bg-gradient-to-br from-purple-500/10 to-fuchsia-600/5 backdrop-blur-md border border-purple-500/20 rounded-xl p-5 cursor-pointer hover:-translate-y-1 hover:shadow-lg transition-all shadow-sm group">
                    <MessageSquare className="absolute -right-4 -bottom-4 h-24 w-24 text-purple-500/10 transform group-hover:scale-110 transition-transform duration-500" />
                    <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest text-purple-600 mb-2 relative z-10">
                      Review Champion
                      <InfoHint text={METRIC_HELP['Review Champion']} />
                    </p>
                    <p className="text-base font-black text-foreground truncate relative z-10">{data.awards.highest_review_velocity.location_name}</p>
                    <p className="text-xs font-bold text-purple-700 dark:text-purple-500 mt-1 relative z-10">{data.awards.highest_review_velocity.review_velocity_raw} reviews</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Search and Toggle */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-8">
            <div className="relative w-full sm:w-72 group">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground group-focus-within:text-indigo-500 transition-colors" />
              <input
                type="text"
                placeholder="Find a location..."
                className="w-full bg-background/50 backdrop-blur-md border border-border/60 shadow-sm rounded-lg pl-9 pr-4 py-2 text-sm focus:border-indigo-500 hover:border-indigo-500/30 outline-none transition-all"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
            
            <div className="flex items-center bg-background/50 backdrop-blur-md p-1 rounded-lg border border-border/60 shadow-sm">
              <button 
                onClick={() => setViewMode('leaderboard')}
                className={`px-4 py-1.5 text-xs font-extrabold uppercase tracking-wider rounded-md transition-all ${viewMode === 'leaderboard' ? 'bg-indigo-500 text-white shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
              >
                Cards
              </button>
              <button 
                onClick={() => setViewMode('table')}
                className={`px-4 py-1.5 text-xs font-extrabold uppercase tracking-wider rounded-md transition-all ${viewMode === 'table' ? 'bg-indigo-500 text-white shadow-md' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'}`}
              >
                Table
              </button>
            </div>
          </div>

          {isSmallOrg ? (
            <div className="bg-card border border-dashed border-border rounded-xl p-12 text-center mt-6">
              <div className="mx-auto w-16 h-16 bg-muted rounded-full flex items-center justify-center mb-4">
                <MapPin className="h-8 w-8 text-muted-foreground/50" />
              </div>
              <h3 className="text-lg font-bold">Add more locations to unlock leaderboard comparisons.</h3>
              <p className="text-muted-foreground mt-2 max-w-md mx-auto">
                Leaderboards require at least 2 eligible locations. You currently have {data.eligible_locations.length}.
              </p>
            </div>
          ) : (
            <div className="mt-6">
              {viewMode === 'leaderboard' ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                  {filteredEligible.map((loc, idx) => (
                    <div 
                      key={loc.location_id}
                      onClick={() => openDrillIn(loc)}
                      className="glass-panel border-border/60 rounded-xl p-5 hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-pointer relative overflow-hidden group"
                    >
                      {/* Medals for Top 3 */}
                      {loc.rank === 1 && <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-yellow-500/20 to-transparent rounded-bl-3xl flex items-start justify-end p-2 border-l border-b border-yellow-500/10"><Trophy className="h-6 w-6 text-yellow-500 drop-shadow-md transform group-hover:scale-110 transition-transform" /></div>}
                      {loc.rank === 2 && <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-gray-400/20 to-transparent rounded-bl-3xl flex items-start justify-end p-2 border-l border-b border-gray-400/10"><Medal className="h-6 w-6 text-gray-400 drop-shadow-md transform group-hover:scale-110 transition-transform" /></div>}
                      {loc.rank === 3 && <div className="absolute top-0 right-0 w-16 h-16 bg-gradient-to-bl from-orange-600/20 to-transparent rounded-bl-3xl flex items-start justify-end p-2 border-l border-b border-orange-600/10"><Medal className="h-6 w-6 text-orange-600 drop-shadow-md transform group-hover:scale-110 transition-transform" /></div>}
                      
                      <div className="flex items-center gap-4 mb-5">
                        <div className="text-4xl font-black text-muted-foreground/20 w-12 tracking-tighter">#{loc.rank}</div>
                        <div>
                          <h4 className="font-extrabold text-foreground text-lg leading-tight group-hover:text-indigo-500 transition-colors">{loc.location_name}</h4>
                          <div className="mt-1 flex items-center gap-2">
                            <MovementIcon movement={loc.rank_movement} />
                            {loc.cohort && loc.cohort_rank && (
                              <span className="text-[10px] font-extrabold uppercase tracking-wider text-indigo-600 dark:text-indigo-400 bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 rounded-full">
                                {loc.cohort} #{loc.cohort_rank}/{loc.cohort_size}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      
                      <div className="pt-4 border-t border-border/60 flex items-end justify-between">
                        <div>
                          <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground">
                            Composite
                            <InfoHint text={METRIC_HELP['Composite']} />
                          </p>
                          <p className="text-2xl font-black bg-gradient-to-br from-indigo-500 to-purple-500 bg-clip-text text-transparent">{loc.composite_score?.toFixed(1)} <span className="text-xs font-bold text-muted-foreground">pts</span></p>
                        </div>
                        {loc.streak_count >= 3 && (
                          <div className="flex items-center gap-1 bg-gradient-to-r from-orange-500/20 to-red-500/10 border border-orange-500/20 text-orange-600 dark:text-orange-400 px-3 py-1 rounded-full text-[10px] font-extrabold uppercase shadow-sm">
                            🔥 {loc.streak_count} mo streak
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="glass-panel border-border/60 rounded-xl overflow-hidden overflow-x-auto shadow-sm">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted/30 border-b border-border/60">
                      <tr>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground w-16">Rank</th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground w-20">Move</th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground">Location Name</th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground">
                          <span className="flex items-center gap-1.5">Cohort<InfoHint text={METRIC_HELP['Cohort']} /></span>
                        </th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground text-right">
                          <span className="flex items-center justify-end gap-1.5">Score<InfoHint text={METRIC_HELP['Composite']} /></span>
                        </th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground text-right">Rating</th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground text-right">Reviews This Month</th>
                        <th className="px-5 py-4 font-extrabold text-[10px] uppercase tracking-wider text-muted-foreground text-right">Health</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {filteredEligible.map(loc => (
                        <tr 
                          key={loc.location_id} 
                          className="hover:bg-primary/5 cursor-pointer transition-colors group"
                          onClick={() => openDrillIn(loc)}
                        >
                          <td className="px-5 py-4 font-black text-muted-foreground group-hover:text-primary transition-colors">#{loc.rank}</td>
                          <td className="px-5 py-4"><MovementIcon movement={loc.rank_movement} /></td>
                          <td className="px-5 py-4 font-bold text-foreground flex items-center gap-3">
                            <span className="group-hover:text-primary transition-colors">{loc.location_name}</span>
                            {loc.streak_count >= 3 && <span title={`${loc.streak_count} month top streak`} className="bg-orange-500/10 px-1.5 py-0.5 rounded text-[10px] border border-orange-500/20">🔥</span>}
                          </td>
                          <td className="px-5 py-4 text-muted-foreground font-semibold text-xs">
                            {loc.cohort ? <span className="bg-muted px-2 py-1 rounded-md">{loc.cohort} #{loc.cohort_rank}/{loc.cohort_size}</span> : '—'}
                          </td>
                          <td className="px-5 py-4 text-right font-black text-primary">{loc.composite_score?.toFixed(1)}</td>
                          <td className="px-5 py-4 text-right font-semibold">{loc.average_rating_raw?.toFixed(2)}</td>
                          <td className="px-5 py-4 text-right font-semibold">{loc.review_velocity_raw}</td>
                          <td className="px-5 py-4 text-right font-semibold">{loc.health_score_raw?.toFixed(1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* Not Yet Eligible Section */}
          {filteredIneligible.length > 0 && (
            <div className="mt-12 bg-muted/30 border border-border rounded-xl overflow-hidden">
              <button 
                onClick={() => setShowIneligible(!showIneligible)}
                className="w-full px-6 py-4 flex items-center justify-between hover:bg-muted/50 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <Info className="h-5 w-5 text-muted-foreground" />
                  <span className="font-bold text-foreground">Not Yet Eligible ({filteredIneligible.length})</span>
                </div>
                {showIneligible ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
              </button>
              
              {showIneligible && (
                <div className="p-6 pt-0 border-t border-border">
                  <p className="text-sm text-muted-foreground mb-4 mt-4">
                    These locations do not have enough data to be ranked fairly. Work on these requirements to unlock their leaderboard placement.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {filteredIneligible.map(loc => {
                      let reasonText = loc.ineligibility_reason || 'Unknown reason'
                      if (reasonText === 'insufficient_reviews') reasonText = 'Needs at least 5 reviews'
                      if (reasonText === 'missing_health_score') reasonText = 'Missing profile health scan'
                      
                      return (
                        <div key={loc.location_id} className="bg-card border border-border p-4 rounded-lg flex flex-col justify-between">
                          <span className="font-semibold text-sm">{loc.location_name}</span>
                          <span className="text-xs font-bold uppercase tracking-wider text-amber-600 bg-amber-500/10 py-1 px-2 rounded mt-2 w-fit">
                            {reasonText}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Hall of Fame (Streak >= 3) */}
          {!isSmallOrg && data.eligible_locations.filter(l => l.streak_count >= 3).length > 0 && (
            <div className="mt-12">
              <h3 className="text-lg font-bold mb-4 flex items-center gap-2">🔥 Hall of Fame</h3>
              <div className="flex flex-wrap gap-3">
                {data.eligible_locations.filter(l => l.streak_count >= 3).map(loc => (
                  <div key={loc.location_id} className="bg-gradient-to-r from-orange-500/10 to-red-500/5 border border-orange-500/20 px-4 py-2 rounded-full flex items-center gap-2">
                    <span className="font-bold text-sm">{loc.location_name}</span>
                    <span className="text-xs font-bold text-orange-600">{loc.streak_count} mo. streak</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* Drill-In Modal/Drawer (Client Side Rendered Overlay) */}
      {selectedLocation && (
        <div className="fixed inset-0 z-50 flex justify-end bg-background/40 backdrop-blur-sm" onClick={() => setSelectedLocation(null)}>
          <div 
            className="w-full max-w-md md:max-w-xl h-full bg-card/95 backdrop-blur-xl border-l border-border/50 shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-300"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-6 border-b border-border/50 flex items-center justify-between bg-muted/20">
              <div>
                <h2 className="text-2xl font-extrabold text-foreground">{selectedLocation.location_name}</h2>
                <p className="text-sm font-semibold text-muted-foreground mt-1">Rank #{selectedLocation.rank} • {selectedLocation.composite_score?.toFixed(1)} pts</p>
              </div>
              <button onClick={() => setSelectedLocation(null)} className="p-2 hover:bg-muted rounded-full transition-colors">
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
              {drawerLoading ? (
                <div className="flex justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-500"></div>
                </div>
              ) : (
                <>
                  {/* Score Breakdown */}
                  <div>
                    <h3 className="flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-widest text-muted-foreground mb-4">
                      Score Breakdown
                      <InfoHint text={METRIC_HELP['Composite Breakdown']} />
                    </h3>
                    <div className="space-y-3">
                      {Object.entries(selectedLocation.score_contributions).map(([key, val]) => {
                        const labelMap: Record<string, string> = {
                          average_rating: 'Average Rating',
                          review_velocity: 'Reviews This Month',
                          health_score: 'Profile Health',
                          review_volume: 'Total Reviews',
                          response_rate: 'Response Rate'
                        }
                        return (
                          <div key={key} className="flex items-center justify-between bg-muted/30 p-4 rounded-xl border border-border/40 hover:bg-muted/50 transition-colors">
                            <span className="text-sm font-bold text-foreground">{labelMap[key] || key}</span>
                            <span className="text-sm font-black text-indigo-500 dark:text-indigo-400">{val.toFixed(1)} pts</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>

                  {/* How to move up (next best action) */}
                  {nextAction && (
                    <div>
                      <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">How to Move Up</h3>
                      <div className="bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/20 rounded-xl p-5">
                        <div className="flex items-start gap-3">
                          <div className="h-9 w-9 rounded-full bg-primary/15 flex items-center justify-center shrink-0">
                            <TrendingUp className="h-5 w-5 text-primary" />
                          </div>
                          <div className="flex-1">
                            <p className="font-bold text-foreground">{nextAction.headline}</p>
                            <p className="text-sm text-muted-foreground mt-1">{nextAction.detail}</p>
                            <div className="flex flex-wrap gap-4 mt-3 text-sm">
                              <span className="font-semibold text-green-600">
                                +{nextAction.projected_composite_gain.toFixed(1)} pts
                              </span>
                              {nextAction.current_cohort_rank && nextAction.projected_cohort_rank &&
                                nextAction.projected_cohort_rank < nextAction.current_cohort_rank && (
                                <span className="text-muted-foreground">
                                  cohort rank #{nextAction.current_cohort_rank} → <span className="font-semibold text-primary">#{nextAction.projected_cohort_rank}</span>
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Why did I move? */}
                  {explainData && explainData.previous_period && (
                    <div>
                      <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">Why did I move?</h3>
                      <div className="bg-muted/20 border border-border rounded-xl p-5">
                        <div className="flex items-center justify-between mb-4 pb-4 border-b border-border">
                          <div>
                            <p className="text-xs text-muted-foreground font-bold uppercase">{explainData.previous_period}</p>
                            <p className="text-xl font-black text-foreground">#{explainData.from_rank}</p>
                          </div>
                          <TrendingUp className={`h-6 w-6 ${(explainData.rank_movement || 0) > 0 ? 'text-green-500' : ((explainData.rank_movement || 0) < 0 ? 'text-red-500 rotate-180' : 'text-muted-foreground')}`} />
                          <div className="text-right">
                            <p className="text-xs text-muted-foreground font-bold uppercase">{explainData.current_period}</p>
                            <p className="text-xl font-black text-primary">#{explainData.to_rank}</p>
                          </div>
                        </div>
                        
                        <div className="space-y-4">
                          {explainData.score_contribution_deltas && Object.entries(explainData.score_contribution_deltas).map(([key, change]) => {
                            if (change === 0) return null
                            const labelMap: Record<string, string> = {
                              average_rating: 'Rating change',
                              review_velocity: 'Velocity change',
                              health_score: 'Health score change',
                              review_volume: 'Volume change',
                              response_rate: 'Response rate change'
                            }
                            return (
                              <div key={key} className="flex justify-between items-center text-sm">
                                <span className="text-muted-foreground">{labelMap[key] || key}</span>
                                <span className={`font-bold ${change > 0 ? 'text-green-500' : 'text-red-500'}`}>
                                  {change > 0 ? '+' : ''}{change.toFixed(1)} pts
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* History Chart */}
                  {historyData && historyData.length > 1 && (
                    <div>
                      <h3 className="text-xs font-extrabold uppercase tracking-widest text-muted-foreground mb-4">Rank History</h3>
                      <div className="h-64 w-full bg-muted/20 border border-border/40 rounded-xl p-5 shadow-sm">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={historyData}>
                            <defs>
                              <linearGradient id="colorRank" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3}/>
                                <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" strokeOpacity={0.5} />
                            <XAxis 
                              dataKey="period_label" 
                              tickLine={false}
                              axisLine={false}
                              tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))', fontWeight: 600 }}
                              dy={10}
                            />
                            <YAxis 
                              reversed 
                              tickLine={false}
                              axisLine={false}
                              tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))', fontWeight: 600 }}
                              domain={[1, 'dataMax']}
                              allowDecimals={false}
                              width={30}
                            />
                            <Tooltip 
                              contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '12px', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', fontWeight: 'bold' }}
                              itemStyle={{ color: 'hsl(var(--primary))', fontWeight: '900' }}
                              formatter={(value: any, name: any) => [`#${value}`, 'Rank']}
                              labelStyle={{ color: 'hsl(var(--muted-foreground))', marginBottom: '4px', fontSize: '12px' }}
                              cursor={{ stroke: 'hsl(var(--border))', strokeWidth: 1, strokeDasharray: '4 4' }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="rank" 
                              stroke="hsl(var(--primary))" 
                              strokeWidth={4}
                              dot={{ r: 4, fill: 'hsl(var(--card))', strokeWidth: 2, stroke: 'hsl(var(--primary))' }}
                              activeDot={{ r: 7, fill: 'hsl(var(--primary))', stroke: 'hsl(var(--background))', strokeWidth: 2 }}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
