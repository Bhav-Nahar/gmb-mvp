'use client'

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { api } from '@/lib/api'
import SeoSubNav from '@/components/admin/SeoSubNav'
import {
  Upload, RefreshCw, CheckCircle2, AlertTriangle, Trash2, ExternalLink, Download,
  Eye, EyeOff, Zap, BarChart3, ChevronDown,
} from 'lucide-react'

// Country pillars: one page per market at /{locale}/local-seo-services/. There is at
// most one row per country, so this is a short list rather than a paginated corpus.
interface Pillar {
  id: number
  country: string
  country_label: string
  locale: string
  status: string
  index_status: string
  quality_score: number | null
  meta_title: string
  published_at: string | null
  updated_at: string | null
}
interface GscMetric { clicks: number; impressions: number; ctr: number; position: number }
interface GscQuery extends GscMetric { query: string }
interface ImportResult {
  created: number; updated: number; failed: number
  results: { row: number; country: string | null; action: string; status?: string; error?: string }[]
}


// ── Content editor ───────────────────────────────────────────────────────────
// One textarea per field, using the same codec as the lpSEO editor and the import
// cell syntax: one item per line, fields joined by " :: ", sub-lists by " ; ".
type Kind = 'text' | 'list' | 'pair' | 'link' | 'service' | 'checklist' | 'package' | 'qa'
interface FieldDef { k: string; label: string; kind: Kind; rows?: number }

const TEXT_FIELDS: FieldDef[] = [
  { k: 'badge', label: 'Hero badge', kind: 'text' },
  { k: 'hero_copy', label: 'Hero copy', kind: 'text', rows: 3 },
  { k: 'primary_cta', label: 'Primary CTA label', kind: 'text' },
  { k: 'secondary_cta', label: 'Secondary CTA label', kind: 'text' },
  { k: 'direct_question', label: 'Direct answer, question', kind: 'text' },
  { k: 'direct_answer', label: 'Direct answer, body', kind: 'text', rows: 4 },
  { k: 'package_copy', label: 'Pricing explanation', kind: 'text', rows: 3 },
  { k: 'primary_keyword', label: 'Primary keyword', kind: 'text' },
]
const STRUCT_FIELDS: FieldDef[] = [
  { k: 'search_behaviour', label: 'Search behaviour  (title :: detail)', kind: 'pair', rows: 5 },
  { k: 'service_matrix', label: 'Service scope  (area :: what Pinzo manages :: why it matters)', kind: 'service', rows: 11 },
  { k: 'ranking_factors', label: 'Ranking principles  (title :: detail)', kind: 'pair', rows: 4 },
  { k: 'city_hubs', label: 'City hubs  (anchor :: url)', kind: 'link', rows: 7 },
  { k: 'industry_hubs', label: 'Industry hubs  (anchor :: url)', kind: 'link', rows: 7 },
  { k: 'single_location_points', label: 'Single location, bullets', kind: 'list', rows: 5 },
  { k: 'multi_location_points', label: 'Multi-location, bullets', kind: 'list', rows: 5 },
  { k: 'ai_entity_plan', label: 'AI search  (title :: detail)', kind: 'pair', rows: 6 },
  { k: 'safeguards', label: 'Safeguards  (title :: detail)', kind: 'pair', rows: 4 },
  { k: 'monthly_deliverables', label: 'Monthly deliverables', kind: 'list', rows: 9 },
  { k: 'roadmap_90_days', label: 'First 90 days  (phase :: detail)', kind: 'pair', rows: 4 },
  { k: 'buyer_checklist', label: 'Buyer checklist  (ask :: good evidence :: warning sign)', kind: 'checklist', rows: 5 },
  { k: 'packages', label: 'Packages  (name :: desc :: feature ; feature)', kind: 'package', rows: 4 },
  { k: 'proof_assets', label: 'Proof assets  (title :: detail)', kind: 'pair', rows: 4 },
  { k: 'audit_checklist', label: 'Sample audit rows  (check :: status)', kind: 'pair', rows: 6 },
  { k: 'faqs', label: 'FAQs  (question :: answer)', kind: 'qa', rows: 12 },
  { k: 'internal_links', label: 'Internal links  (anchor :: url)', kind: 'link', rows: 12 },
]
const ALL_FIELDS = [...TEXT_FIELDS, ...STRUCT_FIELDS]

const parts = (line: string) => line.split('::').map((s) => s.trim())
const sub = (s: string) => (s || '').split(';').map((x) => x.trim()).filter(Boolean)

