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
  streak_count: number
  most_improved_flag: boolean
  average_rating_raw: number | null
  review_velocity_raw: number | null
  health_score_raw: number | null
  review_volume_raw: number | null
  engagement_growth_raw: number | null
  score_contributions: {
    average_rating?: number
    review_velocity?: number
    health_score?: number
    review_volume?: number
    engagement_growth?: number
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
    highest_growth?: { location_id: number; location_name: string; engagement_growth_raw: number }
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
    setDrawerLoading(true)
    try {
      const [explainRes, historyRes] = await Promise.all([
        api.get<ExplainData>(`/leaderboard/${loc.location_id}/explain?period=${loc.period_label}`),
        api.get<HistoryData[]>(`/leaderboard/${loc.location_id}/history`)
      ])
      setExplainData(explainRes)
      setHistoryData(historyRes)
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
    return <div className="p-8 flex justify-center"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>
  }

  const isSmallOrg = data?.has_data && data.eligible_locations.length < 2

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8">
      
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground flex items-center gap-3">
            <Trophy className="h-8 w-8 text-yellow-500" />
            Leaderboard
          </h1>
          <p className="text-muted-foreground mt-1">Gamified performance ranking across your network.</p>
        </div>
        
        <div className="flex items-center gap-3">
          {isAdmin && (
            <button 
              onClick={handleSync}
              disabled={syncing}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-semibold hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              {syncing ? 'Syncing...' : 'Sync Now'}
            </button>
          )}
          <div className="flex flex-col gap-1.5">
            <select
              className="bg-card border border-input rounded-lg text-sm px-3 py-2 text-foreground outline-none focus:ring-1 focus:ring-primary min-w-[150px]"
              value={selectedPeriod}
              onChange={(e) => setSelectedPeriod(e.target.value)}
            >
              <option value="" disabled>Select Period</option>
              {periods.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </div>
          <button 
            onClick={() => handleExport('csv')}
            disabled={!data?.has_data}
            className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-semibold hover:bg-muted transition-colors disabled:opacity-50"
          >
            <Download className="h-4 w-4" /> CSV
          </button>
          <button 
            onClick={() => handleExport('xlsx')}
            disabled={!data?.has_data}
            className="flex items-center gap-2 px-4 py-2 bg-card border border-border rounded-lg text-sm font-semibold hover:bg-muted transition-colors disabled:opacity-50"
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
            <div className="bg-card border border-border rounded-xl p-5 flex items-center gap-4 shadow-sm">
              <div className="h-12 w-12 rounded-full bg-blue-500/10 flex items-center justify-center shrink-0">
                <Star className="h-6 w-6 text-blue-500" />
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Org Avg Rating</p>
                <p className="text-2xl font-bold text-foreground">{data.organization_benchmark.average_rating_raw?.toFixed(2) || 'N/A'}</p>
              </div>
            </div>
            <div className="bg-card border border-border rounded-xl p-5 flex items-center gap-4 shadow-sm">
              <div className="h-12 w-12 rounded-full bg-green-500/10 flex items-center justify-center shrink-0">
                <MessageSquare className="h-6 w-6 text-green-500" />
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Total Reviews</p>
                <p className="text-2xl font-bold text-foreground">{data.organization_benchmark.total_reviews ?? 'N/A'}</p>
              </div>
            </div>
            <div className="bg-card border border-border rounded-xl p-5 flex items-center gap-4 shadow-sm">
              <div className="h-12 w-12 rounded-full bg-indigo-500/10 flex items-center justify-center shrink-0">
                <Activity className="h-6 w-6 text-indigo-500" />
              </div>
              <div>
                <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Org Health Score</p>
                <p className="text-2xl font-bold text-foreground">{data.organization_benchmark.health_score_raw?.toFixed(1) || 'N/A'}</p>
              </div>
            </div>
          </div>

          {/* Awards Grid - Only render if awards exist */}
          {!isSmallOrg && data.awards && Object.values(data.awards).some(v => v !== undefined && v !== null) && (
            <div>
              <h3 className="text-lg font-bold mb-4 flex items-center gap-2"><Medal className="h-5 w-5 text-indigo-500"/> Monthly Awards</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                {data.awards.top_performer && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.top_performer?.location_id)!)} className="bg-gradient-to-br from-yellow-500/10 to-yellow-600/5 border border-yellow-500/20 rounded-xl p-4 cursor-pointer hover:border-yellow-500/40 transition-colors shadow-sm">
                    <p className="text-[10px] font-extrabold uppercase tracking-widest text-yellow-600 mb-1">Top Performer</p>
                    <p className="text-sm font-bold text-foreground truncate">{data.awards.top_performer.location_name}</p>
                    <p className="text-xs text-muted-foreground mt-1">{data.awards.top_performer.composite_score?.toFixed(1)} pts</p>
                  </div>
                )}
                {data.awards.most_improved && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.most_improved?.location_id)!)} className="bg-gradient-to-br from-green-500/10 to-green-600/5 border border-green-500/20 rounded-xl p-4 cursor-pointer hover:border-green-500/40 transition-colors shadow-sm">
                    <p className="text-[10px] font-extrabold uppercase tracking-widest text-green-600 mb-1">Most Improved</p>
                    <p className="text-sm font-bold text-foreground truncate">{data.awards.most_improved.location_name}</p>
                    <p className="text-xs text-green-600 font-semibold flex items-center mt-1"><TrendingUp className="h-3 w-3 mr-1"/>{data.awards.most_improved.rank_movement} ranks</p>
                  </div>
                )}
                {data.awards.highest_rated && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.highest_rated?.location_id)!)} className="bg-card border border-border rounded-xl p-4 cursor-pointer hover:bg-muted/50 transition-colors shadow-sm">
                    <p className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground mb-1">Highest Rated</p>
                    <p className="text-sm font-bold text-foreground truncate">{data.awards.highest_rated.location_name}</p>
                    <p className="text-xs text-muted-foreground mt-1 flex items-center"><Star className="h-3 w-3 text-yellow-500 mr-1"/> {data.awards.highest_rated.average_rating_raw?.toFixed(2)}</p>
                  </div>
                )}
                {data.awards.highest_review_velocity && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.highest_review_velocity?.location_id)!)} className="bg-card border border-border rounded-xl p-4 cursor-pointer hover:bg-muted/50 transition-colors shadow-sm">
                    <p className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground mb-1">Review Champion</p>
                    <p className="text-sm font-bold text-foreground truncate">{data.awards.highest_review_velocity.location_name}</p>
                    <p className="text-xs text-muted-foreground mt-1">{data.awards.highest_review_velocity.review_velocity_raw} reviews</p>
                  </div>
                )}
                {data.awards.highest_growth && (
                  <div onClick={() => openDrillIn(data.eligible_locations.find(l => l.location_id === data.awards.highest_growth?.location_id)!)} className="bg-card border border-border rounded-xl p-4 cursor-pointer hover:bg-muted/50 transition-colors shadow-sm">
                    <p className="text-[10px] font-extrabold uppercase tracking-widest text-muted-foreground mb-1">Highest Growth</p>
                    <p className="text-sm font-bold text-foreground truncate">{data.awards.highest_growth.location_name}</p>
                    <p className="text-xs text-muted-foreground mt-1">+{data.awards.highest_growth.engagement_growth_raw?.toFixed(1)}%</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Search and Toggle */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 mt-8">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Find a location..."
                className="w-full bg-card border border-input rounded-lg pl-9 pr-4 py-2 text-sm focus:ring-1 focus:ring-primary outline-none"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
            
            <div className="flex items-center bg-muted p-1 rounded-lg border border-border">
              <button 
                onClick={() => setViewMode('leaderboard')}
                className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-md transition-colors ${viewMode === 'leaderboard' ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
              >
                Cards
              </button>
              <button 
                onClick={() => setViewMode('table')}
                className={`px-4 py-1.5 text-xs font-bold uppercase tracking-wider rounded-md transition-colors ${viewMode === 'table' ? 'bg-card shadow-sm text-foreground' : 'text-muted-foreground hover:text-foreground'}`}
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
                      className="bg-card border border-border rounded-xl p-5 hover:shadow-md hover:border-primary/30 transition-all cursor-pointer relative overflow-hidden"
                    >
                      {/* Medals for Top 3 */}
                      {loc.rank === 1 && <div className="absolute top-0 right-0 w-12 h-12 bg-yellow-500/10 rounded-bl-3xl flex items-start justify-end p-2"><Trophy className="h-5 w-5 text-yellow-500" /></div>}
                      {loc.rank === 2 && <div className="absolute top-0 right-0 w-12 h-12 bg-gray-400/10 rounded-bl-3xl flex items-start justify-end p-2"><Medal className="h-5 w-5 text-gray-400" /></div>}
                      {loc.rank === 3 && <div className="absolute top-0 right-0 w-12 h-12 bg-orange-600/10 rounded-bl-3xl flex items-start justify-end p-2"><Medal className="h-5 w-5 text-orange-600" /></div>}
                      
                      <div className="flex items-center gap-4 mb-4">
                        <div className="text-3xl font-black text-muted-foreground/30 w-10">#{loc.rank}</div>
                        <div>
                          <h4 className="font-bold text-foreground text-lg leading-tight">{loc.location_name}</h4>
                          <div className="mt-1"><MovementIcon movement={loc.rank_movement} /></div>
                        </div>
                      </div>
                      
                      <div className="pt-4 border-t border-border flex items-end justify-between">
                        <div>
                          <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Composite</p>
                          <p className="text-xl font-black text-primary">{loc.composite_score?.toFixed(1)} <span className="text-xs font-normal text-muted-foreground">pts</span></p>
                        </div>
                        {loc.streak_count >= 3 && (
                          <div className="flex items-center gap-1 bg-orange-500/10 text-orange-600 px-2 py-1 rounded text-[10px] font-bold uppercase">
                            🔥 {loc.streak_count} mo streak
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-card border border-border rounded-xl overflow-hidden overflow-x-auto shadow-sm">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted/50 border-b border-border">
                      <tr>
                        <th className="px-4 py-3 font-bold text-muted-foreground w-16">Rank</th>
                        <th className="px-4 py-3 font-bold text-muted-foreground w-20">Move</th>
                        <th className="px-4 py-3 font-bold text-muted-foreground">Location Name</th>
                        <th className="px-4 py-3 font-bold text-muted-foreground text-right">Score</th>
                        <th className="px-4 py-3 font-bold text-muted-foreground text-right">Rating</th>
                        <th className="px-4 py-3 font-bold text-muted-foreground text-right">Reviews This Month</th>
                        <th className="px-4 py-3 font-bold text-muted-foreground text-right">Health</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {filteredEligible.map(loc => (
                        <tr 
                          key={loc.location_id} 
                          className="hover:bg-muted/30 cursor-pointer transition-colors"
                          onClick={() => openDrillIn(loc)}
                        >
                          <td className="px-4 py-3 font-black text-muted-foreground">#{loc.rank}</td>
                          <td className="px-4 py-3"><MovementIcon movement={loc.rank_movement} /></td>
                          <td className="px-4 py-3 font-semibold text-foreground flex items-center gap-2">
                            {loc.location_name}
                            {loc.streak_count >= 3 && <span title={`${loc.streak_count} month top streak`}>🔥</span>}
                          </td>
                          <td className="px-4 py-3 text-right font-bold text-primary">{loc.composite_score?.toFixed(1)}</td>
                          <td className="px-4 py-3 text-right">{loc.average_rating_raw?.toFixed(2)}</td>
                          <td className="px-4 py-3 text-right">{loc.review_velocity_raw}</td>
                          <td className="px-4 py-3 text-right">{loc.health_score_raw?.toFixed(1)}</td>
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
        <div className="fixed inset-0 z-50 flex justify-end bg-black/50 backdrop-blur-sm" onClick={() => setSelectedLocation(null)}>
          <div 
            className="w-full max-w-md md:max-w-xl h-full bg-card border-l border-border shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-300"
            onClick={e => e.stopPropagation()}
          >
            <div className="p-6 border-b border-border flex items-center justify-between bg-muted/30">
              <div>
                <h2 className="text-xl font-bold text-foreground">{selectedLocation.location_name}</h2>
                <p className="text-sm text-muted-foreground mt-1">Rank #{selectedLocation.rank} • {selectedLocation.composite_score?.toFixed(1)} pts</p>
              </div>
              <button onClick={() => setSelectedLocation(null)} className="p-2 hover:bg-muted rounded-full">
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 space-y-8">
              {drawerLoading ? (
                <div className="flex justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div></div>
              ) : (
                <>
                  {/* Score Breakdown */}
                  <div>
                    <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">Score Breakdown</h3>
                    <div className="space-y-3">
                      {Object.entries(selectedLocation.score_contributions).map(([key, val]) => {
                        const labelMap: Record<string, string> = {
                          average_rating: 'Average Rating',
                          review_velocity: 'Reviews This Month',
                          health_score: 'Profile Health',
                          review_volume: 'Total Reviews',
                          engagement_growth: 'Engagement Growth'
                        }
                        return (
                          <div key={key} className="flex items-center justify-between bg-muted/40 p-3 rounded-lg border border-border/50">
                            <span className="text-sm font-semibold">{labelMap[key] || key}</span>
                            <span className="text-sm font-bold text-primary">{val.toFixed(1)} pts</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>

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
                              engagement_growth: 'Growth change'
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
                      <h3 className="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">Rank History</h3>
                      <div className="h-64 w-full bg-card border border-border rounded-xl p-4">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={historyData}>
                            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                            <XAxis 
                              dataKey="period_label" 
                              tickLine={false}
                              axisLine={false}
                              tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                              dy={10}
                            />
                            <YAxis 
                              reversed 
                              tickLine={false}
                              axisLine={false}
                              tick={{ fontSize: 12, fill: 'hsl(var(--muted-foreground))' }}
                              domain={[1, 'dataMax']}
                              allowDecimals={false}
                            />
                            <Tooltip 
                              contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '8px' }}
                              itemStyle={{ color: 'hsl(var(--foreground))' }}
                              formatter={(value: any, name: any) => [`#${value}`, 'Rank']}
                              labelStyle={{ color: 'hsl(var(--muted-foreground))', marginBottom: '4px' }}
                            />
                            <Line 
                              type="monotone" 
                              dataKey="rank" 
                              stroke="hsl(var(--primary))" 
                              strokeWidth={3}
                              dot={{ r: 4, fill: 'hsl(var(--card))', strokeWidth: 2 }}
                              activeDot={{ r: 6, fill: 'hsl(var(--primary))' }}
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
