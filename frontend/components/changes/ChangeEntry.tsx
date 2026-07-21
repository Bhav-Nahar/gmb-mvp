'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { useBillingStatus } from '@/hooks/useBilling'
import { Button } from '@/components/ui/button'

export function formatDistanceToNow(date: Date, options?: { addSuffix?: boolean }): string {
  const diffMins = Math.floor((Date.now() - date.getTime()) / 60000)
  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return options?.addSuffix ? `${diffMins}m ago` : `${diffMins}m`

  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return options?.addSuffix ? `${diffHours}h ago` : `${diffHours}h`

  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 30) return options?.addSuffix ? `${diffDays}d ago` : `${diffDays}d`

  return date.toLocaleDateString()
}

export function ChangeDiff({ payload }: { payload: any }) {
  const render = (v: any) => {
    // Attribute values arrive as single-element arrays of booleans ([true]); showing
    // that verbatim reads as JSON noise rather than "Yes".
    if (Array.isArray(v) && v.length === 1) v = v[0]
    if (typeof v === 'boolean') return v ? 'Yes' : 'No'
    if (v === null || v === undefined) return <span className="italic text-muted-foreground">not set</span>
    return typeof v === 'object' ? JSON.stringify(v) : String(v)
  }

  // Google-sourced entries have no "old" — Google's live value simply differs from
  // the profile, so there is nothing meaningful to strike through.
  if (payload?.source === 'google') {
    return (
      <div className="text-xs">
        <div className="text-muted-foreground mb-1">Google now shows:</div>
        <div className="text-foreground break-all">{render(payload?.new)}</div>
      </div>
    )
  }

  return (
    <div className="text-xs space-y-1">
      <div className="text-muted-foreground line-through break-all">{render(payload?.old)}</div>
      <div className="text-foreground break-all">{render(payload?.new)}</div>
    </div>
  )
}

// Google has no accept/reject endpoint — both are a locations.patch differing only in
// which value you send. So both buttons just queue a normal listing edit.
export function GoogleUpdateActions({
  locationId,
  activityId,
  payload,
}: {
  locationId: number
  activityId: number
  payload: any
}) {
  const queryClient = useQueryClient()
  const { data: billing } = useBillingStatus()

  // Restoring your own value is a real change to the live listing and can trigger
  // Google re-verification, so critical fields confirm first. Accepting adopts a
  // value that is already live, so it needs no confirmation.
  const CRITICAL = ['title', 'storefrontAddress', 'categories']
  const needsConfirm = CRITICAL.includes(payload?.field)

  const resolve = useMutation({
    mutationFn: (action: 'accept' | 'reject') =>
      api.post(
        `/locations/${locationId}/google-updates/${activityId}/${action}` +
        (action === 'reject' && needsConfirm ? '?acknowledge=true' : ''),
        {},
      ),
    onSuccess: (_data, action) => {
      toast.success(action === 'accept'
        ? "Keeping Google's version — publishing now."
        : 'Restoring your version — publishing now.')
      queryClient.invalidateQueries({ queryKey: ['activity-log', locationId] })
      queryClient.invalidateQueries({ queryKey: ['profile-changes'] })
      queryClient.invalidateQueries({ queryKey: ['listing-edits', locationId] })
    },
    onError: (e: any) => toast.error(e?.message || 'Could not apply that. Try again.'),
  })

  if (payload?.resolved) {
    return <div className="text-xs text-muted-foreground mt-2">You {payload.resolved} this change.</div>
  }
  if (!(billing?.features ?? []).includes('google_updates')) return null

  return (
    <div className="flex gap-2 mt-2">
      <Button size="sm" variant="outline" disabled={resolve.isPending}
        onClick={() => resolve.mutate('accept')}>
        Keep Google&apos;s version
      </Button>
      <Button size="sm" variant="outline" disabled={resolve.isPending}
        onClick={() => {
          if (needsConfirm && !window.confirm(
            'Restoring your version changes the live listing on Google. For a business ' +
            'name, address or category this can trigger re-verification, and your ' +
            'listing may show as unverified for a few days. Continue?'
          )) return
          resolve.mutate('reject')
        }}>
        Restore mine
      </Button>
    </div>
  )
}
