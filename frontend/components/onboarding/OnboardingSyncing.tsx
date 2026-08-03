'use client'

import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, Loader2, AlertTriangle } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { beginGoogleLogin } from '@/lib/oauth'

const STEPS = [
  'Importing your locations',
  'Fetching reviews and ratings',
  'Scoring your profile health',
  'Generating AI insights',
  'Benchmarking your competitors',
]

// Perceived-progress cadence. Steps tick over on a timer (we have no granular sync
// signal); the screen swaps out for the audit the moment billing status flips to ready.
const STEP_MS = 1100

/**
 * Full-screen "building your audit" screen. The staggered checklist and progress bar
 * make the work feel real and thorough, which is what earns the paywall that follows.
 */
// How long to believe "a few seconds" before offering a way out. The screen polls billing
// status every 3s, so anything past this is a sync that is not coming back on its own.
const STALL_MS = 25_000

export function OnboardingSyncing({ failed = false, neverStarted = false }:
  { failed?: boolean; neverStarted?: boolean }) {
  const [done, setDone] = useState(0)
  const [retrying, setRetrying] = useState(false)
  const [stalled, setStalled] = useState(false)
  const kicked = useRef(false)
  const queryClient = useQueryClient()

  // Real retry: re-trigger the org sync, then re-poll billing status (which flips
  // onboarding_sync_status back to 'syncing' and swaps this screen for the checklist).
  const retry = async () => {
    if (retrying) return
    setRetrying(true)
    try {
      await api.post('/locations/sync', {})
      await queryClient.invalidateQueries({ queryKey: ['billing_status'] })
    } catch (e: any) {
      toast.error(e?.message || 'Could not restart the sync. Please try again.')
    } finally {
      setRetrying(false)
    }
  }

  // No sync state at all means the initial task never ran (lost on a worker/broker
  // restart, or the org got its locations another way). Nothing else will ever start it,
  // so start it once — otherwise this screen spins forever.
  useEffect(() => {
    if (failed || !neverStarted || kicked.current) return
    kicked.current = true
    retry()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [failed, neverStarted])

  // Escape hatch: past STALL_MS this stops pretending and offers the retry controls.
  useEffect(() => {
    if (failed) return
    const id = setTimeout(() => setStalled(true), STALL_MS)
    return () => clearTimeout(id)
  }, [failed])

  useEffect(() => {
    if (failed) return
    const id = setInterval(() => {
      // Advance up to the last step, then hold it "in progress" until the parent swaps us.
      setDone((d) => (d < STEPS.length - 1 ? d + 1 : d))
    }, STEP_MS)
    return () => clearInterval(id)
  }, [failed])

  if (failed) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/20 p-4">
        <div className="w-full max-w-md space-y-4 rounded-2xl border bg-card p-8 text-center shadow-2xl">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertTriangle className="h-6 w-6 text-destructive" />
          </div>
          <h2 className="text-xl font-bold">We could not finish your audit</h2>
          <p className="text-sm text-muted-foreground">
            Something went wrong while syncing your Google Business Profile. Please reconnect
            your Google account and try again.
          </p>
          <div className="flex flex-col justify-center gap-2 sm:flex-row">
            <button
              type="button"
              onClick={retry}
              disabled={retrying}
              className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {retrying ? 'Restarting...' : 'Retry sync'}
            </button>
            <button
              type="button"
              onClick={() =>
                beginGoogleLogin('sync_failed').catch(() =>
                  toast.error('Could not open Google sign-in. Please try again.')
                )
              }
              className="rounded-xl border px-4 py-2.5 text-sm font-semibold hover:bg-muted"
            >
              Reconnect Google
            </button>
          </div>
        </div>
      </div>
    )
  }

  const progress = Math.round(((done + 0.5) / STEPS.length) * 100)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-neutral-950/20 p-4">
      <div className="w-full max-w-md space-y-6 rounded-2xl border bg-card p-8 shadow-2xl">
        <div className="space-y-1 text-center">
          <h2 className="text-xl font-bold">Building your audit</h2>
          <p className="text-sm text-muted-foreground">
            {stalled
              ? 'This is taking longer than usual. Your sync may not have started.'
              : 'We are analyzing your Google Business Profile. This takes just a few seconds.'}
          </p>
        </div>

        {stalled && (
          <div className="flex flex-col justify-center gap-2 sm:flex-row">
            <button
              type="button"
              onClick={retry}
              disabled={retrying}
              className="rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {retrying ? 'Restarting...' : 'Restart sync'}
            </button>
            <button
              type="button"
              onClick={() =>
                beginGoogleLogin('sync_failed').catch(() =>
                  toast.error('Could not open Google sign-in. Please try again.')
                )
              }
              className="rounded-xl border px-4 py-2.5 text-sm font-semibold hover:bg-muted"
            >
              Reconnect Google
            </button>
          </div>
        )}

        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary transition-all duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        <ul className="space-y-3">
          {STEPS.map((s, i) => {
            const isDone = i < done
            const isActive = i === done
            return (
              <li key={s} className="flex items-center gap-3 text-sm">
                {isDone ? (
                  <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                ) : isActive ? (
                  <Loader2 className="h-5 w-5 shrink-0 animate-spin text-primary" />
                ) : (
                  <span className="h-5 w-5 shrink-0 rounded-full border-2 border-muted" />
                )}
                <span className={isDone || isActive ? 'text-foreground' : 'text-muted-foreground'}>
                  {s}
                </span>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
