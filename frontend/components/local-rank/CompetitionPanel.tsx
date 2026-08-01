'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import React, { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { Star, Plus, Trash2, TrendingUp, TrendingDown, Users, Info, MapPin } from 'lucide-react'
import { toast } from 'sonner'
import { ResponsiveContainer, BarChart, Bar, LineChart, Line, ScatterChart, Scatter, CartesianGrid, XAxis, YAxis, Tooltip, Cell, LabelList } from 'recharts'
import { loadLeaflet, LocalRankMap, RankCell } from './LocalRankMap'
import { InfoHint } from '@/components/ui/InfoHint'
import { METRIC_HELP } from '@/lib/metric-help'

interface Snapshot {
  captured_at: string
  keyword: string | null
  rating: number | null
  review_count: number | null
  photo_count: number | null
  best_rank: number | null
  avg_rank: number | null
  appearances: number | null
  total_cells: number | null
}

interface Competitor {
  id: number
  place_id: string
  name: string
  category: string | null
  address: string | null
  lat: number | null
  lng: number | null
  distance_km: number | null
  is_claimed: boolean | null
  domain: string | null
  price_level: string | null
  snapshots: Snapshot[]
}

interface KeywordWinner {
  keyword: string
  leader: string | null
  your_avg_rank: number | null
  your_solv: number | null
  scanned_at: string
}

interface OwnTrendPoint { captured_at: string; keyword: string; solv: number; found_count?: number | null; total_cells?: number | null }

interface MarketPoint {
  name: string
  avg_rank: number
  reviews: number | null
  photos: number | null
  rating: number | null
  is_you: boolean
}

interface CompetitorsResponse {
  own: { name: string; lat: number | null; lng: number | null; rating: number | null; reviews: number | null }
  own_trend: OwnTrendPoint[]
  competitors: Competitor[]
  limit: number
  is_pro: boolean
  keyword_winners: KeywordWinner[]
  market: MarketPoint[]
}

interface Suggestion {
  place_id: string
  name: string
  category: string | null
  address: string | null
  rating: number | null
  reviews: number | null
  appearances: number
  best_rank: number | null
  lat: number | null
  lng: number | null
}

const PURPLE = '#7c3aed'

const PRICE_LABEL: Record<string, string> = {
  free: 'Free', inexpensive: '₹', moderate: '₹₹', expensive: '₹₹₹', very_expensive: '₹₹₹₹',
}

/** Change between the previous scan's snapshot and the latest one. */
function Delta({ prev, last, invert = false }: { prev: number | null | undefined, last: number | null | undefined, invert?: boolean }) {
  if (prev == null || last == null || prev === last) return null
  const up = last > prev
  const good = invert ? !up : up
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-bold ${good ? 'text-emerald-500' : 'text-rose-500'}`}
      title="change since previous scan">
      <Icon className="h-3 w-3" />{up ? '+' : ''}{Math.round((last - prev) * 100) / 100}
    </span>
  )
}

function fmtDistance(km: number | null): string {
  if (km == null) return '—'
  return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`
}

