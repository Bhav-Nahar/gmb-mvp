'use client'

import { useEffect, useState } from 'react'
import { MapPin } from 'lucide-react'
import { api } from '@/lib/api'
import { LocalRankPanel } from '@/components/local-rank/LocalRankPanel'

interface Loc { id: number; location_name: string }

export default function LocalRankPage() {
  const [locations, setLocations] = useState<Loc[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get<Loc[]>('/locations/')
      .then((d) => { setLocations(d || []); if (d && d[0]) setSelected(d[0].id) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="p-4 sm:p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <MapPin className="h-6 w-6 text-primary" /> Local Rank Heatmap
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          See where a location ranks for a keyword across the surrounding map — green where you win, red where you vanish.
        </p>
      </div>

      <div className="space-y-1 max-w-sm">
        <label htmlFor="lr-location" className="text-xs font-medium text-muted-foreground">Location</label>
        <select
          id="lr-location"
          value={selected ?? ''}
          onChange={(e) => setSelected(Number(e.target.value))}
          disabled={loading || !locations.length}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
        >
          {locations.map((l) => <option key={l.id} value={l.id}>{l.location_name}</option>)}
        </select>
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Loading locations…</p>
      ) : !locations.length ? (
        <p className="text-sm text-muted-foreground">No locations found. Sync your Google Business Profile first.</p>
      ) : selected ? (
        <LocalRankPanel key={selected} locationId={selected} />
      ) : null}
    </div>
  )
}
