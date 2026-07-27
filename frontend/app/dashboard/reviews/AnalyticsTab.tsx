'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Star, TrendingUp, TrendingDown, Clock, Send, MessageSquare, Gauge, AlertTriangle } from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, Cell,
} from 'recharts'

interface Analytics {
  days: number
  total_reviews: number
  avg_rating: number | null
  replied_count: number
  unreplied_count: number
  response_rate: number | null
  text_count: number
  non_text_count: number
  review_nps: number | null
  promoters: number
  passives: number
  detractors: number
  rating_distribution: Record<string, number>
  sentiment: Record<string, number>
  sentiment_trend: { week: string; positive_pct: number; count: number }[]
  issue_categories: { category: string; count: number }[]
  trend: { week: string; avg_rating: number; count: number }[]
  avg_reply_hours: number | null
  reviews_per_day: number
  prev_period_total: number
  velocity_change_pct: number | null
}

interface LocationOpt { id: number; location_name: string }

const PURPLE = '#7c3aed'
const PERIODS = [
  { days: 30, label: '30d' },
  { days: 90, label: '90d' },
  { days: 180, label: '6mo' },
  { days: 365, label: '1yr' },
]

function fmtWeek(w: string) {
  return new Date(w).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

function StatTile({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="glass-panel p-4 sm:p-5 rounded-2xl">
      <div className="flex items-center gap-2 text-muted-foreground">{icon}
        <span className="text-[11px] uppercase tracking-wider font-bold truncate">{label}</span>
      </div>
      <div className="text-2xl font-extrabold text-foreground mt-2 leading-none">{value}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1.5">{sub}</div>}
    </div>
  )
}

/** Two-segment split bar with counts (never color-alone: labels carry identity). */
function SplitBar({ title, a, b, aLabel, bLabel, aColor = '#10b981', bColor = '#94a3b8', onClickB }: {
  title: string; a: number; b: number; aLabel: string; bLabel: string; aColor?: string; bColor?: string; onClickB?: () => void
}) {
  const total = a + b
  const pctA = total ? (a / total) * 100 : 0
  return (
    <div className="glass-panel p-4 sm:p-5 rounded-2xl">
      <h4 className="text-sm font-semibold text-foreground mb-3">{title}</h4>
      <div className="flex h-3 w-full overflow-hidden rounded-full bg-muted/40">
        {total > 0 && <div className="h-full" style={{ width: `${pctA}%`, backgroundColor: aColor }} />}
        {total > 0 && <div className="h-full flex-1" style={{ backgroundColor: bColor, marginLeft: total && a && b ? 2 : 0 }} />}
      </div>
      <div className="mt-3 flex flex-wrap justify-between gap-2 text-xs">
        <span className="inline-flex items-center gap-1.5 font-medium text-foreground">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: aColor }} />
          {aLabel} · {a} ({total ? Math.round(pctA) : 0}%)
        </span>
        <button onClick={onClickB} disabled={!onClickB}
          className={`inline-flex items-center gap-1.5 font-medium text-foreground ${onClickB ? 'underline decoration-dotted underline-offset-2 hover:text-primary' : ''}`}>
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: bColor }} />
          {bLabel} · {b} ({total ? 100 - Math.round(pctA) : 0}%)
        </button>
      </div>
    </div>
  )
}

