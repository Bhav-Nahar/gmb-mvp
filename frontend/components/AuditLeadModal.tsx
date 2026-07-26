'use client'

import { useState } from 'react'
import { Loader2, CheckCircle2, ArrowRight } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import { getAttribution } from '@/lib/attribution'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

// "Get my custom audit" modal for the paid GBP landing page. Posts to the same
// public endpoint as the local-SEO landing forms, so the enquiry lands in the
// existing super-admin Leads tab (/admin/leads) and the notification email.
//
// ponytail: job title + city ride along in `message` rather than getting their own
// columns — the admin details panel already renders it. Give them columns when
// someone needs to filter or export by city.
export default function AuditLeadModal({ open, onOpenChange, page }: {
  open: boolean
  onOpenChange: (open: boolean) => void
  page: string
}) {
  const [form, setForm] = useState({
    name: '', phone: '', email: '', stores: '', jobTitle: '',
    companyName: '', website: '', city: '',
    company: '', // honeypot: hidden from humans, bots fill it
  })
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!/^\d{10}$/.test(form.phone.replace(/\D/g, '').replace(/^91(?=\d{10}$)/, ''))) {
      setError('Please enter a valid 10-digit mobile number.')
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
          website: form.website,
          locations: form.stores,
          goal: 'Custom GBP audit',
          message: `Job title: ${form.jobTitle}\nCity: ${form.city}`,
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
      if (!res.ok) throw new Error('Request failed')
      setDone(true)
    } catch {
      setError('Something went wrong. Please try again or WhatsApp us.')
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
              Thanks. Our team will review your Google Business Profiles and get back with your custom audit shortly.
            </DialogDescription>
          </div>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>Fill in the details to get your custom audit</DialogTitle>
              <DialogDescription>Fill out this form and we&apos;ll reach out to you shortly.</DialogDescription>
            </DialogHeader>

            <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 pt-2 sm:grid-cols-2">
              <div>
                <label className={labelCls} htmlFor="al-name">Name *</label>
                <input id="al-name" className={inputCls} value={form.name} onChange={(e) => update('name', e.target.value)} autoComplete="name" placeholder="Full name" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-phone">10-digit mobile number *</label>
                <input id="al-phone" className={inputCls} value={form.phone} onChange={(e) => update('phone', e.target.value)} autoComplete="tel" inputMode="numeric" placeholder="9876543210" required />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls} htmlFor="al-email">Official email ID *</label>
                <input id="al-email" type="email" className={inputCls} value={form.email} onChange={(e) => update('email', e.target.value)} autoComplete="email" placeholder="you@company.com" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-stores">No. of stores</label>
                <input id="al-stores" className={inputCls} value={form.stores} onChange={(e) => update('stores', e.target.value)} inputMode="numeric" placeholder="e.g. 12" />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-title">Job title *</label>
                <input id="al-title" className={inputCls} value={form.jobTitle} onChange={(e) => update('jobTitle', e.target.value)} autoComplete="organization-title" placeholder="e.g. Marketing Head" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-company">Company name *</label>
                <input id="al-company" className={inputCls} value={form.companyName} onChange={(e) => update('companyName', e.target.value)} autoComplete="organization" placeholder="Company" required />
              </div>
              <div>
                <label className={labelCls} htmlFor="al-city">City name *</label>
                <input id="al-city" className={inputCls} value={form.city} onChange={(e) => update('city', e.target.value)} autoComplete="address-level2" placeholder="City" required />
              </div>
              <div className="sm:col-span-2">
                <label className={labelCls} htmlFor="al-website">Company website URL *</label>
                <input id="al-website" className={inputCls} value={form.website} onChange={(e) => update('website', e.target.value)} inputMode="url" placeholder="https://" required />
              </div>

              {/* Honeypot: hidden from humans and assistive tech, bots fill it. */}
              <div className="hidden" aria-hidden>
                <label htmlFor="al-hp">Company</label>
                <input id="al-hp" tabIndex={-1} autoComplete="off" value={form.company} onChange={(e) => update('company', e.target.value)} />
              </div>

              {error && <p role="alert" className="text-xs font-semibold text-rose-500 sm:col-span-2">{error}</p>}

              <button type="submit" disabled={submitting} className="flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 disabled:opacity-60 sm:col-span-2">
                {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>Get my custom audit <ArrowRight className="h-4 w-4" /></>}
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
