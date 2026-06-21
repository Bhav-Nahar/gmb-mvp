'use client'

import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { MapPin, Loader2, AlertTriangle } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useLocationWorkspace } from '@/hooks/useLocationWorkspace'
import { useBillingStatus } from '@/hooks/useBilling'
import { LocalRankMap, RankCell } from '@/components/local-rank/LocalRankMap'

// Full scan (detail endpoint) — includes cells.
interface Scan {
  id: number; keyword: string; grid_size: number; radius_miles: number; status: string
  avg_rank: number | null; solv: number | null; found_count: number; total_cells: number
  cells: RankCell[]; credits_charged: number; error: string | null; created_at: string
}

// Lightweight scan (list endpoint) — no cells, carries a centre for the preview.
interface ScanSummary {
  id: number; keyword: string; grid_size: number; radius_miles: number; status: string
  avg_rank: number | null; solv: number | null; found_count: number; total_cells: number
  credits_charged: number; error: string | null; created_at: string
  center_lat: number | null; center_lng: number | null
}

const GRID_SIZES = [3, 5]
// Mirror of backend CREDITS_BY_GRID — gate the button so a click never 402s.
const CREDITS: Record<number, number> = { 3: 1, 5: 2 }
const KM_OPTIONS = [2, 4, 6, 8, 10, 12, 14]
const KM_TO_MILES = 0.621371

const LEGEND = [
  ['#16a34a', '1–3'], ['#84cc16', '4–7'], ['#f59e0b', '8–10'],
  ['#f97316', '11–15'], ['#ef4444', '16–20'], ['#6b7280', '20+'],
]

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })

// JS mirror of the backend build_grid — draws a live preview before scanning.
const MILES_PER_DEG_LAT = 69.0
function buildPreviewGrid(lat: number, lng: number, gridSize: number, radiusMiles: number): RankCell[] {
  const half = (gridSize - 1) / 2
  const step = half ? radiusMiles / half : 0
  const cosLat = Math.cos((lat * Math.PI) / 180) || 1e-6
  const out: RankCell[] = []
  for (let r = 0; r < gridSize; r++) {
    for (let c = 0; c < gridSize; c++) {
      const i = half - r
      const j = c - half
      out.push({
        row: r, col: c,
        lat: lat + (i * step) / MILES_PER_DEG_LAT,
        lng: lng + (j * step) / (MILES_PER_DEG_LAT * cosLat),
        rank: null, top_competitor: null,
      })
    }
  }
  return out
}

interface Props { locationId: number }

