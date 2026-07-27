'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MapPin } from 'lucide-react'
import { api } from '@/lib/api'
import { LocalRankPanel } from '@/components/local-rank/LocalRankPanel'
import { CompetitionPanel } from '@/components/local-rank/CompetitionPanel'

interface Loc { id: number; location_name: string; average_rating?: number | null; total_reviews?: number | null }

export default function LocalRankPage() {
  const [selected, setSelected] = useState<number | null>(null)
  const [view, setView] = useState<'heatmap' | 'competition'>('heatmap')

  const { data: locations = [], isLoading: loading } = useQuery<Loc[]>({
    queryKey: ['locations'],
    queryFn: () => api.get<Loc[]>('/locations/'),
  })

  useEffect(() => {
    if (selected === null && locations[0]) setSelected(locations[0].id)
  }, [locations, selected])

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

      <div className="inline-flex items-center gap-1 rounded-full border border-border bg-card p-1 text-sm">
        <button onClick={() => setView('heatmap')}
          className={`rounded-full px-5 py-1.5 font-semibold transition ${view === 'heatmap' ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
          Heatmap
        </button>
        <button onClick={() => setView('competition')}
          className={`rounded-full px-5 py-1.5 font-semibold transition ${view === 'competition' ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
          Competition
        </button>
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
        view === 'heatmap' ? (
          <LocalRankPanel key={selected} locationId={selected} />
        ) : (
          <CompetitionPanel key={`comp-${selected}`} locationId={selected} />
        )
      ) : null}
    </div>
  )
}
