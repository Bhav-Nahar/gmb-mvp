'use client'

import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import {
  Plus, Upload, Download, Trash2, Loader2, Pencil, Globe, EyeOff, ExternalLink,
  Search, ArrowLeft, Save, AlertTriangle, CheckCircle2, FileSpreadsheet, RefreshCw,
  ChevronLeft, ChevronRight, Eye, Ban, ArrowUp, ArrowDown, ArrowUpDown,
} from 'lucide-react'

// ── Types ────────────────────────────────────────────────────────────────────

interface PageRow {
  id: number
  slug: string
  country: string
  locale: string
  industry_label: string
  city_label: string
  status: string
  index_status: string
  quality_score: number | null
  meta_title: string
  published_at: string | null
  updated_at: string | null
}

interface ImportResult {
  created: number
  updated: number
  failed: number
  results: { row: number; slug: string | null; action: string; status?: string; error?: string }[]
}

interface Stats {
  total: number
  published: number
  draft: number
  noindex: number
}

interface GscMetric {
  clicks: number
  impressions: number
  ctr: number
  position: number
}

interface GscQuery extends GscMetric {
  query: string
}

const PAGE_SIZE = 20
const GSC_DAYS = 28
const CHUNK_ROWS = 300
const BULK_BATCH = 100 // ids per bulk-status call — small enough that no single request freezes the UI or Vercel

// Splits a CSV's data rows into batches of `chunkSize`, header repeated on each —
// keeps every request well under any reverse-proxy timeout regardless of file size.
// ponytail: assumes no literal newlines inside quoted cells (matches this app's own
// export template, which uses `|`/`::` for multi-value cells instead). If a future
// CSV needs embedded newlines, this naive line-split breaks — swap in a real CSV
// parser then.
function splitCsvIntoChunks(text: string, chunkSize: number): string[] {
  const lines = text.split(/\r\n|\n|\r/)
  while (lines.length && lines[lines.length - 1].trim() === '') lines.pop()
  if (lines.length <= 1) return []
  const [header, ...dataLines] = lines
  const chunks: string[] = []
  for (let i = 0; i < dataLines.length; i += chunkSize) {
    chunks.push([header, ...dataLines.slice(i, i + chunkSize)].join('\n'))
  }
  return chunks
}

// Content field groups — mirror backend CONTENT_*_COLS. Lists edit as one-item-per-line
// textareas; pairs as "Title :: detail" per line.
const TEXT_FIELDS: [string, string][] = [
  ['badge', 'Hero badge'],
  ['hero_sub', 'Hero subheadline'],
  ['primary_cta', 'Primary CTA label'],
  ['secondary_cta', 'Secondary CTA label'],
  ['why_matters_body', 'Why GBP matters — intro paragraph'],
  ['reviews_body', 'Review management — body'],
  ['example_review', 'Example customer review'],
  ['example_reply', 'Example AI reply'],
  ['city_visibility_body', 'City visibility — body'],
  ['final_heading', 'Final CTA heading'],
  ['final_sub', 'Final CTA subtext'],
  ['primary_keyword', 'Primary keyword'],
  ['region', 'Region / state'],
  ['page_type', 'Page type'],
  ['template_version', 'Template version'],
  ['last_updated', 'Content last reviewed (date)'],
]
const LIST_FIELDS: [string, string][] = [
  ['why_matters_points', 'Why GBP matters — points'],
  ['problems', 'Common GBP problems (Title :: detail)'],
  ['solutions', 'How Pinzo solves (Title :: detail)'],
  ['gbp_categories', 'GBP categories to add'],
  ['gbp_services', 'GBP services to add'],
  ['gbp_attributes', 'GBP attributes/extras'],
  ['review_themes', 'Review themes'],
  ['post_ideas', 'Google Posts ideas'],
  ['photo_checklist', 'Photo/content checklist'],
  ['neighborhoods', 'City neighborhoods'],
  ['single_points', 'Single-location points'],
  ['multi_points', 'Multi-location points'],
  ['monthly_workflow', 'Monthly workflow (Step :: detail)'],
  ['faqs', 'FAQs (Question :: Answer)'],
  ['secondary_keywords', 'Secondary keywords'],
  ['related_pages', 'Related pages (Anchor :: url)'],
  ['internal_links', 'Internal links (Anchor :: url)'],
]
const PAIR_KEYS = new Set(['problems', 'solutions', 'monthly_workflow', 'faqs', 'related_pages', 'internal_links'])
const LINK_KEYS = new Set(['related_pages', 'internal_links'])

