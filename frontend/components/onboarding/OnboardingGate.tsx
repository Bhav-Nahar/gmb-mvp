'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, ShieldCheck, Sparkles } from 'lucide-react'
import { useCheckoutSubscription, useConfirmPayment, useQuote, useAuditSummary } from '@/hooks/useBilling'
import { useRazorpay } from '@/hooks/useRazorpay'
import { useAuth } from '@/hooks/useAuth'
import { isPaymentVerificationError, PAYMENT_VERIFICATION_FAILED_MSG } from '@/lib/payment'
import { track, trackBeginCheckout, trackAddPaymentInfo, trackTrialStart } from '@/lib/analytics'
import { api } from '@/lib/api'
import { COUNTRY_CODES, parsePhoneState } from '@/lib/phone'

// What the trial unlocks (Basic tier). Shown as the value stack under the findings.
const UNLOCKS = [
  'Full profile health score',
  '10 free AI credits for review replies',
  'Competitor benchmarks',
  'Review and ranking analytics',
]

/**
 * Full-screen, non-dismissible audit result + paywall shown while an org is in the
 * pre-payment onboarding state (synced audit, no mandate yet). One confident screen:
 * what we found, what they unlock, and a single "Start Free Trial" action. There is no
 * dismiss. Frontend twin of the server gate (require_premium / check_billing_lock).
 *
 * Rendered app-wide by BillingBanners, only when there is at least one audited location.
 */
