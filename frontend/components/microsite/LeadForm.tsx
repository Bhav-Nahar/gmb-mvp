'use client'

import React, { useState } from 'react'
import { Toaster, toast } from 'sonner'

interface LeadFormProps {
  slug: string
  businessName: string
  whatsapp?: string | null // GBP WhatsApp link; only used if present
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

export default function LeadForm({ slug, businessName, whatsapp }: LeadFormProps) {
  const [form, setForm] = useState({ name: '', phone: '', email: '', message: '' })
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)

  const update = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      toast.error('Please enter your name')
      return
    }
    setSubmitting(true)
    try {
      const res = await fetch(`${API_BASE}/public/microsites/${slug}/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (!res.ok) throw new Error(res.status === 429 ? 'Too many requests, try again shortly.' : 'Could not send')

      toast.success('Thank you! Your enquiry has been sent.')
      setDone(true)

      // Only when the business has a GBP WhatsApp link: offer to also send on WhatsApp.
      if (whatsapp) {
        const text = encodeURIComponent(
          `Hi ${businessName}, I'm ${form.name}.` +
          (form.phone ? ` Phone: ${form.phone}.` : '') +
          (form.message ? ` ${form.message}` : '')
        )
        const sep = whatsapp.includes('?') ? '&' : '?'
        window.open(`${whatsapp}${sep}text=${text}`, '_blank', 'noopener')
      }
    } catch (err: any) {
      toast.error(err?.message || 'Something went wrong. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section id="enquiry" className="scroll-mt-28">
      <Toaster richColors position="top-center" />
      <div className="glass-panel border border-border shadow-xl rounded-[2rem] p-6 sm:p-8 animate-fade-up relative overflow-hidden bg-card">
        {/* Glow behind the form */}
        <div className="absolute -top-24 -right-24 w-48 h-48 rounded-full bg-primary/10 blur-3xl pointer-events-none"></div>
        
        <div className="mb-8 relative z-10">
          <h2 className="text-2xl font-black text-foreground tracking-tight mb-2">
            Get in touch
          </h2>
          <p className="text-muted-foreground text-sm">
            Send us your details and we&apos;ll get back to you shortly.
          </p>
        </div>

        {done ? (
          <div className="text-center animate-fade-in py-8 relative z-10">
            <div className="w-16 h-16 rounded-full bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto mb-4 text-3xl shadow-inner">
              ✓
            </div>
            <h3 className="text-xl font-black text-foreground mb-2">Enquiry received</h3>
            <p className="text-muted-foreground text-sm mb-6">Thank you for reaching out. We&apos;ll contact you soon.</p>
            <button 
              onClick={() => { setForm({ name: '', phone: '', email: '', message: '' }); setDone(false) }} 
              className="px-6 py-2.5 rounded-full text-sm font-bold bg-primary text-primary-foreground hover:bg-primary/90 transition-all shadow-md active:scale-95"
            >
              Send another
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5 relative z-10" style={{ animationDelay: '100ms' }}>
            <div className="grid grid-cols-1 gap-5">
              <div>
                <label className="block text-xs font-bold text-foreground mb-1.5">Name *</label>
                <input 
                  value={form.name} 
                  onChange={(e) => update('name', e.target.value)} 
                  required 
                  placeholder="Your name"
                  className="w-full rounded-xl border border-border bg-background/50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition-all shadow-sm" 
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-foreground mb-1.5">Phone</label>
                <input 
                  value={form.phone} 
                  onChange={(e) => update('phone', e.target.value)} 
                  type="tel" 
                  inputMode="tel" 
                  placeholder="Mobile number"
                  className="w-full rounded-xl border border-border bg-background/50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition-all shadow-sm" 
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-bold text-foreground mb-1.5">Email</label>
              <input 
                value={form.email} 
                onChange={(e) => update('email', e.target.value)} 
                type="email" 
                placeholder="you@example.com"
                className="w-full rounded-xl border border-border bg-background/50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition-all shadow-sm" 
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-foreground mb-1.5">Message</label>
              <textarea 
                value={form.message} 
                onChange={(e) => update('message', e.target.value)} 
                rows={3} 
                placeholder="How can we help you?"
                className="w-full rounded-xl border border-border bg-background/50 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary/40 transition-all resize-none shadow-sm" 
              />
            </div>
            <button 
              type="submit" 
              disabled={submitting}
              className="w-full bg-primary text-primary-foreground font-bold text-sm py-3.5 rounded-xl shadow-md hover:bg-primary/90 hover:shadow-lg hover:-translate-y-0.5 disabled:opacity-60 disabled:hover:translate-y-0 disabled:cursor-not-allowed transition-all mt-2"
            >
              {submitting ? 'Sending…' : 'Send Enquiry'}
            </button>
          </form>
        )}
      </div>
    </section>
  )
}