/** Leaflet map: own store (purple) + competitors (gray) markers. */
function CompetitorMap({ own, competitors }: { own: CompetitorsResponse['own'], competitors: Competitor[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const points = competitors.filter(c => c.lat != null && c.lng != null)
  const hasOwn = own.lat != null && own.lng != null

  useEffect(() => {
    if (!ref.current || (!hasOwn && points.length === 0)) return
    let map: any
    loadLeaflet().then(L => {
      if (!ref.current) return
      map = L.map(ref.current, { scrollWheelZoom: false })
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
      }).addTo(map)
      const esc = (s: string) => s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string))
      const bounds: any[] = []
      // Labeled pill markers: a colored dot + the business name in a soft chip.
      const pill = (label: string, opts: { bg: string, fg: string, dot: string, bold?: boolean }) => L.divIcon({
        className: '', iconAnchor: [8, 8],
        html: `<div style="display:inline-flex;align-items:center;gap:5px;padding:3px 9px 3px 5px;border-radius:9999px;` +
          `background:${opts.bg};color:${opts.fg};font:${opts.bold ? '700' : '600'} 11px/1.2 system-ui,sans-serif;` +
          `white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.25);border:1px solid rgba(0,0,0,.08)">` +
          `<span style="width:9px;height:9px;border-radius:9999px;background:${opts.dot};flex:none"></span>${label}</div>`,
      })
      const shorten = (s: string) => s.length > 20 ? s.slice(0, 19) + '…' : s
      if (hasOwn) {
        L.marker([own.lat, own.lng], { icon: pill(esc(shorten(own.name)), { bg: PURPLE, fg: 'white', dot: 'white', bold: true }), zIndexOffset: 1000 })
          .addTo(map).bindPopup(`<b>${esc(own.name)}</b><br/>Your store`)
        bounds.push([own.lat, own.lng])
      }
      points.forEach(c => {
        const last = c.snapshots[c.snapshots.length - 1]
        L.marker([c.lat, c.lng], { icon: pill(esc(shorten(c.name)), { bg: 'white', fg: '#0f172a', dot: '#64748b' }) })
          .addTo(map)
          .bindPopup(`<b>${esc(c.name)}</b><br/>${last?.rating != null ? `★ ${last.rating} · ${last.review_count ?? '?'} reviews<br/>` : ''}${c.distance_km != null ? `${fmtDistance(c.distance_km)} away` : ''}`)
        bounds.push([c.lat, c.lng])
      })
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 })
    }).catch(() => { /* map is progressive enhancement */ })
    return () => { if (map) map.remove() }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [own.lat, own.lng, JSON.stringify(points.map(p => [p.lat, p.lng]))])

  if (!hasOwn && points.length === 0) return null
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5">
      <h3 className="text-sm font-semibold text-foreground mb-1 flex items-center gap-2">
        <MapPin className="h-4 w-4 text-primary" /> Competitor locations
      </h3>
      <p className="text-xs text-muted-foreground mb-3">Your store is the purple label; competitors are white.</p>
      <div ref={ref} className="h-72 w-full rounded-xl overflow-hidden z-0" />
    </div>
  )
}

/** Horizontal bars: your rating vs each competitor's latest rating. */
function RatingComparison({ own, competitors }: { own: CompetitorsResponse['own'], competitors: Competitor[] }) {
  const rows = [
    ...(own.rating != null ? [{ name: own.name, rating: Math.round(own.rating * 10) / 10, you: true }] : []),
    ...competitors.flatMap(c => {
      const last = c.snapshots[c.snapshots.length - 1]
      return last?.rating != null ? [{ name: c.name, rating: last.rating, you: false }] : []
    }),
  ].sort((a, b) => b.rating - a.rating)
  if (rows.length < 2) return null
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5 min-w-0">
      <h3 className="text-sm font-semibold text-foreground mb-1">Rating comparison</h3>
      <p className="text-xs text-muted-foreground mb-3">Latest known rating; purple bar is you.</p>
      <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 44)}>
        <BarChart data={rows} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 8 }}>
          <XAxis type="number" domain={[0, 5]} ticks={[1, 2, 3, 4, 5]} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
          <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 11 }} stroke="currentColor" strokeOpacity={0.3} />
          <Tooltip formatter={(v: any) => [v, 'Rating']} contentStyle={{ borderRadius: 8, fontSize: 12 }} />
          <Bar dataKey="rating" radius={[0, 4, 4, 0]} isAnimationActive={false}>
            {rows.map((r, i) => <Cell key={i} fill={r.you ? PURPLE : '#94a3b8'} />)}
            <LabelList dataKey="rating" position="right" style={{ fontSize: 11, fill: 'currentColor' }} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

const TREND_COLORS = ['#7c3aed', '#0d9488', '#ea580c', '#0284c7', '#db2777']

