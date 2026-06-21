'use client'

import { useEffect, useRef } from 'react'

export interface RankResult {
  rank: number
  name: string
  rating: number | null
  reviews: number | null
  category?: string | null
  additional_categories?: string[]
  total_photos?: number | null
  price_level?: string | null
  is_claimed?: boolean | null
  domain?: string | null
  address?: string | null
  image?: string | null
}

export interface RankCell {
  row: number
  col: number
  lat: number
  lng: number
  rank: number | null
  top_competitor: string | null
  top_results?: RankResult[]
}

// Leaflet from CDN (no npm dependency -> Docker `npm ci` stays intact). ponytail:
// OSM tiles are fine for low volume; switch to a paid provider if traffic grows.
let leafletPromise: Promise<any> | null = null
function loadLeaflet(): Promise<any> {
  if (typeof window === 'undefined') return Promise.reject(new Error('no window'))
  if ((window as any).L) return Promise.resolve((window as any).L)
  if (leafletPromise) return leafletPromise
  leafletPromise = new Promise((resolve, reject) => {
    const css = document.createElement('link')
    css.rel = 'stylesheet'
    css.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
    document.head.appendChild(css)
    const js = document.createElement('script')
    js.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
    js.async = true
    js.onload = () => resolve((window as any).L)
    js.onerror = () => reject(new Error('Leaflet failed to load'))
    document.head.appendChild(js)
  })
  return leafletPromise
}

function colorFor(rank: number | null): string {
  if (rank == null) return '#6b7280'
  if (rank <= 3) return '#16a34a'
  if (rank <= 7) return '#84cc16'
  if (rank <= 10) return '#f59e0b'
  if (rank <= 15) return '#f97316'
  return '#ef4444'
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c] as string
  ))
}

const PRICE_LABEL: Record<string, string> = {
  free: 'Free', inexpensive: '$', moderate: '$$', expensive: '$$$', very_expensive: '$$$$',
}

// One competitor row in the pin popup (rich card style).
function resultRowHtml(r: RankResult, isUs: boolean): string {
  const cats = [r.category, ...(r.additional_categories || [])].filter(Boolean).join(', ')
  const meta: string[] = []
  if (r.rating != null) meta.push(`★ ${r.rating}${r.reviews != null ? ` (${r.reviews})` : ''}`)
  if (r.total_photos != null) meta.push(`📷 ${r.total_photos}`)
  if (r.price_level && PRICE_LABEL[r.price_level]) meta.push(PRICE_LABEL[r.price_level])
  if (r.is_claimed === false) meta.push('Unclaimed')
  const img = r.image
    ? `<img src="${escapeHtml(r.image)}" style="width:38px;height:38px;border-radius:6px;object-fit:cover;flex:0 0 auto" onerror="this.style.visibility='hidden'"/>`
    : `<div style="width:38px;height:38px;border-radius:6px;background:#e5e7eb;flex:0 0 auto"></div>`
  return `<div style="display:flex;gap:8px;align-items:flex-start;padding:6px 4px;border-radius:6px;${isUs ? 'background:#dcfce7' : ''}">
    <div style="width:16px;font-weight:700;color:#374151;flex:0 0 auto;text-align:center;font-size:12px;line-height:38px">${r.rank}</div>
    ${img}
    <div style="min-width:0;flex:1">
      <div style="font-weight:600;color:#111827;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(r.name)}${isUs ? ' · you' : ''}</div>
      ${cats ? `<div style="color:#6b7280;font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(cats)}</div>` : ''}
      <div style="color:#6b7280;font-size:11px">${meta.join(' · ')}</div>
    </div>
  </div>`
}

function popupHtml(c: RankCell): string {
  const rankLine = c.rank == null
    ? '<span style="color:#ef4444">Not in top 20 here</span>'
    : `Your rank here: <span style="color:#16a34a">#${c.rank}</span>`
  const results = c.top_results || []
  const list = results.length
    ? results.slice(0, 10).map((r) => resultRowHtml(r, c.rank != null && r.rank === c.rank)).join('')
    : (c.top_competitor
        ? `<div style="color:#6b7280;font-size:12px">#1 here: ${escapeHtml(c.top_competitor)}</div>`
        : '<div style="color:#6b7280;font-size:12px">No results</div>')
  return `<div style="min-width:255px;max-width:300px;font-family:system-ui,sans-serif">
    <div style="font-weight:700;font-size:13px;margin-bottom:6px;padding-bottom:6px;border-bottom:1px solid #e5e7eb">${rankLine}</div>
    <div style="max-height:300px;overflow:auto">${list}</div>
  </div>`
}