function toText(kind: Kind, v: any): string {
  if (kind === 'text') return typeof v === 'string' ? v : ''
  return (Array.isArray(v) ? v : []).map((it: any) => {
    switch (kind) {
      case 'list': return String(it)
      case 'pair': return `${it.title || ''} :: ${it.detail || ''}`
      case 'link': return `${it.anchor || ''} :: ${it.url || ''}`
      case 'service': return `${it.area || ''} :: ${it.work || ''} :: ${it.why || ''}`
      case 'checklist': return `${it.ask || ''} :: ${it.good || ''} :: ${it.warning || ''}`
      case 'package': return `${it.name || ''} :: ${it.desc || ''} :: ${(it.features || []).join(' ; ')}`
      case 'qa': return `${it.q || ''} :: ${it.a || ''}`
      default: return ''
    }
  }).join('\n')
}

function fromText(kind: Kind, text: string): any {
  if (kind === 'text') return text.trim()
  const lines = (text || '').split('\n').map((s) => s.trim()).filter(Boolean)
  return lines.map((line) => {
    const p = parts(line)
    switch (kind) {
      case 'list': return line
      case 'pair': return { title: p[0] || '', detail: p[1] || '' }
      case 'link': return { anchor: p[0] || '', url: p[1] || '' }
      case 'service': return { area: p[0] || '', work: p[1] || '', why: p[2] || '' }
      case 'checklist': return { ask: p[0] || '', good: p[1] || '', warning: p[2] || '' }
      case 'package': return { name: p[0] || '', desc: p[1] || '', features: sub(p[2]) }
      case 'qa': return { q: p[0] || '', a: p.slice(1).join('::').trim() }
      default: return null
    }
  })
}

// Guardrail 5 forbids these four characters anywhere in the page copy, so the
// editor refuses to save them rather than letting a paste from Word through.
const FORBIDDEN = /[\u2013\u2014\u2011\u2212]/

// The global pillar lives at the bare path; every other market is locale-prefixed.
const publicPath = (p: Pillar) => (p.country === 'global' ? '/local-seo-services/' : `/${p.locale}/local-seo-services`)

const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '\u2014')
const GSC_DAYS = 28

