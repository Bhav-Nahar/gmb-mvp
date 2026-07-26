'use client'

import { useState } from 'react'
import { Loader2, CheckCircle2, ArrowRight } from 'lucide-react'
import { getAttribution } from '@/lib/attribution'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

// Public local-SEO lead form. Posts to the unauthenticated lpseo lead endpoint,
// which emails the platform super-admins (no CRM row). `page` gives them context
// on which city x industry page the enquiry came from.
//
// Field set follows the industry x city template (guardrail 6.21): name, business,
// phone, locations, website, primary goal, consent, plus the stored UTM / GCLID /
// landing-page attribution. Success renders only after the endpoint confirms, and
// a failed submit keeps everything the visitor typed.
export default function LpseoLeadForm({ page, submitLabel }: { page: string; submitLabel?: string }) {
  const [form, setForm] = useState({
    name: '', clinic: '', phone: '', website: '',
    locations: '1 location', goal: 'More calls and enquiries',
    company: '', // honeypot: hidden from humans, bots fill it
  })
  const [consent, setConsent] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (!form.name.trim() || !form.clinic.trim() || !form.phone.trim()) {
      setError('Please add your name, business name and phone.')
      return
    }
    if (!consent) {
      setError('Please confirm you are happy for us to contact you about this request.')
      return
    }
    setSubmitting(true)
    try {
      const a = getAttribution()
      const res = await fetch(`${API_BASE}/public/lpseo/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          page,
          utm_source: a.utm_source,
          utm_medium: a.utm_medium,
          utm_campaign: a.utm_campaign,
          gclid: a.gclid,
          landing_page: a.landing_page,
        }),
      })
      // Success only on a confirmed successful response, never optimistically.
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

  if (done) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-8 text-center">
        <CheckCircle2 className="h-9 w-9 text-emerald-500" />
        <h3 className="text-lg font-bold text-foreground">Request received</h3>
        <p className="max-w-sm text-sm text-muted-foreground">Thanks. Our team will review your profile and get back with a prioritised local SEO opportunity list.</p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <div>
        <label className={labelCls} htmlFor="lp-name">Your name</label>
        <input id="lp-name" className={inputCls} value={form.name} onChange={(e) => update('name', e.target.value)} autoComplete="name" placeholder="Full name" required />
      </div>
      <div>
        <label className={labelCls} htmlFor="lp-clinic">Business or group name</label>
        <input id="lp-clinic" className={inputCls} value={form.clinic} onChange={(e) => update('clinic', e.target.value)} placeholder="Clinic or company" required />
      </div>
      <div>
        <label className={labelCls} htmlFor="lp-phone">Phone / WhatsApp</label>
        <input id="lp-phone" className={inputCls} value={form.phone} onChange={(e) => update('phone', e.target.value)} autoComplete="tel" inputMode="tel" placeholder="+91" required />
      </div>
      <div>
        <label className={labelCls} htmlFor="lp-locations">Number of locations</label>
        <select id="lp-locations" className={inputCls} value={form.locations} onChange={(e) => update('locations', e.target.value)}>
          <option>1 location</option>
          <option>2 to 5 locations</option>
          <option>6 to 20 locations</option>
          <option>21+ locations</option>
        </select>
      </div>
      <div className="sm:col-span-2">
        <label className={labelCls} htmlFor="lp-website">Website or Google Maps link</label>
        <input id="lp-website" className={inputCls} value={form.website} onChange={(e) => update('website', e.target.value)} inputMode="url" placeholder="https://" />
      </div>
      <div className="sm:col-span-2">
        <label className={labelCls} htmlFor="lp-goal">Primary goal</label>
        <select id="lp-goal" className={inputCls} value={form.goal} onChange={(e) => update('goal', e.target.value)}>
          <option>More calls and enquiries</option>
          <option>Better Google Maps visibility</option>
          <option>More reviews and stronger reputation</option>
          <option>Visibility across multiple locations</option>
          <option>AI search visibility</option>
          <option>A full local SEO audit first</option>
        </select>
      </div>

      {/* Honeypot: off-screen and hidden from assistive tech, never shown to a human. */}
      <div className="hidden" aria-hidden>
        <label htmlFor="lp-company">Company</label>
        <input id="lp-company" tabIndex={-1} autoComplete="off" value={form.company} onChange={(e) => update('company', e.target.value)} />
      </div>

      <label htmlFor="lp-consent" className="flex items-start gap-2.5 text-[11px] leading-relaxed text-muted-foreground sm:col-span-2">
        <input id="lp-consent" type="checkbox" className="mt-0.5 h-4 w-4 shrink-0 rounded border-border accent-[hsl(var(--primary))]" checked={consent} onChange={(e) => setConsent(e.target.checked)} required />
        <span>I agree that Pinzo may contact me about this request. See our <a href="/privacy" className="font-semibold text-primary underline-offset-4 hover:underline">privacy policy</a>.</span>
      </label>

      {error && <p role="alert" className="text-xs font-semibold text-rose-500 sm:col-span-2">{error}</p>}
      <button type="submit" disabled={submitting} className="flex min-h-[44px] items-center justify-center gap-2 rounded-lg bg-primary px-6 py-3.5 text-sm font-bold text-primary-foreground shadow-lg transition-colors hover:bg-primary/90 disabled:opacity-60 sm:col-span-2">
        {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <>{submitLabel || 'Request my free audit'} <ArrowRight className="h-4 w-4" /></>}
      </button>
      <p className="text-[11px] leading-relaxed text-muted-foreground sm:col-span-2">No ranking guarantees. You get a prioritised review of your profile, website, service coverage and local visibility. No password sharing.</p>
    </form>
  )
}