export function LocalRankPanel({ locationId }: Props) {
  const queryClient = useQueryClient()
  const { location } = useLocationWorkspace(locationId)
  const { data: billing } = useBillingStatus()

  const [keyword, setKeyword] = useState('')
  const [gridSize, setGridSize] = useState(5)
  const [radiusKm, setRadiusKm] = useState(4)
  const [scanId, setScanId] = useState<number | null>(null)
  const [previewing, setPreviewing] = useState(false)

  // Prefill the keyword from the primary category once the location loads.
  useEffect(() => {
    if (location?.primary_category && !keyword) setKeyword(location.primary_category)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location])

  // Recent scans (lightweight) — power the history list AND give a preview centre.
  const { data: recent } = useQuery<ScanSummary[]>({
    queryKey: ['local-rank', locationId],
    queryFn: () => api.get(`/locations/${locationId}/local-rank/scans`, { limit: '20' }),
    enabled: !!locationId,
  })
  useEffect(() => { if (scanId == null && recent?.[0]) setScanId(recent[0].id) }, [recent, scanId])

  // Poll the active scan (full detail with cells) while it's Pending.
  const { data: scan } = useQuery<Scan>({
    queryKey: ['local-rank-scan', scanId],
    queryFn: () => api.get(`/locations/${locationId}/local-rank/scans/${scanId}`),
    enabled: !!scanId,
    refetchInterval: (q) => (q.state.data?.status === 'Pending' ? 2500 : false),
  })

  const available = (billing?.monthly_ai_credits_balance ?? 0) + (billing?.topup_ai_credits_balance ?? 0)
  const price = CREDITS[gridSize]
  const running = scan?.status === 'Pending'

  const runMutation = useMutation({
    mutationFn: () => api.post<Scan>(`/locations/${locationId}/local-rank/scan`,
      { keyword: keyword.trim(), grid_size: gridSize, radius_miles: +(radiusKm * KM_TO_MILES).toFixed(3) }),
    onSuccess: (data) => {
      setScanId(data.id)
      setPreviewing(false)
      queryClient.invalidateQueries({ queryKey: ['local-rank', locationId] })
      toast.success('Scan started — results in a moment')
    },
    onError: (err: any) => toast.error(err.message || 'Could not start scan'),
  })

  useEffect(() => {
    if (scan?.status === 'Failed') toast.error(`Scan failed: ${scan.error || 'unknown error'}`)
    if (scan?.status === 'Completed') queryClient.invalidateQueries({ queryKey: ['billing_status'] })
    if (scan?.status === 'Completed' || scan?.status === 'Failed') {
      queryClient.invalidateQueries({ queryKey: ['local-rank', locationId] })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan?.status])

  // Live preview: centre = the latest scan that has one (precomputed server-side).
  const centerScan = recent?.find((s) => s.center_lat != null && s.center_lng != null)
  const center = centerScan ? { lat: centerScan.center_lat as number, lng: centerScan.center_lng as number } : null
  const radiusMiles = radiusKm * KM_TO_MILES
  const showPreview = (previewing || !(scan && scan.status === 'Completed')) && !!center
  const displayCells: RankCell[] = showPreview && center
    ? buildPreviewGrid(center.lat, center.lng, gridSize, radiusMiles)
    : (scan?.cells ?? [])

  // Insight: which categories the top-ranked competitors use (top 3 per cell).
  const catCounts: Record<string, number> = {}
  if (!showPreview && scan?.status === 'Completed') {
    (scan.cells || []).forEach((c) => (c.top_results || []).slice(0, 3).forEach((r) => {
      [r.category, ...((r.additional_categories) || [])].filter(Boolean).forEach((cat) => {
        catCounts[cat as string] = (catCounts[cat as string] || 0) + 1
      })
    }))
  }
  const topCats = Object.entries(catCounts).sort((a, b) => b[1] - a[1]).slice(0, 6)

  const tooFew = available < price
  const busy = runMutation.isPending || running

  const onGrid = (g: number) => { setGridSize(g); setPreviewing(true) }
  const onRadius = (km: number) => { setRadiusKm(km); setPreviewing(true) }

  // Feature gate — Local Rank is a Pro-tier feature.
  if (billing && !(billing.features ?? []).includes('local_rank')) {
    return (
      <div className="bg-card border border-border rounded-xl p-6 shadow-sm text-center space-y-3">
        <MapPin className="h-8 w-8 text-primary mx-auto" />
        <h3 className="text-lg font-semibold text-foreground">Local Rank is a Pro feature</h3>
        <p className="text-sm text-muted-foreground max-w-md mx-auto">
          See exactly where you rank across the map for any keyword — with competitor categories,
          ratings and photo gaps. Upgrade to Pro to unlock it.
        </p>
        <a href="/dashboard/settings/billing"
          className="inline-flex items-center justify-center h-9 px-4 rounded-md bg-primary text-primary-foreground text-sm font-medium hover:opacity-90">
          Upgrade to Pro
        </a>
      </div>
    )
  }

  return (
    <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-4">
      {/* Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label htmlFor="lr-keyword" className="text-xs">Search keyword</Label>
          <Input id="lr-keyword" value={keyword} onChange={(e) => setKeyword(e.target.value)}
            placeholder="e.g. diamond ring shop" className="text-sm" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="lr-radius" className="text-xs">Radius (km, centre → edge)</Label>
          <select id="lr-radius" value={radiusKm} onChange={(e) => onRadius(Number(e.target.value))}
            className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm">
            {KM_OPTIONS.map((km) => <option key={km} value={km}>{km} km</option>)}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label className="text-xs">Grid size</Label>
          <div className="flex gap-1">
            {GRID_SIZES.map((g) => (
              <button key={g} onClick={() => onGrid(g)}
                className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                  gridSize === g ? 'bg-primary text-primary-foreground border-primary' : 'border-border hover:bg-muted/40'}`}>
                {g}×{g}
              </button>
            ))}
          </div>
        </div>
        <Button onClick={() => runMutation.mutate()} disabled={busy || tooFew || !keyword.trim()}
          title={tooFew ? 'Not enough AI credits' : ''}>
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <MapPin className="h-4 w-4" />}
          {running ? 'Scanning…' : 'Run scan'}
        </Button>
        <span className="text-xs text-muted-foreground">
          {gridSize}×{gridSize} = {gridSize * gridSize} points · {price} credits · you have {available}
        </span>
      </div>

      {/* Map: live gray preview before scanning, real ranks after */}
      {displayCells.length > 0 && (
        <div className="space-y-3 pt-2 border-t border-border/50">
          {!showPreview && scan && scan.status === 'Completed' ? (
            <div className="flex flex-wrap gap-4 text-sm">
              <span><span className="text-muted-foreground">Avg rank:</span> <b>{scan.avg_rank ?? '—'}</b></span>
              <span><span className="text-muted-foreground">Top-3 coverage (SoLV):</span> <b>{scan.solv ?? 0}%</b></span>
              <span><span className="text-muted-foreground">Found in:</span> <b>{scan.found_count}/{scan.total_cells}</b> spots</span>
              <span className="text-muted-foreground">“{scan.keyword}”</span>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              Preview · {gridSize}×{gridSize} grid over {radiusKm} km — press Run scan to get ranks.
            </p>
          )}

          <LocalRankMap cells={displayCells} preview={showPreview} />

          {!showPreview && (
            <div className="flex flex-wrap gap-3 text-[11px] text-muted-foreground">
              {LEGEND.map(([c, label]) => (
                <span key={label} className="flex items-center gap-1">
                  <i className="inline-block h-3 w-3 rounded-full" style={{ background: c }} /> {label}
                </span>
              ))}
            </div>
          )}

          {!showPreview && topCats.length > 0 && (
            <div className="rounded-lg bg-muted/20 border border-border/50 p-3 text-xs space-y-2">
              <div className="font-medium text-foreground">Categories your top-ranked competitors use</div>
              <div className="flex flex-wrap gap-1.5">
                {topCats.map(([cat, n]) => (
                  <span key={cat} className="px-2 py-0.5 rounded-full bg-background border border-border">
                    {cat} <span className="text-muted-foreground">×{n}</span>
                  </span>
                ))}
              </div>
              {location?.primary_category && (
                <div className="text-muted-foreground">
                  Your primary category: <b className="text-foreground">{location.primary_category}</b>
                  {' '}— consider adding any of the above you don’t already cover.
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {running && (
        <p className="text-sm text-muted-foreground flex items-center gap-2 pt-2 border-t border-border/50">
          <Loader2 className="h-4 w-4 animate-spin" /> Running {scan?.grid_size}×{scan?.grid_size} scan — searching from each point…
        </p>
      )}

      {scan && scan.status === 'Failed' && (
        <div className="flex items-start gap-2 text-sm text-destructive pt-2 border-t border-border/50">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /> Scan failed: {scan.error || 'unknown error'}
        </div>
      )}

      {/* Scan history — pick any past run to view its map */}
      {recent && recent.length > 0 && (
        <div className="pt-3 border-t border-border/50">
          <h4 className="text-sm font-medium text-foreground mb-2">Scan history</h4>
          <div className="space-y-1 max-h-52 overflow-auto">
            {recent.map((s) => (
              <button
                key={s.id}
                onClick={() => { setScanId(s.id); setPreviewing(false) }}
                className={`w-full text-left text-xs px-3 py-2 rounded-md border transition-colors ${
                  s.id === scanId && !showPreview ? 'border-primary bg-primary/10 text-foreground' : 'border-border hover:bg-muted/40 text-muted-foreground'
                }`}
              >
                <span className="font-semibold">{fmtDate(s.created_at)}</span> · {s.keyword} · {s.grid_size}×{s.grid_size}
                {s.status === 'Completed'
                  ? ` · avg ${s.avg_rank ?? '—'} · SoLV ${s.solv ?? 0}%`
                  : ` · ${s.status}`}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
