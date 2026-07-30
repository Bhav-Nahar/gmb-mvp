'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import { History } from 'lucide-react'
import { api } from '@/lib/api'
import { Badge } from '@/components/ui/badge'
import { ChangeDiff, GoogleUpdateActions, formatDistanceToNow } from '@/components/changes/ChangeEntry'

export interface ProfileChange {
  id: number
  location_id: number
  location_name: string
  action: string
  payload: any
  created_at: string
}

const PAGE_SIZE = 50

const FILTERS = [
  { key: null, label: 'All' },
  { key: 'profile', label: 'Profile edits' },
  { key: 'google', label: 'Google' },
  { key: 'attribute', label: 'Attributes' },
] as const

export default function ChangesPage() {
  const [source, setSource] = useState<string | null>(null)
  const [locationId, setLocationId] = useState<number | null>(null)
  const [page, setPage] = useState(0)

  // Changing a filter must reset to the first page, or you land on an empty page 3.
  const setFilter = (fn: () => void) => { fn(); setPage(0) }

  // Same query key as the other dashboard pages, so react-query serves it from cache.
  const { data: locations = [] } = useQuery<{ id: number; location_name: string }[]>({
    queryKey: ['locations'],
    queryFn: () => api.get('/locations/'),
  })

  const { data: changes, isLoading, isPlaceholderData } = useQuery<ProfileChange[]>({
    queryKey: ['profile-changes', source, locationId, page],
    queryFn: () => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(page * PAGE_SIZE),
      })
      if (source) params.set('source', source)
      if (locationId) params.set('location_id', String(locationId))
      return api.get(`/profile-changes?${params}`)
    },
    // Keep the current page visible while the next one loads, so the list doesn't
    // collapse to a spinner on every click.
    placeholderData: prev => prev,
  })

  // The API returns a plain list, so a full page means "there is probably more".
  const hasMore = (changes?.length ?? 0) === PAGE_SIZE

  return (
    // Same container as every other dashboard page — the shell adds no padding of its own.
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Unauthorised Changes</h1>
        <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
          Edits to your listings that did not go through this app — made by Google, or by
          someone with direct access to your profile. We can tell you what changed, but
          Google never reports who.
        </p>
      </div>

      {/* Both filters on one row from sm up — they belong together and the page was
          spending three stacked blocks on them. */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
        <div className="w-full sm:max-w-xs space-y-1">
          <label htmlFor="changes-location" className="text-xs font-medium text-muted-foreground">
            Location
          </label>
          <select
            id="changes-location"
            value={locationId ?? ''}
            onChange={e => setFilter(() => setLocationId(e.target.value ? Number(e.target.value) : null))}
            disabled={!locations.length}
            className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm"
          >
            <option value="">All locations</option>
            {locations.map(l => (
              <option key={l.id} value={l.id}>{l.location_name}</option>
            ))}
          </select>
        </div>

        <div className="flex flex-wrap gap-2 sm:pt-5">
          {FILTERS.map(f => (
            <Badge
              key={f.label}
              variant={source === f.key ? 'default' : 'outline'}
              className="cursor-pointer h-auto py-2 px-3 text-xs sm:h-7 sm:py-1 sm:px-3"
              onClick={() => setFilter(() => setSource(f.key))}
            >
              {f.label}
            </Badge>
          ))}
        </div>
      </div>

      {isLoading && <div className="text-muted-foreground py-8 text-center">Loading…</div>}

      {!isLoading && !changes?.length && (
        <div className="text-center py-16 border border-dashed border-border rounded-lg">
          <History className="h-8 w-8 mx-auto text-muted-foreground/40 mb-3" />
          <div className="text-foreground font-medium">Nothing has changed</div>
          <p className="text-sm text-muted-foreground mt-1">
            {locationId || source
              ? 'No changes match these filters.'
              : 'Your listings match what we last published. We check daily.'}
          </p>
        </div>
      )}

      <div className="space-y-4">
        {changes?.map(change => (
          <div
            key={change.id}
            className="p-4 sm:p-5 border border-border/50 bg-card rounded-lg shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex justify-between items-start gap-4">
              <div className="space-y-1 min-w-0">
                <Link
                  href={`/dashboard/locations/${change.location_id}`}
                  className="text-xs text-muted-foreground hover:text-primary hover:underline"
                >
                  {change.location_name}
                </Link>
                <div className="font-medium text-sm text-foreground">{change.action}</div>
              </div>
              <span className="text-xs text-muted-foreground shrink-0">
                {formatDistanceToNow(new Date(change.created_at))}
              </span>
            </div>

            <div className="mt-3 text-xs bg-muted p-3 rounded-md max-h-48 overflow-y-auto">
              <ChangeDiff payload={change.payload} />
            </div>

            {change.payload?.source === 'google' && (
              <GoogleUpdateActions
                locationId={change.location_id}
                activityId={change.id}
                payload={change.payload}
              />
            )}
          </div>
        ))}
      </div>

      {(page > 0 || hasMore) && (
        <div className="flex items-center justify-between border-t border-border pt-4">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0 || isPlaceholderData}
            className="text-sm px-3 py-1.5 rounded-md border border-border disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted/50"
          >
            Previous
          </button>
          <span className="text-xs text-muted-foreground tabular-nums">Page {page + 1}</span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={!hasMore || isPlaceholderData}
            className="text-sm px-3 py-1.5 rounded-md border border-border disabled:opacity-40 disabled:cursor-not-allowed hover:bg-muted/50"
          >
            Next
          </button>
        </div>
      )}
    </main>
  )
}
