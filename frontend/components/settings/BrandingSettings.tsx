'use client'

import { useEffect, useState } from 'react'
import { Palette } from 'lucide-react'
import { api } from '@/lib/api'
import { useBranding, invalidateBranding } from '@/hooks/useBranding'

const FIELDS = [
  { key: 'brand_name', label: 'Agency name', placeholder: 'RankWise Digital', type: 'text' },
  { key: 'brand_logo_url', label: 'Logo URL', placeholder: 'https://rankwise.in/logo.png', type: 'url' },
  { key: 'brand_website_url', label: 'Website', placeholder: 'https://rankwise.in', type: 'url' },
] as const

type FormKey = typeof FIELDS[number]['key']

/** Renders nothing unless a super-admin has enabled agency mode for this org. */
export function BrandingSettings() {
  const state = useBranding()
  const [form, setForm] = useState<Record<FormKey, string>>({
    brand_name: '', brand_logo_url: '', brand_website_url: '',
  })
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null)

  useEffect(() => {
    if (!state) return
    setForm({
      brand_name: state.saved.brand_name ?? '',
      brand_logo_url: state.saved.brand_logo_url ?? '',
      brand_website_url: state.saved.brand_website_url ?? '',
    })
  }, [state])

  if (!state?.is_agency) return null

  const save = async () => {
    setSaving(true)
    setStatus(null)
    try {
      await api.patch('/branding', form)
      invalidateBranding()
      setStatus({ kind: 'ok', msg: 'Saved. New exports will use your branding.' })
    } catch (e: any) {
      setStatus({ kind: 'err', msg: e?.message || 'Could not save. Check the URLs and try again.' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section className="rounded-xl border border-border bg-card p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-1">
        <Palette className="h-5 w-5 text-indigo-600 dark:text-indigo-400 shrink-0" />
        <h3 className="text-sm font-bold text-foreground">Report branding</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-4 max-w-lg">
        Your logo and website appear on exported PDF reports and the weekly email instead of ours.
        Leave a field blank to keep the default.
      </p>

      <div className="space-y-3">
        {FIELDS.map((f) => (
          <div key={f.key}>
            <label htmlFor={f.key} className="block text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5">
              {f.label}
            </label>
            <input
              id={f.key}
              type={f.type}
              value={form[f.key]}
              placeholder={f.placeholder}
              onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              className="w-full h-11 rounded-xl border border-border bg-background px-4 text-sm font-medium text-foreground placeholder-muted-foreground focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 transition-all"
            />
          </div>
        ))}
      </div>

      {form.brand_logo_url && (
        <div className="mt-4 rounded-lg border border-border/60 bg-muted/20 p-3">
          <p className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground mb-2">Preview</p>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={form.brand_logo_url}
            alt="Logo preview"
            className="h-8"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        </div>
      )}

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="inline-flex h-10 items-center rounded-xl bg-indigo-600 px-4 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {saving ? 'Saving…' : 'Save branding'}
        </button>
        {status && (
          <span className={`text-xs font-semibold ${status.kind === 'ok' ? 'text-emerald-600' : 'text-red-600'}`}>
            {status.msg}
          </span>
        )}
      </div>
    </section>
  )
}
