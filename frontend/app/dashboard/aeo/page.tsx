'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, ShieldAlert } from 'lucide-react'
import { api } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { AEOPanel } from '@/components/aeo/AEOPanel'

interface Loc { id: number; location_name: string }

export default function AEOPage() {
  const { user } = useAuth()
  const isAdmin = !!user?.role && ['owner', 'admin'].includes(user.role.toLowerCase())
  const [selected, setSelected] = useState<number | null>(null)

  const { data: locations = [], isLoading } = useQuery<Loc[]>({
    queryKey: ['locations'],
    queryFn: () => api.get<Loc[]>('/locations/'),
    enabled: isAdmin,
  })

  useEffect(() => {
    if (selected === null && locations[0]) setSelected(locations[0].id)
  }, [locations, selected])

  // Defense in depth — sidebar hides the nav and the backend enforces 403, but a
  // typed URL still lands here, so a non-admin sees a clear message, not a broken page.
  if (user && !isAdmin) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center p-6">
        <div className="max-w-md space-y-3 rounded-2xl border bg-card p-8 text-center shadow-sm">
          <ShieldAlert className="mx-auto h-8 w-8 text-muted-foreground" />
          <h2 className="text-lg font-bold">Owners &amp; Admins only</h2>
          <p className="text-sm text-muted-foreground">AI Visibility is managed by your organization&apos;s owners and admins.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5 p-4 sm:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold text-foreground">
          <Sparkles className="h-6 w-6 text-primary" /> AI Visibility
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Where each location shows up when customers ask AI — ChatGPT, Gemini, Perplexity and Google&apos;s AI answers — for local searches.
        </p>
      </div>

      <div className="max-w-sm space-y-1">
        <label htmlFor="aeo-location" className="text-xs font-medium text-muted-foreground">Location</label>
        <select
          id="aeo-location"
          value={selected ?? ''}
          onChange={(e) => setSelected(Number(e.target.value))}
          disabled={isLoading || !locations.length}
          className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
        >
          {locations.map((l) => <option key={l.id} value={l.id}>{l.location_name}</option>)}
        </select>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading locations…</p>
      ) : !locations.length ? (
        <p className="text-sm text-muted-foreground">No locations found. Sync your Google Business Profile first.</p>
      ) : selected ? (
        <AEOPanel key={selected} locationId={selected} locationName={locations.find((l) => l.id === selected)?.location_name} />
      ) : null}
    </div>
  )
}