export function AnalyticsTab({ locations, initialLocationId, onDrillToUnreplied }: {
  locations: LocationOpt[]
  initialLocationId?: number | ''
  onDrillToUnreplied?: (locationId: number | '') => void
}) {
  const [locId, setLocId] = useState<number | ''>(initialLocationId ?? '')
  const [days, setDays] = useState(90)
  const [data, setData] = useState<Analytics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let dead = false
    setLoading(true); setError(false)
    const qs = new URLSearchParams({ days: String(days) })
    if (locId !== '') qs.set('location_id', String(locId))
    api.get<Analytics>(`/reviews/analytics?${qs}`)
      .then(d => { if (!dead) setData(d) })
      .catch(() => { if (!dead) setError(true) })
      .finally(() => { if (!dead) setLoading(false) })
    return () => { dead = true }
  }, [locId, days])

  const dist = data ? [5, 4, 3, 2, 1].map(star => ({ star: `${star}★`, count: data.rating_distribution[String(star)] ?? 0 })) : []
  const pos = data?.sentiment?.['Positive'] ?? 0
  const neu = data?.sentiment?.['Neutral'] ?? 0
  const neg = data?.sentiment?.['Negative'] ?? 0
  const tagged = pos + neu + neg

  return (
    <div className="space-y-6">
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        <select value={locId} onChange={e => setLocId(e.target.value === '' ? '' : Number(e.target.value))}
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm font-medium min-h-[40px]">
          <option value="">All locations</option>
          {locations.map(l => <option key={l.id} value={l.id}>{l.location_name}</option>)}
        </select>
        <div className="inline-flex items-center gap-1 rounded-full border border-border bg-card p-1 text-xs">
          {PERIODS.map(p => (
            <button key={p.days} onClick={() => setDays(p.days)}
              className={`rounded-full px-3.5 py-1.5 font-semibold transition ${days === p.days ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 animate-pulse">
          {[...Array(5)].map((_, i) => <div key={i} className="h-28 rounded-2xl bg-muted/40" />)}
        </div>
      ) : error || !data ? (
        <div className="glass-panel rounded-2xl p-8 text-center">
          <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Couldn&apos;t load review analytics. Try again in a moment.</p>
        </div>
      ) : data.total_reviews === 0 ? (
        <div className="glass-panel rounded-2xl p-8 text-center text-sm text-muted-foreground">
          No reviews in this period. Try a longer time range.
        </div>
      ) : (
        <>
          {/* KPI tiles */}
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4">
            <StatTile icon={<Star className="h-4 w-4 text-amber-400" />} label="Avg rating"
              value={data.avg_rating != null ? data.avg_rating.toFixed(2) : '—'}
              sub={`${data.total_reviews} reviews in ${data.days}d`} />
            <StatTile icon={<Gauge className="h-4 w-4 text-primary" />} label="Review NPS"
              value={data.review_nps != null ? data.review_nps : '—'}
              sub={`${data.promoters} promoters · ${data.detractors} detractors`} />
            <StatTile icon={<Send className="h-4 w-4 text-emerald-400" />} label="Response rate"
              value={data.response_rate != null ? `${data.response_rate}%` : '—'}
              sub={`${data.unreplied_count} awaiting reply`} />
            <StatTile icon={<Clock className="h-4 w-4 text-sky-400" />} label="Avg reply time"
              value={data.avg_reply_hours != null ? (data.avg_reply_hours >= 48 ? `${(data.avg_reply_hours / 24).toFixed(1)}d` : `${data.avg_reply_hours}h`) : '—'}
              sub="review → owner reply" />
            <StatTile icon={data.velocity_change_pct != null && data.velocity_change_pct < 0
                ? <TrendingDown className="h-4 w-4 text-rose-400" /> : <TrendingUp className="h-4 w-4 text-emerald-400" />}
              label="Review velocity" value={`${data.reviews_per_day}/day`}
              sub={data.velocity_change_pct != null
                ? `${data.velocity_change_pct > 0 ? '+' : ''}${data.velocity_change_pct}% vs previous ${data.days}d`
                : `no reviews in previous ${data.days}d`} />
          </div>

          {/* Rating trend + distribution */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
            <div className="glass-panel p-4 sm:p-6 rounded-2xl min-w-0">
              <h4 className="text-sm font-semibold text-foreground mb-4">Average rating by week</h4>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={data.trend} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" strokeOpacity={0.07} />
                  <XAxis dataKey="week" tickFormatter={fmtWeek} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
                  <YAxis domain={[0, 5]} ticks={[1, 2, 3, 4, 5]} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
                  <Tooltip labelFormatter={(w: any) => fmtWeek(String(w))} formatter={(v: any, name: any) => name === 'avg_rating' ? [v, 'Avg rating'] : [v, 'Reviews']} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                  <Line type="monotone" dataKey="avg_rating" stroke={PURPLE} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="glass-panel p-4 sm:p-6 rounded-2xl min-w-0">
              <h4 className="text-sm font-semibold text-foreground mb-4">Rating distribution</h4>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={dist} layout="vertical" margin={{ top: 0, right: 30, bottom: 0, left: -10 }}>
                  <XAxis type="number" allowDecimals={false} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
                  <YAxis type="category" dataKey="star" width={40} tick={{ fontSize: 12 }} stroke="currentColor" strokeOpacity={0.3} />
                  <Tooltip formatter={(v: any) => [v, 'Reviews']} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                  <Bar dataKey="count" fill={PURPLE} radius={[0, 4, 4, 0]} isAnimationActive={false} label={{ position: 'right', fontSize: 11, fill: 'currentColor' }} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Volume trend */}
          <div className="glass-panel p-4 sm:p-6 rounded-2xl min-w-0">
            <h4 className="text-sm font-semibold text-foreground mb-4">Review volume by week</h4>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={data.trend} margin={{ top: 5, right: 10, bottom: 0, left: -25 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" strokeOpacity={0.07} />
                <XAxis dataKey="week" tickFormatter={fmtWeek} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
                <Tooltip labelFormatter={(w: any) => fmtWeek(String(w))} formatter={(v: any) => [v, 'Reviews']} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="count" fill={PURPLE} radius={[4, 4, 0, 0]} isAnimationActive={false} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Splits */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
            <SplitBar title="Replied vs awaiting reply" a={data.replied_count} b={data.unreplied_count}
              aLabel="Replied" bLabel="Awaiting reply" aColor="#10b981" bColor="#f59e0b"
              onClickB={data.unreplied_count > 0 && onDrillToUnreplied ? () => onDrillToUnreplied(locId) : undefined} />
            <SplitBar title="Text vs rating-only reviews" a={data.text_count} b={data.non_text_count}
              aLabel="With text" bLabel="Rating only" aColor={PURPLE} bColor="#94a3b8" />
          </div>

          {/* Sentiment */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
            <div className="glass-panel p-4 sm:p-5 rounded-2xl">
              <h4 className="text-sm font-semibold text-foreground mb-3">Sentiment (AI-tagged)</h4>
              {tagged === 0 ? (
                <p className="text-xs text-muted-foreground">No sentiment-tagged reviews in this period yet.</p>
              ) : (
                <>
                  <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted/40">
                    <div className="h-full" style={{ width: `${(pos / tagged) * 100}%`, backgroundColor: '#10b981' }} />
                    <div className="h-full" style={{ width: `${(neu / tagged) * 100}%`, backgroundColor: '#94a3b8' }} />
                    <div className="h-full" style={{ width: `${(neg / tagged) * 100}%`, backgroundColor: '#ef4444' }} />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs font-medium text-foreground">
                    <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />Positive · {pos} ({Math.round((pos / tagged) * 100)}%)</span>
                    <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-slate-400" />Neutral · {neu}</span>
                    <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-full bg-red-500" />Negative · {neg}</span>
                  </div>
                  {data.sentiment_trend.length > 1 && (
                    <ResponsiveContainer width="100%" height={140}>
                      <LineChart data={data.sentiment_trend} margin={{ top: 15, right: 10, bottom: 0, left: -20 }}>
                        <XAxis dataKey="week" tickFormatter={fmtWeek} tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3} />
                        <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3} />
                        <Tooltip labelFormatter={(w: any) => fmtWeek(String(w))} formatter={(v: any) => [`${v}%`, 'Positive']} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                        <Line type="monotone" dataKey="positive_pct" stroke="#10b981" strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  )}
                </>
              )}
            </div>
            <div className="glass-panel p-4 sm:p-5 rounded-2xl">
              <h4 className="text-sm font-semibold text-foreground mb-3 flex items-center gap-2">
                <MessageSquare className="h-4 w-4 text-primary" /> What customers mention (AI-tagged)
              </h4>
              {data.issue_categories.length === 0 ? (
                <p className="text-xs text-muted-foreground">No tagged topics in this period yet.</p>
              ) : (
                <div className="space-y-2">
                  {data.issue_categories.map(ic => {
                    const max = data.issue_categories[0].count || 1
                    return (
                      <div key={ic.category} className="flex items-center gap-3">
                        <span className="w-32 shrink-0 truncate text-xs font-medium text-foreground">{ic.category}</span>
                        <div className="flex-1 h-2.5 rounded-full bg-muted/40 overflow-hidden">
                          <div className="h-full rounded-full" style={{ width: `${(ic.count / max) * 100}%`, backgroundColor: PURPLE }} />
                        </div>
                        <span className="w-8 text-right text-xs tabular-nums text-muted-foreground">{ic.count}</span>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          <p className="text-[11px] text-muted-foreground">
            Review NPS is derived from star ratings (5★ = promoter, 4★ = passive, ≤3★ = detractor) — a proxy, not a surveyed NPS.
            Trends cover reviews received in the selected period across {locId === '' ? 'all your locations' : 'the selected location'}.
          </p>
        </>
      )}
    </div>
  )
}
