'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import {
  ImagePlus, Trash2, RefreshCw, AlertCircle, CheckCircle2, Clock, XCircle, Upload, PlayCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { api } from '@/lib/api'

// Photo categories relevant to retail/storefront businesses. GBP also defines
// food-specific ones (FOOD_AND_DRINK, MENU) which we omit here — they're only
// meaningful for restaurants and just add noise for a jewelry/retail profile.
const CATEGORIES = [
  { value: 'COVER', label: 'Cover' },
  { value: 'LOGO', label: 'Logo' },
  { value: 'EXTERIOR', label: 'Exterior' },
  { value: 'INTERIOR', label: 'Interior' },
  { value: 'PRODUCT', label: 'Product' },
  { value: 'AT_WORK', label: 'At Work' },
  { value: 'TEAMS', label: 'Team' },
  { value: 'ADDITIONAL', label: 'Additional' },
]

interface LocationMedia {
  id: number
  gbp_category: string
  media_format: string
  source_url: string
  thumbnail_url: string | null
  publish_status: string
  failure_reason: string | null
  created_at: string
}

const PENDING = new Set(['Pending', 'Publishing'])

function StatusBadge({ status, reason }: { status: string; reason: string | null }) {
  if (status === 'Published')
    return <Badge className="bg-emerald-100 text-emerald-700 border-emerald-200 shadow-none gap-1"><CheckCircle2 className="h-3 w-3" />Live</Badge>
  if (PENDING.has(status))
    return <Badge className="bg-amber-100 text-amber-700 border-amber-200 shadow-none gap-1"><Clock className="h-3 w-3 animate-pulse" />Publishing…</Badge>
  return (
    <span title={reason || 'Failed'}>
      <Badge className="bg-rose-100 text-rose-700 border-rose-200 shadow-none gap-1"><XCircle className="h-3 w-3" />{status}</Badge>
    </span>
  )
}

