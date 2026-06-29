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
    ? `<img src="${escapeHtml(r.image)}" style="width:38px;height:38px;border-radius:6px;object-fit:cover;flex:0 0 auto;box-shadow:0 2px 4px rgba(0,0,0,0.1)" onerror="this.style.visibility='hidden'"/>`
    : `<div style="width:38px;height:38px;border-radius:6px;background:var(--muted);flex:0 0 auto;box-shadow:inset 0 2px 4px rgba(0,0,0,0.05)"></div>`
  
  return `<div style="display:flex;gap:10px;align-items:flex-start;padding:8px;border-radius:8px;margin-bottom:4px;transition:all 0.2s;${isUs ? 'background:rgba(16,185,129,0.1);border:1px solid rgba(16,185,129,0.2)' : 'background:var(--background);border:1px solid var(--border)'}">
    <div style="width:20px;font-weight:800;color:var(--foreground);flex:0 0 auto;text-align:center;font-size:13px;line-height:38px">${r.rank}</div>
    ${img}
    <div style="min-width:0;flex:1">
      <div style="font-weight:700;color:var(--foreground);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${escapeHtml(r.name)}${isUs ? ' <span style="color:#10b981">· you</span>' : ''}</div>
      ${cats ? `<div style="color:var(--muted-foreground);font-size:11px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px">${escapeHtml(cats)}</div>` : ''}
      <div style="color:var(--muted-foreground);font-size:10px;font-weight:500;margin-top:2px">${meta.join(' · ')}</div>
    </div>
  </div>`
}

function popupHtml(c: RankCell): string {
  const rankLine = c.rank == null
    ? '<span style="color:#ef4444">Not in top 20 here</span>'
    : `Your rank here: <span style="color:#10b981;font-size:16px">#${c.rank}</span>`
  const results = c.top_results || []
  const list = results.length
    ? results.slice(0, 10).map((r) => resultRowHtml(r, c.rank != null && r.rank === c.rank)).join('')
    : (c.top_competitor
        ? `<div style="color:var(--muted-foreground);font-size:12px;font-weight:600">#1 here: ${escapeHtml(c.top_competitor)}</div>`
        : '<div style="color:var(--muted-foreground);font-size:12px;font-weight:600">No results</div>')
  return `<div style="min-width:260px;max-width:320px;font-family:inherit">
    <div style="font-weight:800;font-size:13px;margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid var(--border);color:var(--foreground)">${rankLine}</div>
    <div style="max-height:320px;overflow-y:auto;padding-right:4px" class="custom-scrollbar">${list}</div>
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
          html: `<div style="background:${color};width:32px;height:32px;border-radius:9999px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:12px;border:3px solid #fff;box-shadow:0 4px 12px rgba(0,0,0,0.35), inset 0 2px 4px rgba(255,255,255,0.3);transition:transform 0.2s">${label}</div>`,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
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

  return (
    <>
      <style dangerouslySetInnerHTML={{__html: `
        .leaflet-popup-content-wrapper {
          background: hsl(var(--card));
          color: hsl(var(--foreground));
          border: 1px solid hsl(var(--border) / 0.6);
          border-radius: 12px;
          box-shadow: 0 10px 30px -10px rgba(0,0,0,0.5);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
        }
        .leaflet-popup-tip {
          background: hsl(var(--card));
          border-top: 1px solid hsl(var(--border) / 0.6);
          border-left: 1px solid hsl(var(--border) / 0.6);
        }
        .leaflet-popup-close-button {
          color: hsl(var(--muted-foreground)) !important;
          margin-top: 4px !important;
          margin-right: 4px !important;
        }
        .leaflet-popup-close-button:hover {
          color: hsl(var(--foreground)) !important;
          background: transparent !important;
        }
        .leaflet-container {
          background: hsl(var(--muted) / 0.3);
          font-family: inherit;
        }
        .leaflet-div-icon > div:hover {
          transform: scale(1.15) translateY(-2px);
          z-index: 1000 !important;
        }
      `}} />
      <div ref={containerRef} className="h-[70vh] min-h-[520px] w-full rounded-lg overflow-hidden border-none z-0 shadow-inner" />
    </>
  )
}