export function OnboardingGate({ locations }: { locations: number }) {
  const { user } = useAuth()
  const { mutateAsync: checkoutSubscription } = useCheckoutSubscription()
  const { mutateAsync: confirmPayment } = useConfirmPayment()
  const { openRazorpay } = useRazorpay()
  const queryClient = useQueryClient()
  const [submitting, setSubmitting] = useState(false)
  // Phone is collected inline here (one screen, one click) instead of a separate step.
  const [countryCode, setCountryCode] = useState(() => parsePhoneState(user?.phone).code)
  const [phoneDigits, setPhoneDigits] = useState(() => parsePhoneState(user?.phone).digits)
  const phoneOk = phoneDigits.length >= 7 && phoneDigits.length <= 15

  const count = Math.max(1, locations || 1)
  const { data: quote } = useQuote(count, 'monthly', 'basic', true)
  const { data: audit } = useAuditSummary(true)
  const monthly = quote ? Math.round((quote.total_paise ?? 0) / 100) : undefined
  const criticalCount = audit?.critical_issues ?? 0
  const hasIssues = criticalCount > 0
  // Only Owner/Admin can start the trial (checkout is admin-only server-side). A
  // non-admin teammate sees a "ask your admin" message instead of a CTA that would 403.
  const isAdmin = user?.role === 'Owner' || user?.role === 'Admin'

  useEffect(() => {
    // Once per session, not per mount — this is the top of the payment funnel.
    if (!sessionStorage.getItem('pz_gate_viewed')) {
      sessionStorage.setItem('pz_gate_viewed', '1')
      track('gate_viewed', { email: user?.email, locations_included: count })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Best-effort lead capture: persist the number as they finish typing, so a bounce at
  // the wall still leaves a contact. Silent on failure — checkout re-sends it anyway.
  const savePhoneLead = () => {
    if (phoneOk && `${countryCode}${phoneDigits}` !== user?.phone) {
      api.post('/users/me/phone', { phone: `${countryCode}${phoneDigits}` }).catch(() => {})
    }
  }

  const startTrial = async () => {
    if (submitting) return
    if (!phoneOk) {
      toast.error('Please enter a valid mobile number to start your trial.')
      return
    }
    const razorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY
    if (!razorpayKey) {
      toast.error('Payments are not set up (missing key). Please contact support.')
      return
    }
    setSubmitting(true)
    trackBeginCheckout({ user_id: user?.id, email: user?.email })
    try {
      const response = await checkoutSubscription({
        location_count: count, interval: 'monthly', plan_tier: 'basic', phone: `${countryCode}${phoneDigits}`,
      })
      await openRazorpay({
        key: razorpayKey,
        subscription_id: response.subscription.id,
        name: 'Pinzo',
        description: `7-day free trial for ${count} location${count > 1 ? 's' : ''}`,
        handler: async (res: any) => {
          // Payment info exists only now — the mandate was approved in Razorpay.
          trackAddPaymentInfo({
            plan_name: 'Trial', paymentTerm: 'monthly', value: 0,
            locations_included: count, user_id: user?.id, email: user?.email,
          })
          try {
            const result = await confirmPayment({
              razorpay_payment_id: res.razorpay_payment_id,
              razorpay_signature: res.razorpay_signature,
              razorpay_subscription_id: res.razorpay_subscription_id,
            })
            if (result?.activated) {
              trackTrialStart({ user_id: user?.id ?? '', email: user?.email, locationsCount: count })
              toast.success('Your free trial is active. Welcome in.')
            } else {
              toast.info('Verifying your payment method. Your trial will unlock shortly.')
            }
          } catch (err) {
            if (isPaymentVerificationError(err)) toast.error(PAYMENT_VERIFICATION_FAILED_MSG)
            else toast.info('Verifying your payment method. Your trial will unlock shortly.')
          } finally {
            setSubmitting(false)
            queryClient.invalidateQueries({ queryKey: ['billing_status'] })
            window.dispatchEvent(new Event('billing:refresh'))
          }
        },
        onFailure: (err: any) => {
          setSubmitting(false)
          toast.error(err?.description || 'We could not verify your payment method. Trial not started.')
        },
        modal: {
          ondismiss: () => {
            track('checkout_dismissed', { email: user?.email, locations_included: count })
            setSubmitting(false)
          },
        },
      } as any)
    } catch (error: any) {
      setSubmitting(false)
      toast.error(error?.message || 'We could not start your trial. Please try again.')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-neutral-950/20 p-4">
      <div className="my-auto w-full max-w-md overflow-hidden rounded-2xl border bg-card shadow-2xl">
        {/* Header: audit-complete confirmation */}
        <div className="border-b bg-muted/40 px-6 py-4">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
            <CheckCircle2 className="h-3.5 w-3.5" />
            Audit complete
          </div>
          <h2 className="mt-3 text-xl font-bold leading-tight">
            {hasIssues
              ? `We found ${criticalCount} issue${criticalCount === 1 ? '' : 's'} costing you customers`
              : 'Your audit is ready'}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {hasIssues
              ? `Across your ${locations} Google location${locations === 1 ? '' : 's'}. Start your free trial to see the full report and fix them.`
              : `We analyzed your ${locations} Google location${locations === 1 ? '' : 's'}. Start your free trial to unlock the full report.`}
          </p>
        </div>

        <div className="space-y-5 px-6 py-5">
          {/* Findings */}
          {hasIssues && (
            <ul className="space-y-2.5">
              {audit!.issues.slice(0, 4).map((it, i) => (
                <li key={i} className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
                  <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                  <div>
                    <p className="text-sm font-semibold leading-tight">{it.label}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">{it.detail}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {/* Value stack */}
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Sparkles className="h-3.5 w-3.5" /> Your trial unlocks
            </p>
            <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
              {UNLOCKS.map((u) => (
                <li key={u} className="flex items-center gap-2 text-sm">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  {u}
                </li>
              ))}
            </ul>
          </div>

          {isAdmin ? (
            <>
              {/* Phone (inline, so it is one screen and one click to Razorpay) */}
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Mobile number
                </span>
                <div className="flex items-stretch overflow-hidden rounded-xl border focus-within:ring-2 focus-within:ring-ring">
                  <select
                    value={countryCode}
                    onChange={(e) => setCountryCode(e.target.value)}
                    className="bg-muted px-2 py-2.5 text-sm font-semibold text-muted-foreground outline-none border-r border-border hover:bg-muted/80 cursor-pointer"
                  >
                    {COUNTRY_CODES.map(c => (
                      <option key={c.code} value={c.code}>{c.label}</option>
                    ))}
                  </select>
                  <input
                    type="tel"
                    inputMode="numeric"
                    value={phoneDigits}
                    onChange={(e) => setPhoneDigits(e.target.value.replace(/\D/g, '').slice(0, 15))}
                    onBlur={savePhoneLead}
                    placeholder="98765 43210"
                    className="flex-1 bg-background px-4 py-2.5 text-sm focus:outline-none"
                  />
                </div>
              </label>

              {/* Price */}
              <div className="rounded-xl border bg-muted/30 p-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-base font-bold">7 days free</span>
                  <span className="inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">
                    No charge today
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {monthly !== undefined
                    ? `Then ₹${monthly.toLocaleString('en-IN')} per month. Cancel anytime.`
                    : 'Cancel anytime before your trial ends.'}
                </p>
              </div>

              {/* CTA */}
              <button
                type="button"
                onClick={startTrial}
                disabled={submitting}
                className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-60"
              >
                {submitting ? 'Starting your trial...' : 'Start Free Trial'}
              </button>

              {/* Trust */}
              <div className="space-y-2 text-center text-xs text-muted-foreground">
                <p className="flex items-center justify-center gap-1.5">
                  <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
                  Secure checkout via Razorpay. A ₹5 verification may appear and is refunded automatically.
                </p>
                <p className="text-[10px] leading-relaxed px-4">
                  By starting your trial, you agree to receive onboarding support, audit reports, and critical alerts via WhatsApp & SMS.
                </p>
              </div>
            </>
          ) : (
            <div className="rounded-xl border bg-muted/30 p-4 text-center text-sm text-muted-foreground">
              Your account owner or an admin needs to start the free trial to unlock the
              dashboard. Please ask them to sign in and activate it.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
