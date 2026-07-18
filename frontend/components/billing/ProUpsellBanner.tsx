'use client'

import { useState } from 'react'
import { Sparkles, X } from 'lucide-react'
import { useBillingStatus } from '@/hooks/useBilling'

const DISMISS_KEY = 'pro_upsell_dismissed'

/**
 * Slim, dismissible "go Pro" nudge for Basic-tier users — the post-value upsell (shown
 * to a happy trial/active user, never at the onboarding wall). CTA opens the existing
 * UpgradeModal (via BillingProvider) rather than any new payment path. Dismissal sticks
 * per browser so it never nags.
 */
export function ProUpsellBanner() {
  const { data: billing } = useBillingStatus()
  const [dismissed, setDismissed] = useState(
    () => typeof window !== 'undefined' && localStorage.getItem(DISMISS_KEY) === '1',
  )

  if (dismissed || !billing) return null
  if (billing.plan_tier !== 'basic') return null
  // ACTIVE Basic users only. Upgrading via the plain checkout charges immediately and
  // (for a trial) would orphan the Basic trial mandate into a day-7 double charge — so a
  // trial->Pro switch needs a dedicated change-tier endpoint (not built yet). Until then
  // we don't offer the upsell mid-trial.
  if (billing.subscription_status !== 'active') return null

  const dismiss = () => {
    if (typeof window !== 'undefined') localStorage.setItem(DISMISS_KEY, '1')
    setDismissed(true)
  }

  return (
    <div className="flex items-center justify-center gap-3 border-b border-violet-200 bg-violet-50 px-4 py-2.5 text-sm text-violet-900 dark:border-violet-900/40 dark:bg-violet-950/30 dark:text-violet-200">
      <Sparkles className="h-4 w-4 shrink-0" />
      <span>
        You&apos;re on <strong>Basic</strong>. Go <strong>Pro</strong> for local-rank heatmaps,
        a published microsite &amp; more AI credits.
      </span>
      <button
        type="button"
        onClick={() => window.dispatchEvent(new Event('open-upgrade-modal'))}
        className="shrink-0 rounded-md bg-violet-600 px-3 py-1 text-xs font-semibold text-white transition hover:bg-violet-700"
      >
        Upgrade to Pro
      </button>
      <button type="button" onClick={dismiss} aria-label="Dismiss" className="shrink-0 opacity-60 hover:opacity-100">
        <X className="h-4 w-4" />
      </button>
    </div>
  )
}