export default function AdminCseoPage() {
  const scope = useSearchParams()?.get('scope') ?? null
  const [rows, setRows] = useState<Pillar[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [gsc, setGsc] = useState<{ configured: boolean; metrics: Record<string, GscMetric> } | null>(null)
  const [queries, setQueries] = useState<Record<number, GscQuery[]>>({})
  const [openQ, setOpenQ] = useState<number | null>(null)
  const [editing, setEditing] = useState<{
    id: number; meta: Record<string, string>; draft: Record<string, string>; content: Record<string, any>
  } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const flash = (m: string) => { setNotice(m); setTimeout(() => setNotice(''), 6000) }

  const load = async () => {
    setLoading(true); setError('')
    try {
      const d = await api.get<{ pages: Pillar[] }>('/admin/cseo')
      setRows(d.pages.filter((p) => (scope === 'global' ? p.country === 'global' : p.country !== 'global')))
    } catch (e: any) { setError(e.message || 'Failed to load') } finally { setLoading(false) }
  }
  const loadGsc = async () => {
    try { setGsc(await api.get('/admin/cseo/gsc-metrics', { days: String(GSC_DAYS) })) } catch { /* optional */ }
  }
  useEffect(() => { load(); loadGsc() }, [scope]) // eslint-disable-line react-hooks/exhaustive-deps

  const showQueries = async (id: number) => {
    if (openQ === id) { setOpenQ(null); return }
    setOpenQ(id)
    if (queries[id]) return
    try {
      const d = await api.get<{ queries: GscQuery[] }>(`/admin/cseo/${id}/gsc-queries`, { days: String(GSC_DAYS) })
      setQueries((q) => ({ ...q, [id]: d.queries }))
    } catch (e: any) { setError(e.message || 'Failed to load queries') }
  }

  const openEditor = async (id: number) => {
    setError('')
    try {
      const d = await api.get<any>(`/admin/cseo/${id}`)
      const c = d.content || {}
      setEditing({
        id,
        meta: {
          country_label: d.country_label ?? '', meta_title: d.meta_title ?? '',
          meta_description: d.meta_description ?? '', h1: d.h1 ?? '',
          canonical_url: d.canonical_url ?? '', quality_score: d.quality_score == null ? '' : String(d.quality_score),
        },
        draft: Object.fromEntries(ALL_FIELDS.map((f) => [f.k, toText(f.kind, c[f.k])])),
        // Everything the form does not render (page_id, template_version, launch
        // blockers...) is kept verbatim, because PATCH replaces content wholesale
        // and a save must never silently drop a key the editor happens not to show.
        content: c,
      })
    } catch (e: any) { setError(e.message || 'Failed to load page') }
  }

  const saveEditor = async () => {
    if (!editing) return
    const bad = [...Object.entries(editing.meta), ...Object.entries(editing.draft)]
      .filter(([, v]) => FORBIDDEN.test(v)).map(([k]) => k)
    if (bad.length) {
      setError(`Remove the en dash, em dash, nonbreaking hyphen or minus sign from: ${bad.join(', ')} (guardrail 5).`)
      return
    }
    setBusy(true); setError('')
    try {
      const content = { ...editing.content }
      for (const f of ALL_FIELDS) {
        const parsed = fromText(f.kind, editing.draft[f.k] ?? '')
        if (f.kind === 'text') { if (parsed) content[f.k] = parsed; else delete content[f.k] }
        else if ((parsed as any[]).length) content[f.k] = parsed
        else delete content[f.k]
      }
      const score = editing.meta.quality_score.trim()
      await api.patch(`/admin/cseo/${editing.id}`, {
        country: rows.find((r) => r.id === editing.id)?.country,
        country_label: editing.meta.country_label,
        meta_title: editing.meta.meta_title, meta_description: editing.meta.meta_description,
        h1: editing.meta.h1, canonical_url: editing.meta.canonical_url || null,
        index_status: rows.find((r) => r.id === editing.id)?.index_status,
        quality_score: score === '' ? null : Number(score),
        content,
      })
      setEditing(null); flash('Saved.'); await load()
    } catch (e: any) { setError(e.message || 'Save failed') }
    finally { setBusy(false) }
  }

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true); setError('')
    try { await fn(); flash(msg); await load() }
    catch (e: any) { setError(e.message || 'Action failed') }
    finally { setBusy(false) }
  }

  const importFile = async (file: File) => {
    setBusy(true); setError(''); setResult(null)
    try {
      const fd = new FormData()
      fd.append('file', file)
      const r = await api.post<ImportResult>('/admin/cseo/import', fd)
      setResult(r)
      flash(`Imported: ${r.created} created, ${r.updated} updated, ${r.failed} failed.`)
      await load()
    } catch (e: any) { setError(e.message || 'Import failed') }
    finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }

  const downloadTemplate = async () => {
    try {
      const meta = await api.get<{ columns: string[] }>('/admin/cseo/import/columns')
      const csv = meta.columns.join(',') + '\n'
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
      a.download = 'pinzo-country-pillar-template.csv'; a.click(); URL.revokeObjectURL(a.href)
    } catch (e: any) { setError(e.message || 'Failed to load columns') }
  }

  const inputCls = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/15'
  const labelCls = 'mb-1.5 block text-[11px] font-bold uppercase tracking-wide text-muted-foreground'

  // ── Editor view ────────────────────────────────────────────────────────────
  if (editing) {
    const meta = (k: string, label: string, rows = 1) => (
      <div key={k} className={rows > 1 ? 'sm:col-span-2' : ''}>
        <label className={labelCls} htmlFor={`m-${k}`}>{label}</label>
        {rows > 1
          ? <textarea id={`m-${k}`} rows={rows} className={inputCls} value={editing.meta[k]} onChange={(e) => setEditing({ ...editing, meta: { ...editing.meta, [k]: e.target.value } })} />
          : <input id={`m-${k}`} className={inputCls} value={editing.meta[k]} onChange={(e) => setEditing({ ...editing, meta: { ...editing.meta, [k]: e.target.value } })} />}
      </div>
    )
    return (
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-lg font-bold">Edit country pillar</h1>
            <p className="mt-0.5 text-xs text-muted-foreground">Changes go live on save. Fields not shown here (page id, template version, launch blockers) are preserved untouched.</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setEditing(null)} className="rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground">Cancel</button>
            <button onClick={saveEditor} disabled={busy} className="rounded-lg bg-primary px-4 py-2 text-xs font-bold uppercase tracking-wider text-primary-foreground disabled:opacity-50">{busy ? 'Saving…' : 'Save'}</button>
          </div>
        </div>

        {error && <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs font-semibold text-red-500"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}

        <div className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-sm font-bold text-foreground">Identity and metadata</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {meta('country_label', 'Country label')}
            {meta('quality_score', 'Quality score (0-100)')}
            {meta('h1', 'H1')}
            {meta('canonical_url', 'Canonical URL')}
            {meta('meta_title', `Meta title (${editing.meta.meta_title.length} chars, target 45-60)`, 2)}
            {meta('meta_description', `Meta description (${editing.meta.meta_description.length} chars, target 140-160)`, 3)}
          </div>
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-sm font-bold text-foreground">Copy</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {TEXT_FIELDS.map((f) => (
              <div key={f.k} className={(f.rows ?? 1) > 1 ? 'sm:col-span-2' : ''}>
                <label className={labelCls} htmlFor={`f-${f.k}`}>{f.label}</label>
                {(f.rows ?? 1) > 1
                  ? <textarea id={`f-${f.k}`} rows={f.rows} className={inputCls} value={editing.draft[f.k]} onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, [f.k]: e.target.value } })} />
                  : <input id={`f-${f.k}`} className={inputCls} value={editing.draft[f.k]} onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, [f.k]: e.target.value } })} />}
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-sm font-bold text-foreground">
            Sections <span className="font-normal text-muted-foreground">one item per line, fields joined by <code>::</code>, sub-lists by <code>;</code></span>
          </h2>
          {STRUCT_FIELDS.map((f) => (
            <div key={f.k}>
              <label className={labelCls} htmlFor={`s-${f.k}`}>{f.label}</label>
              <textarea id={`s-${f.k}`} rows={f.rows ?? 4} className={`${inputCls} font-mono text-xs`} value={editing.draft[f.k]} onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, [f.k]: e.target.value } })} />
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <SeoSubNav />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">{scope === 'global' ? 'Global pillar' : 'Country pillars'}</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            The national page at pinzo.io/en-&#123;country&#125;/local-seo-services/. It replaces the auto-generated
            industry hub for any market that has one, and is the parent every city and industry page links back to.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={downloadTemplate} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground"><Download className="h-3.5 w-3.5" /> CSV template</button>
          <button onClick={() => fileRef.current?.click()} disabled={busy} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground disabled:opacity-50"><Upload className="h-3.5 w-3.5" /> Import CSV/XLSX</button>
          <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
          <button onClick={load} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground"><RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh</button>
        </div>
      </div>

      {gsc && !gsc.configured && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs font-semibold text-amber-600"><AlertTriangle className="h-4 w-4 shrink-0" />Search Console isn&apos;t connected. Set GSC_SERVICE_ACCOUNT_JSON and GSC_PROPERTY_URL to see clicks, impressions and queries here.</div>
      )}

      {notice && <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-semibold text-emerald-600"><CheckCircle2 className="h-4 w-4 shrink-0" />{notice}</div>}
      {error && <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs font-semibold text-red-500"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
      {result && result.results.some((r) => r.action === 'error') && (
        <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="text-xs font-bold text-amber-600">Rows with errors</p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {result.results.filter((r) => r.action === 'error').map((r) => (<li key={r.row}>Row {r.row}{r.country ? ` (${r.country})` : ''}: {r.error}</li>))}
          </ul>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-3 font-bold">Country</th>
                <th className="px-4 py-3 font-bold">Title</th>
                <th className="px-4 py-3 font-bold">Status</th>
                <th className="px-4 py-3 font-bold">Robots</th>
                <th className="px-4 py-3 font-bold">Score</th>
                <th className="px-4 py-3 font-bold" title={`Search Console, last ${GSC_DAYS} days`}>Clicks</th>
                <th className="px-4 py-3 font-bold">Impr.</th>
                <th className="px-4 py-3 font-bold">Pos.</th>
                <th className="px-4 py-3 font-bold">Updated</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-b border-border/60 align-top">
                  <td className="whitespace-nowrap px-4 py-3 font-bold">
                    {p.country_label}
                    <a href={publicPath(p)} target="_blank" rel="noopener noreferrer" className="ml-1.5 inline-flex text-muted-foreground hover:text-primary" aria-label={`Open the ${p.country_label} pillar`}><ExternalLink className="h-3 w-3" /></a>
                    <div className="text-[11px] font-normal text-muted-foreground">{publicPath(p)}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{p.meta_title}</td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className={`text-[11px] font-bold ${p.status === 'published' ? 'text-emerald-600' : 'text-muted-foreground'}`}>{p.status}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span className={`text-[11px] font-bold ${p.index_status === 'index' ? 'text-emerald-600' : 'text-amber-600'}`}>{p.index_status}</span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs">{p.quality_score ?? '\u2014'}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs font-semibold">{gsc?.metrics?.[p.country]?.clicks ?? '\u2014'}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{gsc?.metrics?.[p.country]?.impressions ?? '\u2014'}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{gsc?.metrics?.[p.country]?.position?.toFixed(1) ?? '\u2014'}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{fmt(p.updated_at)}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-3">
                      <button onClick={() => openEditor(p.id)} className="text-[11px] font-bold text-primary hover:underline">Edit</button>
                      {p.status === 'published'
                        ? <button disabled={busy} onClick={() => act(() => api.post(`/admin/cseo/${p.id}/unpublish`, {}), 'Unpublished.')} className="text-[11px] font-bold text-muted-foreground hover:text-foreground disabled:opacity-40">Unpublish</button>
                        : <button disabled={busy} onClick={() => act(() => api.post(`/admin/cseo/${p.id}/publish`, {}), 'Published.')} className="text-[11px] font-bold text-primary hover:underline disabled:opacity-40">Publish</button>}
                      {p.index_status === 'index'
                        ? <button disabled={busy} title="Remove from the index" onClick={() => act(() => api.post(`/admin/cseo/${p.id}/index-status`, { index_status: 'noindex' }), 'Set to noindex.')} className="inline-flex items-center gap-1 text-[11px] font-bold text-amber-600 hover:underline disabled:opacity-40"><EyeOff className="h-3.5 w-3.5" />noindex</button>
                        : <button
                            disabled={busy}
                            title="Allow indexing. Only after the launch blockers are cleared."
                            onClick={() => { if (confirm(`Allow Google to index the ${p.country_label} pillar?\n\nGuardrail 16 wants the child URLs returning 200, approved proof, a delivered test lead and final schema validation before this.`)) act(() => api.post(`/admin/cseo/${p.id}/index-status`, { index_status: 'index' }), 'Now indexable.') }}
                            className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-600 hover:underline disabled:opacity-40"><Eye className="h-3.5 w-3.5" />index</button>}
                      <button disabled={busy} title="Flush the Redis and ISR cache for this page" onClick={() => act(() => api.post(`/admin/cseo/${p.id}/flush-cache`, {}), 'Cache flushed.')} className="text-muted-foreground hover:text-primary disabled:opacity-40" aria-label="Flush cache"><Zap className="h-3.5 w-3.5" /></button>
                      <button onClick={() => showQueries(p.id)} title="Top Search Console queries" className="text-muted-foreground hover:text-primary" aria-label="Show top queries"><ChevronDown className={`h-3.5 w-3.5 transition-transform ${openQ === p.id ? 'rotate-180' : ''}`} /></button>
                    <button
                      disabled={busy}
                      onClick={() => { if (confirm(`Delete the ${p.country_label} pillar? The market falls back to the auto-generated industry hub.`)) act(() => api.delete(`/admin/cseo/${p.id}`), 'Deleted.') }}
                      aria-label={`Delete the ${p.country_label} pillar`}
                      className="text-muted-foreground hover:text-red-500 disabled:opacity-40"><Trash2 className="h-3.5 w-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
              {rows.map((p) => openQ === p.id && (
                <tr key={`q-${p.id}`} className="border-b border-border/60 bg-muted/20">
                  <td colSpan={10} className="px-4 py-4">
                    <p className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-muted-foreground"><BarChart3 className="h-3.5 w-3.5" />Top queries, last {GSC_DAYS} days</p>
                    {gsc && !gsc.configured
                      ? <p className="text-xs text-muted-foreground">Search Console is not connected.</p>
                      : (queries[p.id] || []).length === 0
                        ? <p className="text-xs text-muted-foreground">No query data yet. A noindex page will not have any.</p>
                        : (
                          <table className="w-full text-xs">
                            <thead><tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground"><th className="py-1 font-bold">Query</th><th className="py-1 font-bold">Clicks</th><th className="py-1 font-bold">Impressions</th><th className="py-1 font-bold">Position</th></tr></thead>
                            <tbody>
                              {(queries[p.id] || []).map((q) => (
                                <tr key={q.query} className="border-t border-border/60">
                                  <td className="py-1.5 font-medium text-foreground">{q.query}</td>
                                  <td className="py-1.5">{q.clicks}</td>
                                  <td className="py-1.5 text-muted-foreground">{q.impressions}</td>
                                  <td className="py-1.5 text-muted-foreground">{q.position.toFixed(1)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                  </td>
                </tr>
              ))}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={10} className="px-4 py-10 text-center text-xs text-muted-foreground">No country pillars yet. Import the package CSV to add one.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">
        A pillar imports as a draft on <code>noindex</code>, matching the package&apos;s staging state. Publish it to serve the
        page, then switch robots to index only once the launch blockers in the guardrails file are cleared.
      </p>
    </div>
  )
}