// ── Content JSON <-> textarea codecs ─────────────────────────────────────────

function contentToDraft(content: any): Record<string, string> {
  const d: Record<string, string> = {}
  for (const [k] of TEXT_FIELDS) d[k] = content?.[k] || ''
  for (const [k] of LIST_FIELDS) {
    const v = content?.[k]
    if (!Array.isArray(v)) { d[k] = ''; continue }
    d[k] = v.map((item: any) => {
      if (typeof item === 'string') return item
      if (k === 'faqs') return `${item.q || ''} :: ${item.a || ''}`
      if (LINK_KEYS.has(k)) return `${item.anchor || ''} :: ${item.url || ''}`
      return item.detail ? `${item.title || ''} :: ${item.detail}` : (item.title || '')
    }).join('\n')
  }
  return d
}

function draftToContent(d: Record<string, string>): any {
  const content: any = {}
  for (const [k] of TEXT_FIELDS) if (d[k]?.trim()) content[k] = d[k].trim()
  for (const [k] of LIST_FIELDS) {
    const lines = (d[k] || '').split('\n').map((s) => s.trim()).filter(Boolean)
    if (!lines.length) continue
    if (PAIR_KEYS.has(k)) {
      const pairs = lines.map((line) => {
        const [title, ...rest] = line.split('::')
        const detail = rest.join('::').trim()
        if (k === 'faqs') return { q: title.trim(), a: detail }
        if (LINK_KEYS.has(k)) return { anchor: title.trim(), url: detail }
        return { title: title.trim(), detail }
      })
      content[k] = pairs
    } else {
      content[k] = lines
    }
  }
  return content
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function AdminPseoPage() {
  const [pages, setPages] = useState<PageRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<Stats | null>(null)
  const [gscConfigured, setGscConfigured] = useState(true) // assume yes until we hear otherwise, avoids a flash of the "not connected" hint
  const [gscMetrics, setGscMetrics] = useState<Record<string, GscMetric>>({})
  const [gscDays, setGscDays] = useState(GSC_DAYS)
  const [sortBy, setSortBy] = useState<'clicks' | 'impressions' | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [selectAllMatching, setSelectAllMatching] = useState(false)
  const [bulkProgress, setBulkProgress] = useState<{ done: number; total: number } | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importProgress, setImportProgress] = useState<{ done: number; total: number } | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // Editor state: null = list view; {} draft object = editing/creating
  const [editing, setEditing] = useState<any | null>(null)
  const [gscQueries, setGscQueries] = useState<GscQuery[]>([])

  const flash = (msg: string) => { setNotice(msg); setTimeout(() => setNotice(''), 6000) }

  const loadStats = async () => {
    try { setStats(await api.get<Stats>('/admin/pseo/stats')) } catch { /* non-critical */ }
  }

  const loadGsc = async () => {
    try {
      const d = await api.get<{ configured: boolean; metrics: Record<string, GscMetric> }>('/admin/pseo/gsc-metrics', { days: String(gscDays) })
      setGscConfigured(d.configured)
      setGscMetrics(d.metrics || {})
    } catch { /* non-critical */ }
  }

  const load = async () => {
    setLoading(true); setError('')
    try {
      const params: Record<string, string> = { page: String(page), page_size: String(PAGE_SIZE) }
      if (q.trim()) params.q = q.trim()
      if (statusFilter) params.status = statusFilter
      if (sortBy) { params.sort_by = sortBy; params.sort_dir = sortDir; params.gsc_days = String(gscDays) }
      const d = await api.get<{ pages: PageRow[]; total: number }>('/admin/pseo', params)
      setPages(d.pages || [])
      setTotal(d.total || 0)
      setSelected(new Set())
      setSelectAllMatching(false)
    } catch (e: any) {
      setError(e.message || 'Failed to load pages')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(); loadStats() }, [page, statusFilter, sortBy, sortDir]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadGsc(); if (sortBy) load() }, [gscDays]) // eslint-disable-line react-hooks/exhaustive-deps

  const search = () => { setPage(1); load() }

  const toggleSort = (col: 'clicks' | 'impressions') => {
    setPage(1)
    if (sortBy === col) {
      setSortDir((d) => d === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(col)
      setSortDir('desc')
    }
  }

  const toggleSelected = (id: number) => {
    setSelectAllMatching(false)
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }
  const toggleSelectAll = () => {
    setSelectAllMatching(false)
    setSelected((prev) => prev.size === pages.length ? new Set() : new Set(pages.map((p) => p.id)))
  }

  const bulkUpdate = async (body: { status?: string; index_status?: string }, label: string) => {
    setBusy(true); setError('')
    try {
      // Resolve the full target id set (fetch matching ids when "select all N"),
      // then apply in small batches so no single request freezes the UI or Vercel.
      let ids: number[]
      if (selectAllMatching) {
        const params: Record<string, string> = {}
        if (q.trim()) params.q = q.trim()
        if (statusFilter) params.status = statusFilter
        ids = (await api.get<{ ids: number[] }>('/admin/pseo/ids', params)).ids || []
      } else {
        ids = Array.from(selected)
      }
      if (!ids.length) { flash('No pages selected.'); return }
      let done = 0
      setBulkProgress({ done: 0, total: ids.length })
      for (let i = 0; i < ids.length; i += BULK_BATCH) {
        const batch = ids.slice(i, i + BULK_BATCH)
        await api.post<{ updated: number }>('/admin/pseo/bulk-status', { ids: batch, ...body })
        done += batch.length
        setBulkProgress({ done, total: ids.length })
      }
      flash(`${ids.length} page(s) ${label}.`)
      await Promise.all([load(), loadStats()])
    } catch (e: any) {
      setError(e.message || 'Bulk update failed')
    } finally {
      setBusy(false)
      setBulkProgress(null)
    }
  }

  const openNew = () => {
    setGscQueries([])
    setEditing({
      id: null, country: 'us', industry_label: '', city_label: '', slug: '', meta_title: '', meta_description: '', h1: '',
      canonical_url: '', index_status: 'index', quality_score: '',
      status: 'draft', draft: Object.fromEntries([...TEXT_FIELDS, ...LIST_FIELDS].map(([k]) => [k, ''])),
    })
  }

  const openEdit = async (row: PageRow) => {
    setBusy(true)
    setGscQueries([])
    try {
      const p = await api.get<any>(`/admin/pseo/${row.id}`)
      setEditing({
        id: p.id, country: p.country || 'in', industry_label: p.industry_label, city_label: p.city_label, slug: p.slug,
        meta_title: p.meta_title, meta_description: p.meta_description || '', h1: p.h1 || '',
        canonical_url: p.canonical_url || '', index_status: p.index_status || 'index',
        quality_score: p.quality_score ?? '', status: p.status, draft: contentToDraft(p.content),
      })
      if (gscConfigured) {
        api.get<{ queries: GscQuery[] }>(`/admin/pseo/${row.id}/gsc-queries`, { days: String(gscDays) })
          .then((d) => setGscQueries(d.queries || []))
          .catch(() => {})
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load page')
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!editing.industry_label.trim() || !editing.city_label.trim()) {
      setError('Industry and city are required'); return
    }
    setBusy(true); setError('')
    const qs = String(editing.quality_score).trim()
    const body = {
      country: editing.country,
      industry_label: editing.industry_label.trim(),
      city_label: editing.city_label.trim(),
      slug: editing.slug.trim() || null,
      meta_title: editing.meta_title.trim() || null,
      meta_description: editing.meta_description.trim() || null,
      h1: editing.h1.trim() || null,
      canonical_url: editing.canonical_url.trim() || null,
      index_status: editing.index_status,
      quality_score: qs ? Number(qs) : null,
      status: editing.status,
      content: draftToContent(editing.draft),
    }
    try {
      if (editing.id) {
        await api.patch(`/admin/pseo/${editing.id}`, body)
        flash('Page saved.')
      } else {
        await api.post('/admin/pseo', body)
        flash('Page created.')
      }
      setEditing(null)
      await Promise.all([load(), loadStats()])
    } catch (e: any) {
      setError(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const setStatus = async (row: PageRow, publish: boolean) => {
    setBusy(true); setError('')
    try {
      await api.post(`/admin/pseo/${row.id}/${publish ? 'publish' : 'unpublish'}`, {})
      flash(publish ? `Published /${row.slug}` : `Unpublished /${row.slug}`)
      await Promise.all([load(), loadStats()])
    } catch (e: any) {
      setError(e.message || 'Status change failed')
    } finally {
      setBusy(false)
    }
  }

  const flushCache = async (row: PageRow) => {
    setBusy(true); setError('')
    try {
      await api.post(`/admin/pseo/${row.id}/flush-cache`, {})
      flash(`Cache flushed for /${row.slug} — changes are live now.`)
    } catch (e: any) {
      setError(e.message || 'Cache flush failed')
    } finally {
      setBusy(false)
    }
  }

  const remove = async (row: PageRow) => {
    if (!window.confirm(`Delete /${row.slug}? This cannot be undone.`)) return
    setBusy(true); setError('')
    try {
      await api.delete(`/admin/pseo/${row.id}`)
      flash('Page deleted.')
      await Promise.all([load(), loadStats()])
    } catch (e: any) {
      setError(e.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  const importFile = async (file: File) => {
    setBusy(true); setError(''); setImportResult(null); setImportProgress(null)
    // XLSX isn't chunked (no parser on the client) — uploads as one request. If that
    // starts timing out too, convert to CSV first; the template download is CSV.
    const isCsv = file.name.toLowerCase().endsWith('.csv')
    const chunks: (string | null)[] = isCsv ? splitCsvIntoChunks(await file.text(), CHUNK_ROWS) : [null]
    let created = 0, updated = 0, failed = 0
    let results: ImportResult['results'] = []
    try {
      for (let i = 0; i < chunks.length; i++) {
        if (chunks.length > 1) setImportProgress({ done: i, total: chunks.length })
        const fd = new FormData()
        const chunk = chunks[i]
        fd.append('file', chunk === null ? file : new Blob([chunk], { type: 'text/csv' }), chunk === null ? file.name : `chunk-${i + 1}.csv`)
        const r = await api.post<ImportResult>('/admin/pseo/import', fd)
        created += r.created; updated += r.updated; failed += r.failed
        results = results.concat(r.results)
        setImportResult({ created, updated, failed, results }) // visible progress as batches land
      }
      flash(`Import done: ${created} created, ${updated} updated, ${failed} failed${chunks.length > 1 ? ` (${chunks.length} batches)` : ''}.`)
    } catch (e: any) {
      const savedSoFar = created + updated
      setError((e.message || 'Import failed') + (savedSoFar ? ` — ${savedSoFar} row(s) from earlier batches are already saved.` : ''))
    } finally {
      setBusy(false)
      setImportProgress(null)
      if (fileRef.current) fileRef.current.value = ''
      await Promise.all([load(), loadStats()])
    }
  }

  const downloadTemplate = async () => {
    try {
      const meta = await api.get<{ columns: string[] }>('/admin/pseo/import/columns')
      const example: Record<string, string> = {
        country: 'us', industry_label: 'Doctors', city_label: 'New York, NY', status: 'draft',
        index_status: 'index', quality_score: '85',
        hero_sub: 'Keep every clinic profile complete, answer patient reviews with AI, and rank when patients search nearby.',
        primary_keyword: 'google business profile management for doctors in new york',
        secondary_keywords: 'GBP management for clinics NYC | Google Maps marketing for doctors',
        why_matters_points: 'Patients check reviews before booking | Maps drives walk-in appointments',
        problems: 'Missing services :: Google cannot match you to treatment searches | Unanswered reviews :: Patients read the silence',
        solutions: 'AI review replies :: Drafted in your tone, you approve | Profile audits :: Every missing field flagged',
        related_pages: 'Dentists in New York :: /en-us/gbp-management/dentists-in-new-york-ny',
        faqs: 'Is Pinzo compliant for clinics? :: Yes — replies never disclose patient information.',
      }
      const esc = (s: string) => `"${(s || '').replace(/"/g, '""')}"`
      const csv = [meta.columns.join(','), meta.columns.map((c) => esc(example[c] || '')).join(',')].join('\n')
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
      a.download = 'pinzo-pseo-template.csv'
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e: any) {
      setError(e.message || 'Template download failed')
    }
  }

  const inputCls = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none'
  const labelCls = 'mb-1 block text-[11px] font-bold uppercase tracking-wide text-muted-foreground'

  // ── Editor view ────────────────────────────────────────────────────────────
  if (editing) {
    return (
      <div className="mx-auto max-w-4xl space-y-6 p-6">
        <div className="flex items-center justify-between">
          <button onClick={() => setEditing(null)} className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-3.5 w-3.5" /> Back to list
          </button>
          <div className="flex items-center gap-3">
            <select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value })} className="rounded-lg border border-border bg-background px-3 py-2 text-xs font-bold">
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
            <button onClick={save} disabled={busy} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-bold uppercase tracking-wider text-primary-foreground disabled:opacity-50">
              {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />} Save
            </button>
          </div>
        </div>

        {error && <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs font-semibold text-red-500"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}

        {editing.id && gscConfigured && (
          <div className="space-y-3 rounded-2xl border border-border bg-card p-6">
            <h2 className="text-sm font-bold text-foreground">Search Console — top queries ({gscDays}d)</h2>
            {gscQueries.length === 0 ? (
              <p className="text-xs text-muted-foreground">No organic clicks/impressions yet for this page in the selected window.</p>
            ) : (
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-border text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    <th className="py-1.5 pr-3">Query</th>
                    <th className="py-1.5 pr-3">Clicks</th>
                    <th className="py-1.5 pr-3">Impressions</th>
                    <th className="py-1.5 pr-3">CTR</th>
                    <th className="py-1.5">Avg. position</th>
                  </tr>
                </thead>
                <tbody>
                  {gscQueries.map((q) => (
                    <tr key={q.query} className="border-b border-border/50 last:border-0">
                      <td className="py-1.5 pr-3 text-foreground">{q.query}</td>
                      <td className="py-1.5 pr-3">{q.clicks}</td>
                      <td className="py-1.5 pr-3">{q.impressions}</td>
                      <td className="py-1.5 pr-3">{(q.ctr * 100).toFixed(1)}%</td>
                      <td className="py-1.5">{q.position.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        <div className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-sm font-bold text-foreground">Identity & SEO meta</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className={labelCls}>Country (market)</label>
              <select className={inputCls} value={editing.country} onChange={(e) => setEditing({ ...editing, country: e.target.value })}>
                {[['us','United States'],['in','India'],['gb','United Kingdom'],['ca','Canada'],['au','Australia'],['ae','UAE'],['sg','Singapore'],['za','South Africa'],['ie','Ireland'],['nz','New Zealand']].map(([c,n]) => <option key={c} value={c}>{n} (en-{c})</option>)}
              </select>
            </div>
            <div><label className={labelCls}>Industry label *</label><input className={inputCls} value={editing.industry_label} onChange={(e) => setEditing({ ...editing, industry_label: e.target.value })} placeholder="Doctors & Clinics" /></div>
            <div><label className={labelCls}>City label *</label><input className={inputCls} value={editing.city_label} onChange={(e) => setEditing({ ...editing, city_label: e.target.value })} placeholder="New York, NY" /></div>
          </div>
          <div><label className={labelCls}>Slug (blank = auto: industry-in-city)</label><input className={inputCls} value={editing.slug} onChange={(e) => setEditing({ ...editing, slug: e.target.value })} placeholder="doctors-in-new-york-ny" /><p className="mt-1 text-[11px] text-muted-foreground">Served at <span className="font-mono">/en-{editing.country}/gbp-management/{editing.slug || 'doctors-in-new-york-ny'}</span></p></div>
          <div><label className={labelCls}>H1 (blank = auto)</label><input className={inputCls} value={editing.h1} onChange={(e) => setEditing({ ...editing, h1: e.target.value })} /></div>
          <div><label className={labelCls}>Meta title (blank = auto)</label><input className={inputCls} value={editing.meta_title} onChange={(e) => setEditing({ ...editing, meta_title: e.target.value })} /></div>
          <div><label className={labelCls}>Meta description (blank = auto)</label><textarea rows={2} className={inputCls} value={editing.meta_description} onChange={(e) => setEditing({ ...editing, meta_description: e.target.value })} /></div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className={labelCls}>Index status</label>
              <select className={inputCls} value={editing.index_status} onChange={(e) => setEditing({ ...editing, index_status: e.target.value })}>
                <option value="index">index (in sitemap)</option>
                <option value="noindex">noindex (hidden from search)</option>
              </select>
            </div>
            <div><label className={labelCls}>Quality score (0–100)</label><input type="number" min={0} max={100} className={inputCls} value={editing.quality_score} onChange={(e) => setEditing({ ...editing, quality_score: e.target.value })} placeholder="optional" /></div>
            <div><label className={labelCls}>Canonical URL override</label><input className={inputCls} value={editing.canonical_url} onChange={(e) => setEditing({ ...editing, canonical_url: e.target.value })} placeholder="blank = self" /></div>
          </div>
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-sm font-bold text-foreground">Copy blocks</h2>
          {TEXT_FIELDS.map(([k, label]) => (
            <div key={k}>
              <label className={labelCls}>{label}</label>
              <textarea rows={k.endsWith('_body') || k === 'hero_sub' ? 3 : 1} className={inputCls} value={editing.draft[k]} onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, [k]: e.target.value } })} />
            </div>
          ))}
        </div>

        <div className="space-y-4 rounded-2xl border border-border bg-card p-6">
          <h2 className="text-sm font-bold text-foreground">Lists <span className="font-normal text-muted-foreground">— one item per line; pairs use <code>Title :: detail</code></span></h2>
          {LIST_FIELDS.map(([k, label]) => (
            <div key={k}>
              <label className={labelCls}>{label}</label>
              <textarea rows={4} className={`${inputCls} font-mono text-xs`} value={editing.draft[k]} onChange={(e) => setEditing({ ...editing, draft: { ...editing.draft, [k]: e.target.value } })} />
            </div>
          ))}
        </div>
      </div>
    )
  }

  // ── List view ──────────────────────────────────────────────────────────────
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-extrabold text-foreground">pSEO landing pages</h1>
          <p className="text-xs text-muted-foreground">Country × industry × city pages served at pinzo.io/en-&#123;country&#125;/gbp-management/&#123;industry&#125;-in-&#123;city&#125;. Import in bulk from CSV/XLSX or create one by one.</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={downloadTemplate} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground">
            <Download className="h-3.5 w-3.5" /> CSV template
          </button>
          <button onClick={() => fileRef.current?.click()} disabled={busy} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground disabled:opacity-50">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {importProgress ? `Importing batch ${importProgress.done + 1} of ${importProgress.total}…` : 'Import CSV/XLSX'}
          </button>
          <input ref={fileRef} type="file" accept=".csv,.xlsx" className="hidden" onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])} />
          <button onClick={openNew} className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-xs font-bold uppercase tracking-wider text-primary-foreground">
            <Plus className="h-3.5 w-3.5" /> New page
          </button>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: 'Total pages', value: stats.total },
            { label: 'Published', value: stats.published },
            { label: 'Draft', value: stats.draft },
            { label: 'Noindex', value: stats.noindex },
          ].map((c) => (
            <div key={c.label} className="rounded-xl border border-border bg-card px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{c.label}</div>
              <div className="mt-1 text-xl font-bold text-foreground">{c.value}</div>
            </div>
          ))}
        </div>
      )}

      {notice && <div className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-3 text-xs font-semibold text-emerald-600"><CheckCircle2 className="h-4 w-4 shrink-0" />{notice}</div>}
      {error && <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs font-semibold text-red-500"><AlertTriangle className="h-4 w-4 shrink-0" />{error}</div>}
      {!gscConfigured && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs font-semibold text-amber-600">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          Search Console isn&apos;t connected yet — set GSC_SERVICE_ACCOUNT_JSON and GSC_PROPERTY_URL to see organic clicks/impressions here.
        </div>
      )}

      {importResult && importResult.results.some((r) => r.action === 'error') && (
        <div className="space-y-2 rounded-xl border border-amber-500/30 bg-amber-500/5 p-4">
          <p className="flex items-center gap-2 text-xs font-bold text-amber-600"><FileSpreadsheet className="h-4 w-4" />Rows with errors</p>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {importResult.results.filter((r) => r.action === 'error').map((r) => (
              <li key={r.row}>Row {r.row}{r.slug ? ` (${r.slug})` : ''}: {r.error}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            className="w-full rounded-lg border border-border bg-background py-2 pl-9 pr-3 text-sm"
            placeholder="Search slug, industry, city…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search()}
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
        </select>
        <select
          value={gscDays}
          onChange={(e) => setGscDays(Number(e.target.value))}
          title="Search Console date range"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm"
        >
          <option value={7}>Last 7 days</option>
          <option value={28}>Last 28 days</option>
          <option value={90}>Last 90 days</option>
          <option value={180}>Last 180 days</option>
        </select>
        <button onClick={search} className="rounded-lg border border-border px-3 py-2 text-xs font-bold text-muted-foreground hover:text-foreground">Search</button>
        {selected.size > 0 && (
          <div className="ml-auto flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 px-3 py-1.5">
            <span className="text-xs font-bold text-foreground">{selectAllMatching ? `All ${total} matching selected` : `${selected.size} selected`}</span>
            {!selectAllMatching && selected.size === pages.length && pages.length < total && (
              <button onClick={() => setSelectAllMatching(true)} className="text-[11px] font-bold text-primary underline underline-offset-2">Select all {total} matching</button>
            )}
            {bulkProgress && (<span className="flex items-center gap-1.5 text-[11px] font-bold text-primary"><Loader2 className="h-3 w-3 animate-spin" />Updating {bulkProgress.done}/{bulkProgress.total}…</span>)}
            <button onClick={() => bulkUpdate({ status: 'published' }, 'published')} disabled={busy} className="flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-bold text-white disabled:opacity-50"><Globe className="h-3 w-3" /> Publish</button>
            <button onClick={() => bulkUpdate({ status: 'draft' }, 'unpublished')} disabled={busy} className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[11px] font-bold text-muted-foreground hover:text-foreground disabled:opacity-50"><EyeOff className="h-3 w-3" /> Unpublish</button>
            <span className="mx-1 h-4 w-px bg-border" />
            <button onClick={() => bulkUpdate({ index_status: 'index' }, 'set to index')} disabled={busy} className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[11px] font-bold text-muted-foreground hover:text-foreground disabled:opacity-50"><Eye className="h-3 w-3" /> Index</button>
            <button onClick={() => bulkUpdate({ index_status: 'noindex' }, 'set to noindex')} disabled={busy} className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[11px] font-bold text-muted-foreground hover:text-foreground disabled:opacity-50"><Ban className="h-3 w-3" /> Noindex</button>
            <button onClick={() => { setSelected(new Set()); setSelectAllMatching(false) }} className="text-[11px] font-bold text-muted-foreground hover:text-foreground">Clear</button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto rounded-2xl border border-border bg-card">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-border text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              <th className="w-10 px-4 py-3">
                <input type="checkbox" checked={pages.length > 0 && (selectAllMatching || selected.size === pages.length)} onChange={toggleSelectAll} />
              </th>
              <th className="px-4 py-3">Page</th>
              <th className="px-4 py-3">Market</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">
                <button onClick={() => toggleSort('clicks')} className="inline-flex items-center gap-1 hover:text-foreground">
                  Clicks ({gscDays}d)
                  {sortBy === 'clicks' ? (sortDir === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                </button>
              </th>
              <th className="px-4 py-3 text-right">
                <button onClick={() => toggleSort('impressions')} className="inline-flex items-center gap-1 hover:text-foreground">
                  Impressions ({gscDays}d)
                  {sortBy === 'impressions' ? (sortDir === 'desc' ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                </button>
              </th>
              <th className="px-4 py-3">Updated</th>
              <th className="px-4 py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-xs text-muted-foreground">Loading…</td></tr>
            ) : pages.length === 0 ? (
              <tr><td colSpan={8} className="px-4 py-10 text-center text-xs text-muted-foreground">No pages yet. Import a CSV or create one.</td></tr>
            ) : pages.map((p) => (
              <tr key={p.id} className="border-b border-border/50 last:border-0">
                <td className="px-4 py-3">
                  <input type="checkbox" checked={selectAllMatching || selected.has(p.id)} onChange={() => toggleSelected(p.id)} />
                </td>
                <td className="px-4 py-3">
                  <p className="font-semibold text-foreground">{p.industry_label} · {p.city_label}</p>
                  <p className="font-mono text-[11px] text-muted-foreground">/{p.locale}/gbp-management/{p.slug}</p>
                </td>
                <td className="px-4 py-3">
                  <span className="rounded border border-border px-2 py-0.5 text-[10px] font-bold uppercase text-muted-foreground">{p.locale}</span>
                  {p.index_status === 'noindex' && <span className="ml-1 rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-600">noindex</span>}
                </td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${p.status === 'published' ? 'bg-emerald-500/10 text-emerald-600' : 'bg-muted text-muted-foreground'}`}>{p.status}</span>
                </td>
                <td className="px-4 py-3 text-right text-xs text-foreground">{gscMetrics[p.slug]?.clicks ?? <span className="text-muted-foreground">—</span>}</td>
                <td className="px-4 py-3 text-right text-xs text-foreground">{gscMetrics[p.slug]?.impressions ?? <span className="text-muted-foreground">—</span>}</td>
                <td className="px-4 py-3 text-xs text-muted-foreground">{p.updated_at ? new Date(p.updated_at).toLocaleDateString() : '—'}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-1.5">
                    {p.status === 'published' && (
                      <a href={`/${p.locale}/gbp-management/${p.slug}`} target="_blank" rel="noopener noreferrer" title="View live" className="rounded-lg border border-border p-2 text-muted-foreground hover:text-foreground"><ExternalLink className="h-3.5 w-3.5" /></a>
                    )}
                    {p.status === 'published' && (
                      <button onClick={() => flushCache(p)} disabled={busy} title="Flush cache (this page only)" className="rounded-lg border border-border p-2 text-muted-foreground hover:text-foreground disabled:opacity-50"><RefreshCw className="h-3.5 w-3.5" /></button>
                    )}
                    <button onClick={() => openEdit(p)} disabled={busy} title="Edit" className="rounded-lg border border-border p-2 text-muted-foreground hover:text-foreground disabled:opacity-50"><Pencil className="h-3.5 w-3.5" /></button>
                    {p.status === 'published' ? (
                      <button onClick={() => setStatus(p, false)} disabled={busy} title="Unpublish" className="rounded-lg border border-border p-2 text-muted-foreground hover:text-foreground disabled:opacity-50"><EyeOff className="h-3.5 w-3.5" /></button>
                    ) : (
                      <button onClick={() => setStatus(p, true)} disabled={busy} title="Publish" className="rounded-lg border border-border p-2 text-emerald-600 hover:bg-emerald-500/10 disabled:opacity-50"><Globe className="h-3.5 w-3.5" /></button>
                    )}
                    <button onClick={() => remove(p)} disabled={busy} title="Delete" className="rounded-lg border border-border p-2 text-rose-500 hover:bg-rose-500/10 disabled:opacity-50"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{total === 0 ? '0 pages' : `${(page - 1) * PAGE_SIZE + 1}–${Math.min(page * PAGE_SIZE, total)} of ${total}`}</span>
        <div className="flex items-center gap-2">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1 || loading} className="flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 font-bold hover:text-foreground disabled:opacity-40"><ChevronLeft className="h-3.5 w-3.5" /> Prev</button>
          <span className="font-bold text-foreground">Page {page} / {Math.max(1, Math.ceil(total / PAGE_SIZE))}</span>
          <button onClick={() => setPage((p) => p + 1)} disabled={page * PAGE_SIZE >= total || loading} className="flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 font-bold hover:text-foreground disabled:opacity-40">Next <ChevronRight className="h-3.5 w-3.5" /></button>
        </div>
      </div>
    </div>
  )
}