/** Top strip: where you stand at a glance. */
function SummaryStrip({ own, competitors }: { own: CompetitorsResponse['own'], competitors: Competitor[] }) {
  const latest = (c: Competitor) => c.snapshots[c.snapshots.length - 1]
  const ratings = [
    ...(own.rating != null ? [{ you: true, v: own.rating }] : []),
    ...competitors.flatMap(c => latest(c)?.rating != null ? [{ you: false, v: latest(c)!.rating! }] : []),
  ].sort((a, b) => b.v - a.v)
  const ratingPos = ratings.findIndex(r => r.you) + 1
  const maxCompReviews = Math.max(0, ...competitors.map(c => latest(c)?.review_count ?? 0))
  const reviewGap = own.reviews != null ? own.reviews - maxCompReviews : null
  const nearest = competitors.filter(c => c.distance_km != null).sort((a, b) => a.distance_km! - b.distance_km!)[0]
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
      <div className="glass-panel rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] uppercase tracking-wider font-bold text-muted-foreground">Rating position</div>
        <div className="text-2xl font-extrabold text-foreground mt-1.5">{ratingPos > 0 ? `#${ratingPos}` : '—'} <span className="text-sm text-muted-foreground font-medium">of {ratings.length}</span></div>
        <div className="text-xs text-muted-foreground mt-1">{ratingPos === 1 ? 'Highest rated in your tracked set' : 'among you + tracked competitors'}</div>
      </div>
      <div className="glass-panel rounded-2xl p-4 sm:p-5">
        <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider font-bold text-muted-foreground">
          Review lead
          <InfoHint text={METRIC_HELP['Review lead']} />
        </div>
        <div className={`text-2xl font-extrabold mt-1.5 ${reviewGap != null && reviewGap < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
          {reviewGap != null ? `${reviewGap > 0 ? '+' : ''}${reviewGap}` : '—'}
        </div>
        <div className="text-xs text-muted-foreground mt-1">{reviewGap != null && reviewGap < 0 ? 'behind the review leader' : 'vs the biggest competitor'}</div>
      </div>
      <div className="glass-panel rounded-2xl p-4 sm:p-5">
        <div className="text-[11px] uppercase tracking-wider font-bold text-muted-foreground">Closest competitor</div>
        <div className="text-2xl font-extrabold text-foreground mt-1.5">{nearest ? fmtDistance(nearest.distance_km) : '—'}</div>
        <div className="text-xs text-muted-foreground mt-1 truncate">{nearest ? nearest.name : 'no location data yet'}</div>
      </div>
    </div>
  )
}

/** Share of voice over time: your grid visibility % vs each competitor's. */
function SovTrend({ own, ownTrend, competitors }: { own: CompetitorsResponse['own'], ownTrend: OwnTrendPoint[], competitors: Competitor[] }) {
  const byDate: Record<string, any> = {}
  ownTrend.forEach(p => {
    const d = new Date(p.captured_at).toISOString().slice(0, 10)
    // Appearance share, matching what competitor snapshots record. Older scans
    // predate found_count, so fall back to solv (top-3 share) for those points.
    const pct = p.total_cells ? Math.round(((p.found_count ?? 0) / p.total_cells) * 100) : Math.round(p.solv)
    byDate[d] = { ...(byDate[d] || { date: d }), You: pct }
  })
  const tracked = competitors.filter(c => c.snapshots.some(s => s.appearances != null && s.total_cells)).slice(0, 4)
  tracked.forEach(c => c.snapshots.forEach(s => {
    if (!s.appearances || !s.total_cells) return
    const d = new Date(s.captured_at).toISOString().slice(0, 10)
    byDate[d] = { ...(byDate[d] || { date: d }), [c.name]: Math.round((s.appearances / s.total_cells) * 100) }
  }))
  const series = Object.values(byDate).sort((a: any, b: any) => a.date.localeCompare(b.date))
  if (series.length < 2) return null
  const names = ['You', ...tracked.map(c => c.name)]
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5 min-w-0">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-1">
        Share of local voice
        <InfoHint text={METRIC_HELP['Share of local voice']} />
      </h3>
      <p className="text-xs text-muted-foreground mb-3">% of grid points where each business appears, per scan.</p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -20 }}>
          <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3}
            tickFormatter={(d: any) => new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3} unit="%" />
          <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} formatter={(v: any) => [`${v}%`]} />
          {names.map((n, i) => (
            <Line key={n} type="monotone" dataKey={n} stroke={TREND_COLORS[i]} strokeWidth={n === 'You' ? 3 : 2} dot={{ r: 3 }} isAnimationActive={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {names.map((n, i) => (
          <span key={n} className="inline-flex items-center gap-1.5 font-medium text-foreground">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: TREND_COLORS[i] }} />{n}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Side-by-side grid comparison: your heatmap vs the competitor's, latest scan. */
function GridCompare({ locationId, competitor, ownName }: { locationId: number, competitor: Competitor, ownName: string }) {
  const { data, isLoading, isError } = useQuery<{ keyword: string, scanned_at: string, your_cells: RankCell[], competitor_cells: RankCell[] }>({
    queryKey: ['competitor-heatmap', locationId, competitor.id],
    queryFn: () => api.get(`/locations/${locationId}/competitors/${competitor.id}/heatmap`),
  })
  if (isLoading) return <div className="h-56 animate-pulse rounded-xl bg-muted/40 my-3" />
  if (isError || !data) return <p className="text-xs text-muted-foreground py-3">Couldn&apos;t load the grid comparison.</p>
  return (
    <div className="py-3">
      <p className="text-xs text-muted-foreground mb-2">Grid ranks for &ldquo;{data.keyword}&rdquo; — {new Date(data.scanned_at).toLocaleDateString()}. Green = top 3.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="min-w-0">
          <div className="text-xs font-bold text-primary mb-1.5">{ownName} (you)</div>
          <LocalRankMap cells={data.your_cells} preview />
        </div>
        <div className="min-w-0">
          <div className="text-xs font-bold text-foreground mb-1.5">{competitor.name}</div>
          <LocalRankMap cells={data.competitor_cells} preview />
        </div>
      </div>
    </div>
  )
}

/** Badges shared by the table row and the mobile card. */
function CompetitorBadges({ c }: { c: Competitor }) {
  return (
    <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
      {c.category && <span>{c.category}</span>}
      {PRICE_LABEL[c.price_level ?? ''] && <span className="rounded bg-muted/60 px-1.5 py-0.5 font-semibold">{PRICE_LABEL[c.price_level ?? '']}</span>}
      {c.domain ? (
        <span className="rounded bg-sky-500/10 px-1.5 py-0.5 font-semibold text-sky-600 dark:text-sky-400">has website</span>
      ) : c.is_claimed != null ? (
        <span className="rounded bg-muted/60 px-1.5 py-0.5 font-semibold">no website</span>
      ) : null}
      {c.is_claimed === false && (
        <span className="rounded bg-amber-500/10 px-1.5 py-0.5 font-semibold text-amber-600 dark:text-amber-400" title="This profile is unclaimed — an easy competitor to outrank">unclaimed</span>
      )}
    </div>
  )
}

/** Pro: reviews/week velocity, photo change, and what it takes to overtake each competitor. */
function ProVelocityAndGaps({ own, competitors }: { own: CompetitorsResponse['own'], competitors: Competitor[] }) {
  const rows = competitors.map(c => {
    const first = c.snapshots[0]
    const last = c.snapshots[c.snapshots.length - 1]
    let perWeek: number | null = null
    if (first && last && first !== last && first.review_count != null && last.review_count != null) {
      const days = (new Date(last.captured_at).getTime() - new Date(first.captured_at).getTime()) / 86400000
      if (days >= 1) perWeek = Math.round(((last.review_count - first.review_count) / days) * 7 * 10) / 10
    }
    const photoDelta = (first?.photo_count != null && last?.photo_count != null && first !== last)
      ? last.photo_count - first.photo_count : null
    const reviewGap = (own.reviews != null && last?.review_count != null && last.review_count > own.reviews)
      ? last.review_count - own.reviews + 1 : null
    const ratingGap = (own.rating != null && last?.rating != null && last.rating > own.rating)
      ? Math.round((last.rating - own.rating) * 10) / 10 : null
    return { c, last, perWeek, photoDelta, reviewGap, ratingGap }
  })
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
        Momentum & gaps
        <InfoHint text={METRIC_HELP['Momentum & gaps']} />
      </h3>
      <div className="space-y-3">
        {rows.map(({ c, perWeek, photoDelta, reviewGap, ratingGap }) => (
          <div key={c.id} className="rounded-xl border border-border/50 bg-muted/10 px-4 py-3">
            <div className="text-sm font-semibold text-foreground">{c.name}</div>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>{perWeek != null ? `${perWeek > 0 ? '+' : ''}${perWeek} reviews/week` : 'velocity: needs 2+ scans over time'}</span>
              {photoDelta != null && photoDelta !== 0 && <span>{photoDelta > 0 ? '+' : ''}{photoDelta} photos since first scan</span>}
              {reviewGap != null && <span className="text-amber-500 font-medium">{reviewGap} more reviews to pass them</span>}
              {ratingGap != null && <span className="text-amber-500 font-medium">rating {ratingGap} below theirs</span>}
              {reviewGap == null && ratingGap == null && <span className="text-emerald-500 font-medium">you lead on rating & reviews</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Pro: each competitor's average rank across scans (lower is better). */
function ProRankTrend({ competitors }: { competitors: Competitor[] }) {
  const tracked = competitors.filter(c => c.snapshots.filter(s => s.avg_rank != null).length >= 2).slice(0, 5)
  if (tracked.length === 0) return null
  // Merge snapshots onto a shared date axis
  const byDate: Record<string, any> = {}
  tracked.forEach(c => c.snapshots.forEach(s => {
    if (s.avg_rank == null) return
    const d = new Date(s.captured_at).toISOString().slice(0, 10)
    byDate[d] = { ...(byDate[d] || { date: d }), [c.name]: s.avg_rank }
  }))
  const series = Object.values(byDate).sort((a: any, b: any) => a.date.localeCompare(b.date))
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5 min-w-0">
      <h3 className="text-sm font-semibold text-foreground mb-1">Competitor rank trend</h3>
      <p className="text-xs text-muted-foreground mb-3">Average grid rank per scan — lower is better.</p>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={series} margin={{ top: 5, right: 10, bottom: 0, left: -25 }}>
          <XAxis dataKey="date" tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3}
            tickFormatter={(d: any) => new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} />
          <YAxis reversed domain={[1, 'auto']} allowDecimals={false} tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3} />
          <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
          {tracked.map((c, i) => (
            <Line key={c.id} type="monotone" dataKey={c.name} stroke={TREND_COLORS[i]} strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} connectNulls />
          ))}
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {tracked.map((c, i) => (
          <span key={c.id} className="inline-flex items-center gap-1.5 font-medium text-foreground">
            <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: TREND_COLORS[i] }} />{c.name}
          </span>
        ))}
      </div>
    </div>
  )
}

/** Pro: who owns the #1 spot per scanned keyword. */
function ProKeywordWinners({ winners, ownName }: { winners: KeywordWinner[], ownName: string }) {
  if (winners.length === 0) return null
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5">
      <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground mb-3">
        Who wins each keyword
        <InfoHint text={METRIC_HELP['Who wins each keyword']} />
      </h3>
      <div className="space-y-2">
        {winners.map(w => {
          const youLead = w.leader != null && (w.leader.toLowerCase().includes(ownName.toLowerCase()) || ownName.toLowerCase().includes(w.leader.toLowerCase()))
          return (
            <div key={w.keyword} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-border/50 bg-muted/10 px-4 py-2.5 text-sm">
              <span className="font-medium text-foreground">&ldquo;{w.keyword}&rdquo;</span>
              <span className="flex items-center gap-3 text-xs text-muted-foreground">
                {w.leader && (
                  <span>#1: <span className={`font-semibold ${youLead ? 'text-emerald-500' : 'text-foreground'}`}>{youLead ? 'You' : w.leader}</span></span>
                )}
                {w.your_avg_rank != null && <span>your avg #{Math.round(w.your_avg_rank * 10) / 10}</span>}
                {w.your_solv != null && <span>{Math.round(w.your_solv)}% visibility</span>}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/** Pro: does having more reviews/photos correlate with ranking better in this market? */
function RankCorrelation({ market, metric, label }: { market: MarketPoint[], metric: 'reviews' | 'photos', label: string }) {
  const pts = market.filter(m => m[metric] != null)
  if (pts.length < 3) return null
  return (
    <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5 min-w-0">
      <h3 className="text-sm font-semibold text-foreground mb-1">{label} vs ranking</h3>
      <p className="text-xs text-muted-foreground mb-3">Each dot is a business in your latest scan — purple is you. Higher dots rank better.</p>
      <ResponsiveContainer width="100%" height={220}>
        <ScatterChart margin={{ top: 10, right: 15, bottom: 5, left: -15 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="currentColor" strokeOpacity={0.07} />
          <XAxis type="number" dataKey={metric} name={label} tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3} />
          <YAxis type="number" dataKey="avg_rank" name="Avg rank" reversed domain={[1, 'auto']}
            allowDecimals={false} tick={{ fontSize: 10 }} stroke="currentColor" strokeOpacity={0.3} />
          <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} cursor={{ strokeDasharray: '3 3' }}
            formatter={(v: any, n: any) => [v, n]}
            labelFormatter={() => ''}
            content={({ payload }: any) => {
              const p = payload?.[0]?.payload
              if (!p) return null
              return (
                <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
                  <div className="font-semibold text-foreground">{p.name}{p.is_you ? ' (you)' : ''}</div>
                  <div className="text-muted-foreground mt-0.5">{label}: {p[metric]} · avg rank #{p.avg_rank}{p.rating != null ? ` · ★ ${p.rating}` : ''}</div>
                </div>
              )
            }} />
          <Scatter data={pts} isAnimationActive={false}>
            {pts.map((p, i) => (
              <Cell key={i} fill={p.is_you ? PURPLE : '#94a3b8'} r={p.is_you ? 8 : 5} stroke={p.is_you ? PURPLE : 'none'} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

function ProTeaser() {
  return (
    <div className="glass-panel rounded-2xl border-primary/30 border-dashed shadow-sm p-6 text-center">
      <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
        <TrendingUp className="h-5 w-5" />
      </div>
      <h3 className="text-sm font-bold text-foreground">Unlock competitor intelligence with Pro</h3>
      <p className="mx-auto mt-1 max-w-md text-xs text-muted-foreground">
        Review velocity, gaps to overtake each competitor, rank trends over time, keyword winners — and track up to 10 competitors per location.
      </p>
      <a href="/dashboard/settings/billing" className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-bold text-primary-foreground hover:opacity-90 transition">
        Upgrade to Pro
      </a>
    </div>
  )
}

export function CompetitionPanel({ locationId }: { locationId: number }) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)

  const { data, isLoading } = useQuery<CompetitorsResponse>({
    queryKey: ['competitors', locationId],
    queryFn: () => api.get(`/locations/${locationId}/competitors`),
  })
  const { data: suggestionList = [] } = useQuery<Suggestion[]>({
    queryKey: ['competitor-suggestions', locationId],
    queryFn: () => api.get(`/locations/${locationId}/competitors/suggestions`),
  })
  const competitors = data?.competitors ?? []
  const own = data?.own
  const limit = data?.limit ?? 3
  const isPro = data?.is_pro ?? false

  const addMut = useMutation({
    mutationFn: (s: Suggestion) => api.post(`/locations/${locationId}/competitors`, {
      place_id: s.place_id, name: s.name, category: s.category, address: s.address, lat: s.lat, lng: s.lng,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['competitors', locationId] })
      qc.invalidateQueries({ queryKey: ['competitor-suggestions', locationId] })
      toast.success('Competitor added — snapshots backfilled from your past scans.')
    },
    onError: (e: any) => toast.error(e?.message || 'Could not add competitor'),
    onSettled: () => setAdding(null),
  })
  const delMut = useMutation({
    mutationFn: (id: number) => api.delete(`/locations/${locationId}/competitors/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['competitors', locationId] })
      qc.invalidateQueries({ queryKey: ['competitor-suggestions', locationId] })
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-2 rounded-xl border border-primary/20 bg-primary/5 p-3.5 text-xs text-muted-foreground">
        <Info className="h-4 w-4 text-primary shrink-0 mt-0.5" />
        <span>Competitor data is captured free from your geo-grid rank scans — every new scan adds a snapshot for each tracked competitor. Deltas compare your latest scan with the previous one.</span>
      </div>

      {/* At-a-glance position */}
      {own && competitors.length > 0 && <SummaryStrip own={own} competitors={competitors} />}

      {/* Tracked competitors */}
      <div className="glass-panel rounded-2xl border-border/40 shadow-sm overflow-hidden">
        <div className="flex items-center justify-between p-4 sm:p-5 border-b border-border/50">
          <h3 className="text-sm font-semibold text-foreground flex items-center gap-2">
            <Users className="h-4 w-4 text-primary" /> Tracked competitors ({competitors.length}/{limit})
          </h3>
        </div>
        {isLoading ? (
          <div className="p-6 animate-pulse space-y-2">{[1, 2, 3].map(i => <div key={i} className="h-10 rounded-lg bg-muted/40" />)}</div>
        ) : competitors.length === 0 ? (
          <p className="p-6 text-sm text-muted-foreground">
            No competitors tracked yet. Add them from the suggestions below — or run a rank scan first if the list is empty.
          </p>
        ) : (
          <>
          {/* Mobile: stacked cards */}
          <div className="md:hidden divide-y divide-border/30">
            {own && (
              <div className="p-4 bg-primary/[0.04]">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-bold text-foreground text-sm">{own.name} <span className="ml-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold text-primary">YOU</span></span>
                  <span className="inline-flex items-center gap-1 text-sm font-medium"><Star className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />{own.rating != null ? own.rating.toFixed(1) : '—'} · {own.reviews ?? '—'} reviews</span>
                </div>
              </div>
            )}
            {competitors.map(c => {
              const last = c.snapshots[c.snapshots.length - 1]
              const prev = c.snapshots.length > 1 ? c.snapshots[c.snapshots.length - 2] : undefined
              return (
                <div key={c.id} className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-semibold text-foreground text-sm">{c.name}</div>
                      <CompetitorBadges c={c} />
                    </div>
                    <button onClick={() => delMut.mutate(c.id)} aria-label={`Remove ${c.name}`}
                      className="p-2 -m-1 rounded-lg text-muted-foreground hover:text-rose-500 active:bg-rose-500/10 shrink-0">
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                  <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                    <div><div className="text-[10px] uppercase font-bold text-muted-foreground">Rating</div>
                      <div className="text-sm font-semibold mt-0.5">{last?.rating != null ? last.rating.toFixed(1) : '—'} <Delta prev={prev?.rating} last={last?.rating} /></div></div>
                    <div><div className="text-[10px] uppercase font-bold text-muted-foreground">Reviews</div>
                      <div className="text-sm font-semibold mt-0.5">{last?.review_count ?? '—'} <Delta prev={prev?.review_count} last={last?.review_count} /></div></div>
                    <div><div className="text-[10px] uppercase font-bold text-muted-foreground">Rank</div>
                      <div className="text-sm font-semibold mt-0.5">{last?.best_rank != null ? `#${last.best_rank}` : '—'} <Delta prev={prev?.best_rank} last={last?.best_rank} invert /></div></div>
                    <div><div className="text-[10px] uppercase font-bold text-muted-foreground">Distance</div>
                      <div className="text-sm font-semibold mt-0.5">{fmtDistance(c.distance_km)}</div></div>
                  </div>
                  <button onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                    className="mt-3 w-full rounded-lg border border-border py-2 text-xs font-semibold text-foreground hover:border-primary/40 active:bg-muted/40 transition">
                    {expandedId === c.id ? 'Hide grid comparison' : 'Compare grids: you vs them'}
                  </button>
                  {expandedId === c.id && own && <GridCompare locationId={locationId} competitor={c} ownName={own.name} />}
                </div>
              )
            })}
          </div>
          {/* Desktop: table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-b border-border/50 text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 sm:px-5 py-3">Business</th>
                  <th className="px-3 py-3">Rating</th>
                  <th className="px-3 py-3">Reviews</th>
                  <th className="px-3 py-3">Best rank</th>
                  <th className="px-3 py-3">Distance</th>
                  <th className="px-3 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {own && (
                  <tr className="border-b border-border/30 bg-primary/[0.04]">
                    <td className="px-4 sm:px-5 py-3 font-bold text-foreground">{own.name} <span className="ml-1 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold text-primary">YOU</span></td>
                    <td className="px-3 py-3 font-medium">{own.rating != null ? <span className="inline-flex items-center gap-1"><Star className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />{own.rating.toFixed(1)}</span> : '—'}</td>
                    <td className="px-3 py-3 font-medium">{own.reviews ?? '—'}</td>
                    <td className="px-3 py-3 text-muted-foreground" colSpan={3}>see heatmap for your rank</td>
                  </tr>
                )}
                {competitors.map(c => {
                  const last = c.snapshots[c.snapshots.length - 1]
                  const prev = c.snapshots.length > 1 ? c.snapshots[c.snapshots.length - 2] : undefined
                  return (
                    <React.Fragment key={c.id}>
                    <tr className="border-b border-border/30 hover:bg-muted/20">
                      <td className="px-4 sm:px-5 py-3">
                        <div className="font-medium text-foreground">{c.name}</div>
                        <CompetitorBadges c={c} />
                      </td>
                      <td className="px-3 py-3">
                        {last?.rating != null ? (
                          <span className="inline-flex items-center gap-1.5">
                            <span className="inline-flex items-center gap-1"><Star className="h-3.5 w-3.5 text-amber-400 fill-amber-400" />{last.rating.toFixed(1)}</span>
                            <Delta prev={prev?.rating} last={last?.rating} />
                          </span>
                        ) : '—'}
                      </td>
                      <td className="px-3 py-3">
                        <span className="inline-flex items-center gap-1.5">
                          {last?.review_count ?? '—'}
                          <Delta prev={prev?.review_count} last={last?.review_count} />
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <span className="inline-flex items-center gap-1.5">
                          {last?.best_rank != null ? `#${last.best_rank}` : '—'}
                          <Delta prev={prev?.best_rank} last={last?.best_rank} invert />
                        </span>
                      </td>
                      <td className="px-3 py-3">{fmtDistance(c.distance_km)}</td>
                      <td className="px-3 py-3 text-right whitespace-nowrap">
                        <button onClick={() => setExpandedId(expandedId === c.id ? null : c.id)}
                          className={`mr-1 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition ${expandedId === c.id ? 'border-primary/50 text-primary bg-primary/5' : 'border-border text-muted-foreground hover:border-primary/40 hover:text-foreground'}`}>
                          {expandedId === c.id ? 'Hide grid' : 'Compare grid'}
                        </button>
                        <button onClick={() => delMut.mutate(c.id)} aria-label={`Remove ${c.name}`}
                          className="p-2 rounded-lg text-muted-foreground hover:text-rose-500 hover:bg-rose-500/10 transition-colors">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                    {expandedId === c.id && own && (
                      <tr className="border-b border-border/30 bg-muted/10">
                        <td colSpan={6} className="px-4 sm:px-5">
                          <GridCompare locationId={locationId} competitor={c} ownName={own.name} />
                        </td>
                      </tr>
                    )}
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          </>
        )}
      </div>

      {/* Map + rating comparison */}
      {own && competitors.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          <CompetitorMap own={own} competitors={competitors} />
          <RatingComparison own={own} competitors={competitors} />
        </div>
      )}

      {/* Share of local voice over time */}
      {own && competitors.length > 0 && (
        <SovTrend own={own} ownTrend={data?.own_trend ?? []} competitors={competitors} />
      )}

      {/* Pro intelligence — velocity, gaps, trends, keyword winners */}
      {own && competitors.length > 0 && (
        isPro ? (
          <>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
              <ProVelocityAndGaps own={own} competitors={competitors} />
              <ProRankTrend competitors={competitors} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
              <RankCorrelation market={data?.market ?? []} metric="reviews" label="Reviews" />
              <RankCorrelation market={data?.market ?? []} metric="photos" label="Photos" />
            </div>
            <ProKeywordWinners winners={data?.keyword_winners ?? []} ownName={own.name} />
          </>
        ) : (
          <ProTeaser />
        )
      )}

      {/* Suggestions from scans */}
      <div className="glass-panel rounded-2xl border-border/40 shadow-sm p-4 sm:p-5">
        <h3 className="text-sm font-semibold text-foreground mb-1">Found in your rank scans</h3>
        <p className="text-xs text-muted-foreground mb-4">Businesses that ranked around you in recent scans, most-seen first.</p>
        {suggestionList.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nothing yet — run a rank scan on the Heatmap tab and competitors will appear here automatically.
          </p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {suggestionList.map(s => (
              <div key={s.place_id} className="flex items-start justify-between gap-3 rounded-xl border border-border/60 bg-muted/10 p-3.5">
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-foreground truncate">{s.name}</div>
                  <div className="text-[11px] text-muted-foreground truncate">{s.category || s.address || ''}</div>
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    {s.rating != null && <span className="inline-flex items-center gap-1"><Star className="h-3 w-3 text-amber-400 fill-amber-400" />{s.rating.toFixed(1)}</span>}
                    {s.reviews != null && <span>{s.reviews} reviews</span>}
                    {s.best_rank != null && <span>best #{s.best_rank}</span>}
                  </div>
                </div>
                <button
                  onClick={() => { setAdding(s.place_id); addMut.mutate(s) }}
                  disabled={adding === s.place_id || competitors.length >= limit}
                  className="shrink-0 inline-flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-xs font-bold text-primary-foreground hover:opacity-90 disabled:opacity-50 transition">
                  <Plus className="h-3.5 w-3.5" /> Track
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
