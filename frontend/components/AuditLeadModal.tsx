'use client'

import { useEffect, useRef, useState } from 'react'
import { Loader2, CheckCircle2, ArrowRight, Clock } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { getAttribution } from '@/lib/attribution'
import {
  trackAuditFormOpen, trackGenerateLead, trackLeadSignUp, trackFormError, trackCustomerData,
  type CtaLocation,
} from '@/lib/analytics'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

// "Request my free audit" modal for the paid GBP landing page. Posts to the same
// public endpoint as the local-SEO landing forms, so the enquiry lands in the
// existing super-admin Leads tab (/admin/leads) and the notification email.
//
// The audit is prepared by a person, so every promise here is about someone getting
// back to them — nothing on this path connects Google or runs instantly.
//
// Five fields, four required. Job title, city and website were cut: none of them
// changed how the audit actually gets done, and each one costs conversions on cold
// paid traffic. The team asks for whatever else it needs on the follow-up.
export default function AuditLeadModal({ open, onOpenChange, page, ctaLocation }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  page: string
  ctaLocation?: CtaLocation
}) {
  const [form, setForm] = useState({
    name: '', phone: '', email: '', stores: '', companyName: '',
    company: '', // honeypot: hidden from humans, bots fill it
  })
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  // One conversion per lead, whatever the visitor does with the modal afterwards.
  const converted = useRef(false)

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  // view_promotion — the offer was actually shown, not merely clicked.
  useEffect(() => {
    if (open) trackAuditFormOpen(ctaLocation ?? 'hero')
  }, [open, ctaLocation])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (submitting || converted.current) return
    if (!/^\d{10}$/.test(form.phone.replace(/\D/g, '').replace(/^91(?=\d{10}$)/, ''))) {
      setError('Please enter a valid 10-digit mobile number.')
      trackFormError('audit_form: invalid phone')
      return
    }
    setSubmitting(true)
    try {
      const a = getAttribution()
      const res = await fetch(`${API_BASE}/public/lpseo/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          phone: form.phone,
          email: form.email,
          clinic: form.companyName,
          locations: form.stores,
          goal: 'Free GBP audit request',
          company: form.company,
          page,
          utm_source: a.utm_source,
          utm_medium: a.utm_medium,
          utm_campaign: a.utm_campaign,
          gclid: a.gclid,
          landing_page: a.landing_page,
        }),
      })
      // Success only on a confirmed response — never optimistically.
      if (!res.ok) throw new Error(`lead POST ${res.status}`)
      const body = await res.json().catch(() => ({}))
      converted.current = true
      // Raw PII for GTM to hash — this is what powers Google Ads enhanced
      // conversions for leads. Pushed before generate_lead so the values are
      // already in the dataLayer when the conversion tag reads them.
      trackCustomerData({ name: form.name, mobile: form.phone, email: form.email })
      trackGenerateLead({
        lead_id: body?.id,
        cta_location: ctaLocation,
        locationsCount: Number(form.stores.replace(/\D/g, '')) || undefined,
        email: form.email,
      })
      // Same lead, also as sign_up — that's the event the Ads conversion goal
      // currently reads. Remove once generate_lead is imported into Ads itself.
      trackLeadSignUp({ lead_id: body?.id, cta_location: ctaLocation, email: form.email })
      setDone(true)
    } catch (err) {
      setError('Something went wrong. Please try again or WhatsApp us.')
      trackFormError(`audit_form: ${err instanceof Error ? err.message : 'submit failed'}`)
    } finally {
      setSubmitting(false)
    }
  }

  const inputCls = 'h-11 w-full rounded-lg border border-border bg-background px-3 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15'
  const labelCls = 'mb-1.5 block text-[11px] font-bold uppercase tracking-wide text-muted-foreground'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        {done ? (
          <div className="flex flex-col items-center justify-center gap-3 py-6 text-center">
            <CheckCircle2 className="h-9 w-9 text-emerald-500" />
            <DialogTitle className="text-lg font-bold">Request received</DialogTitle>
            <DialogDescription className="max-w-sm text-sm">
              Our local visibility team is on it. You&apos;ll get your branch-wise audit
              within 1 business day, on the email and number you shared.
            </DialogDescription>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Request your free GBP audit</DialogTitle>
              <DialogDescription>
                Tell us where to send it. Our team reviews your Google Business Profiles
                by hand and comes back with the gaps worth fixing first.
              </DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
              <div>
                <label className={labelCls} htmlFor="al-name">Name *</label>
                <input id="al-name" name="name" className={inputCls} value={form.name} onChange={(e) => update('name', e.target.value)} autoComplete="name" placeholder="Full name" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-phone">10-digit mobile number *</label>
                <input id="al-phone" name="phone" className={inputCls} value={form.phone} onChange={(e) => update('phone', e.target.value)} autoComplete="tel" inputMode="numeric" placeholder="9876543210" required />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls} htmlFor="al-email">Email *</label>
                <input id="al-email" name="email" type="email" className={inputCls} value={form.email} onChange={(e) => update('email', e.target.value)} autoComplete="email" placeholder="you@company.com" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-company">Business name *</label>
                <input id="al-company" name="organization" className={inputCls} value={form.companyName} onChange={(e) => update('companyName', e.target.value)} autoComplete="organization" placeholder="As it appears on Google" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-stores">No. of locations</label>
                <input id="al-stores" name="locations" className={inputCls} value={form.stores} onChange={(e) => update('stores', e.target.value)} inputMode="numeric" placeholder="e.g. 12" />
              </div>

              {/* Honeypot: hidden from humans and assistive tech, bots fill it. */}
              <div className="hidden" aria-hidden>
                <label htmlFor="al-hp">Company</label>
                <input id="al-hp" tabIndex={-1} autoComplete="off" value={form.company} onChange={(e) => update('company', e.target.value)} />
              </div>

              {error && <p role="alert" className="text-xs font-semibold text-rose-500 sm:col-span-2">{error}</p>}

              <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/30 p-2.5 text-[11px] font-medium leading-relaxed text-muted-foreground sm:col-span-2">
                <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                Your branch-wise audit arrives within 1 business day. No payment, and no
                Google account access needed to receive it.
              </p>

              <button type="submit" disabled={submitting} className="flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 disabled:opacity-60 sm:col-span-2">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Request my free audit <ArrowRight className="h-4 w-4" /></>}
              </button>
              <p className="text-[11px] leading-relaxed text-muted-foreground sm:col-span-2">
                By submitting you agree that Pinzo may contact you about this request. See our{' '}
                <a href="/privacy" className="font-semibold text-primary underline-offset-4 hover:underline">privacy policy</a>.
              </p>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