export function PhotosTab({ locationId }: { locationId: number }) {
  const [items, setItems] = useState<LocationMedia[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [category, setCategory] = useState('INTERIOR')
  const [filter, setFilter] = useState('ALL')
  const [page, setPage] = useState(1)
  const fileRef = useRef<HTMLInputElement>(null)

  const PAGE_SIZE = 24

  const fetchMedia = useCallback(async () => {
    try {
      const res = await api.get<LocationMedia[]>(`/locations/${locationId}/media`)
      setItems(res ?? [])
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [locationId])

  useEffect(() => { fetchMedia() }, [fetchMedia])

  // Opening the tab triggers a debounced reconcile with Google on the backend;
  // re-poll a few times so photos uploaded outside our app appear automatically.
  useEffect(() => {
    let n = 0
    const t = setInterval(() => {
      n += 1
      fetchMedia()
      if (n >= 5) clearInterval(t)
    }, 4000)
    return () => clearInterval(t)
  }, [fetchMedia])

  // Keep polling while anything is still publishing.
  useEffect(() => {
    if (!items.some((i) => PENDING.has(i.publish_status))) return
    const t = setInterval(fetchMedia, 5000)
    return () => clearInterval(t)
  }, [items, fetchMedia])

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      // 1. Reuse the existing upload pipeline (storage + validation + optimize).
      const formData = new FormData()
      formData.append('file', file)
      const uploaded: any = await api.post('/media/upload', formData)
      // 2. Publish that asset to this location's Google gallery.
      await api.post(`/locations/${locationId}/media`, {
        source_media_id: uploaded.id,
        category,
      })
      toast.success('Photo queued — it will appear on Google shortly.')
      fetchMedia()
    } catch (err: any) {
      toast.error(err?.message || 'Failed to publish photo')
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  // Categories actually present in the gallery, for the filter dropdown.
  const presentCategories = Array.from(new Set(items.map((i) => i.gbp_category)))
  const filteredItems = filter === 'ALL' ? items : items.filter((i) => i.gbp_category === filter)

  // Paginate client-side: the metadata is cheap, but rendering hundreds of
  // full-res Google images at once is the real bottleneck.
  const totalPages = Math.max(1, Math.ceil(filteredItems.length / PAGE_SIZE))
  const safePage = Math.min(page, totalPages)
  const pagedItems = filteredItems.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  // Reset to page 1 whenever the filter or result set shrinks.
  useEffect(() => { setPage(1) }, [filter])

  const prettyCat = (c: string) => c.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, (m) => m.toUpperCase())

  // Prefer Google's light poster/thumbnail; else shrink an lh3 image URL to a
  // grid-sized render instead of the full-res =s0 original.
  const thumb = (m: LocationMedia) => {
    if (m.thumbnail_url) return m.thumbnail_url
    const url = m.source_url
    return url.includes('googleusercontent.com')
      ? url.replace(/=s\d+(-[a-z]+)?$/i, '=s400').replace(/(=s0)$/i, '=s400')
      : url
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/locations/media/${id}`)
      toast.success('Photo removed')
      setItems((prev) => prev.filter((i) => i.id !== id))
    } catch {
      toast.error('Failed to remove photo')
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-border/40 pb-4">
        <div>
          <h2 className="text-lg font-bold text-foreground">Photos</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Publish photos directly to this location&apos;s Google profile.</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {/* Gallery filter (distinct from the upload category below) */}
          {items.length > 0 && (
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="h-11 sm:h-10 px-3 rounded-md border border-input bg-background text-sm flex-1 min-w-[8rem] sm:flex-none"
              title="Filter photos by category"
            >
              <option value="ALL">All categories ({items.length})</option>
              {presentCategories.map((c) => (
                <option key={c} value={c}>
                  {prettyCat(c)} ({items.filter((i) => i.gbp_category === c).length})
                </option>
              ))}
            </select>
          )}
          <span className="text-xs text-muted-foreground hidden sm:inline">Upload as:</span>
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="h-11 sm:h-10 px-3 rounded-md border border-input bg-background text-sm flex-1 min-w-[8rem] sm:flex-none"
            disabled={uploading}
            title="Category for the next photo you upload"
          >
            {CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={handleFile} />
          <Button size="sm" className="gap-2 bg-gradient-to-r from-indigo-500 to-purple-600 text-white w-full min-h-[44px] sm:w-auto sm:min-h-0"
            onClick={() => fileRef.current?.click()} disabled={uploading}>
            {uploading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            {uploading ? 'Publishing…' : 'Add Photo'}
          </Button>
        </div>
      </div>

      {/* Gallery */}
      {loading ? (
        <div className="h-48 flex items-center justify-center text-sm text-muted-foreground">
          <RefreshCw className="h-4 w-4 animate-spin mr-2" /> Loading photos…
        </div>
      ) : error ? (
        <div className="h-48 flex flex-col items-center justify-center gap-2 text-muted-foreground">
          <AlertCircle className="h-6 w-6 text-amber-500" />
          <p className="font-medium text-foreground">Couldn&apos;t load photos</p>
          <button onClick={fetchMedia} className="text-sm font-medium text-indigo-600 hover:underline">Retry</button>
        </div>
      ) : items.length === 0 ? (
        <div className="h-56 flex flex-col items-center justify-center gap-3 border border-dashed border-border rounded-xl text-muted-foreground">
          <ImagePlus className="h-8 w-8" />
          <p className="text-sm">No photos yet. Add one to strengthen this profile.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {pagedItems.map((m) => (
              <div key={m.id} className="group relative rounded-xl overflow-hidden border border-border/60 bg-card shadow-sm">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={thumb(m)} alt={m.gbp_category} loading="lazy" className="w-full h-40 object-cover bg-muted/30" />
                {m.media_format === 'VIDEO' && (
                  <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <PlayCircle className="h-10 w-10 text-white/90 drop-shadow" />
                  </div>
                )}
                <div className="absolute top-2 left-2"><StatusBadge status={m.publish_status} reason={m.failure_reason} /></div>
                <button
                  onClick={() => handleDelete(m.id)}
                  className="absolute top-2 right-2 flex items-center justify-center h-10 w-10 sm:h-auto sm:w-auto sm:p-1.5 rounded-md bg-black/50 text-white opacity-100 sm:opacity-0 group-hover:opacity-100 transition-opacity hover:bg-rose-600 active:bg-rose-600"
                  title="Remove photo"
                >
                  <Trash2 className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
                </button>
                <div className="p-2.5">
                  <span className="text-xs font-semibold text-foreground capitalize">
                    {m.gbp_category.replace(/_/g, ' ').toLowerCase()}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {filteredItems.length > PAGE_SIZE && (
            <div className="flex items-center justify-between pt-2">
              <p className="text-xs text-muted-foreground">
                Showing {(safePage - 1) * PAGE_SIZE + 1}–{Math.min(safePage * PAGE_SIZE, filteredItems.length)} of {filteredItems.length}
              </p>
              <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled={safePage <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Previous</Button>
                <span className="text-xs text-muted-foreground">Page {safePage} / {totalPages}</span>
                <Button variant="outline" size="sm" disabled={safePage >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Next</Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