export function LocalRankMap({ cells, preview = false }: { cells: RankCell[]; preview?: boolean }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<any>(null)
  const layerRef = useRef<any>(null)

  useEffect(() => {
    let cancelled = false
    loadLeaflet().then((L) => {
      if (cancelled || !containerRef.current) return
      if (!mapRef.current) {
        mapRef.current = L.map(containerRef.current, { scrollWheelZoom: false }).setView([20, 78], 5)
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
          attribution: '&copy; OpenStreetMap contributors',
          maxZoom: 19,
        }).addTo(mapRef.current)
      }
      if (layerRef.current) layerRef.current.remove()
      layerRef.current = L.layerGroup().addTo(mapRef.current)

      // Grid lines — connect adjacent points along each row and column (drawn first,
      // so the pins sit on top).
      const rows = new Map<number, RankCell[]>()
      const cols = new Map<number, RankCell[]>()
      cells.forEach((c) => {
        if (!rows.has(c.row)) rows.set(c.row, [])
        if (!cols.has(c.col)) cols.set(c.col, [])
        rows.get(c.row)!.push(c)
        cols.get(c.col)!.push(c)
      })
      const lineOpts = { color: '#94a3b8', weight: 1, opacity: 0.5, interactive: false }
      rows.forEach((rc) => {
        const line = [...rc].sort((a, b) => a.col - b.col).map((c) => [c.lat, c.lng] as [number, number])
        if (line.length > 1) L.polyline(line, lineOpts).addTo(layerRef.current)
      })
      cols.forEach((cc) => {
        const line = [...cc].sort((a, b) => a.row - b.row).map((c) => [c.lat, c.lng] as [number, number])
        if (line.length > 1) L.polyline(line, lineOpts).addTo(layerRef.current)
      })

      const pts: [number, number][] = []
      cells.forEach((c) => {
        if (preview) {
          const dot = L.divIcon({
            className: '',
            html: `<div style="background:#64748b;opacity:.55;width:12px;height:12px;border-radius:9999px;border:2px solid #fff;box-shadow:0 1px 2px rgba(0,0,0,.35)"></div>`,
            iconSize: [12, 12],
            iconAnchor: [6, 6],
          })
          L.marker([c.lat, c.lng], { icon: dot, interactive: false }).addTo(layerRef.current)
          pts.push([c.lat, c.lng])
          return
        }
        const color = colorFor(c.rank)
        const label = c.rank == null ? '20+' : String(c.rank)
        const icon = L.divIcon({
          className: '',
          html: `<div style="background:${color};width:30px;height:30px;border-radius:9999px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:700;font-size:11px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.45)">${label}</div>`,
          iconSize: [30, 30],
          iconAnchor: [15, 15],
        })
        L.marker([c.lat, c.lng], { icon }).addTo(layerRef.current).bindPopup(popupHtml(c), { maxWidth: 320 })
        pts.push([c.lat, c.lng])
      })
      if (pts.length) mapRef.current.fitBounds(pts, { padding: [50, 50], maxZoom: 15 })
      setTimeout(() => { if (!cancelled && mapRef.current) mapRef.current.invalidateSize() }, 150)
    }).catch(() => { /* CDN/network failure — map just stays blank */ })
    return () => { cancelled = true }
  }, [cells, preview])

  // Tear the map down on unmount so route changes don't leak or clash.
  useEffect(() => () => {
    if (mapRef.current) { mapRef.current.remove(); mapRef.current = null }
  }, [])

  return <div ref={containerRef} className="h-[70vh] min-h-[520px] w-full rounded-lg overflow-hidden border border-border z-0" />
}
