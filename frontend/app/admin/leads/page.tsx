'use client'

import { Fragment, useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Search, RefreshCw, ChevronLeft, ChevronRight, Trash2, AlertTriangle } from 'lucide-react'

// Enquiries from the public Local SEO landing-page audit forms. Read-only on
// purpose: this is lead collection, not a CRM. The only write is delete, for spam
// that beat the honeypot and for erasure requests.
interface Lead {
  id: number
  name: string
  clinic: string | null
  phone: string | null
  email: string | null
  website: string | null
  locations: string | null
  goal: string | null
  message: string | null
  page: string | null
  utm_source: string | null
  utm_medium: string | null
  utm_campaign: string | null
  gclid: string | null
  landing_page: string | null
  emailed: boolean
  created_at: string | null
}

const PAGE = 50
const fmt = (iso: string | null) => (iso ? new Date(iso).toLocaleString() : '—')
const dash = (s: string | null) => s || '—'

// Forms that have no column of their own for a field pack it into `message` as
// "Label: value" lines (the GBP audit form sends job title and city that way).
// Those get their own cells here; anything else stays one free-text block.
const detailFields = (r: Lead): [string, React.ReactNode][] => {
  const extra: [string, React.ReactNode][] = []
  const rest: string[] = []
  for (const line of (r.message || '').split('\n')) {
    const m = line.match(/^\s*([\w /]{2,24}):\s*(.+?)\s*$/)
    if (m) extra.push([m[1], m[2]])
    else if (line.trim()) rest.push(line)
  }
  return [
    ['Email', r.email ? <a href={`mailto:${r.email}`} className="text-primary hover:underline">{r.email}</a> : '—'],
    ['Website', r.website ? <a href={r.website} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{r.website}</a> : '—'],
    ['Locations / stores', dash(r.locations)],
    ...extra,
    ['UTM source', dash(r.utm_source)], ['UTM medium', dash(r.utm_medium)],
    ['UTM campaign', dash(r.utm_campaign)], ['GCLID', dash(r.gclid)],
    ['Landing page', dash(r.landing_page)],
    ...(rest.length ? ([['Message', rest.join('\n')]] as [string, React.ReactNode][]) : []),
  ]
}

export default function AdminLeadsPage() {
  const [rows, setRows] = useState<Lead[]>([])
  const [total, setTotal] = useState(0)
  const [notEmailed, setNotEmailed] = useState(0)
  const [page, setPage] = useState(1)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async (p = page) => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string> = { page: String(p), page_size: String(PAGE) }
      if (q.trim()) params.q = q.trim()
      const data = await api.get<{ leads: Lead[]; total: number; not_emailed: number }>('/admin/lpseo/leads', params)
      setRows(data.leads)
      setTotal(data.total)
      setNotEmailed(data.not_emailed)
      setPage(p)
    } catch (e: any) {
      setError(e.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(1) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const remove = async (id: number) => {
    if (!confirm('Delete this lead? This cannot be undone.')) return
    try {
      await api.delete(`/admin/lpseo/leads/${id}`)
      load(page)
    } catch (e: any) {
      setError(e.message || 'Failed to delete')
    }
  }

  const exportCsv = () => {
    const cols: (keyof Lead)[] = ['created_at', 'name', 'clinic', 'phone', 'email', 'website',
      'locations', 'goal', 'page', 'utm_source', 'utm_medium', 'utm_campaign', 'gclid', 'emailed']
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`
    const csv = [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    a.download = `pinzo-local-seo-leads-page-${page}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold">Leads</h1>
        <p className="mt-0.5 text-xs text-muted-foreground">Enquiries from the public Local SEO landing-page audit forms.</p>
      </div>

      {notEmailed > 0 && (
        <div className="flex items-start gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            <strong>{notEmailed}</strong> lead{notEmailed === 1 ? '' : 's'} saved but never emailed to the super-admins.
            Check <code className="font-mono">RESEND_API_KEY</code> and <code className="font-mono">SUPERADMIN_EMAILS</code>.
            The leads are safe here either way.
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={(e) => { e.preventDefault(); load(1) }} className="flex min-w-[260px] flex-1 items-center gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name, business, phone, email or page…" className="w-full rounded-lg border border-border bg-card py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:opacity-90">Search</button>
        </form>
        <button onClick={exportCsv} disabled={rows.length === 0} className="rounded-lg border border-border bg-card px-3 py-2 text-sm font-semibold disabled:opacity-40 hover:bg-muted/40">Export page as CSV</button>
        <button onClick={() => load(page)} className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-semibold hover:bg-muted/40">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-600">{error}</div>}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-3 font-bold">When</th>
                <th className="px-4 py-3 font-bold">Name</th>
                <th className="px-4 py-3 font-bold">Business</th>
                <th className="px-4 py-3 font-bold">Phone</th>
                <th className="px-4 py-3 font-bold">Goal</th>
                <th className="px-4 py-3 font-bold">Page</th>
                <th className="px-4 py-3 font-bold">Emailed</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.id}>
                <tr className={`border-b border-border/60 align-top ${open === r.id ? 'bg-muted/30' : ''}`}>
                  <td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{fmt(r.created_at)}</td>
                  <td className="whitespace-nowrap px-4 py-3 font-semibold">{r.name}</td>
                  <td className="whitespace-nowrap px-4 py-3">{dash(r.clinic)}</td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {r.phone ? <a href={`tel:${r.phone}`} className="font-semibold text-primary hover:underline">{r.phone}</a> : '—'}
                  </td>
                  <td className="px-4 py-3 text-[11px] text-muted-foreground">{dash(r.goal)}</td>
                  <td className="px-4 py-3 text-[11px] text-muted-foreground">
                    {r.page ? <a href={r.page} target="_blank" rel="noopener noreferrer" className="hover:underline">{r.page}</a> : '—'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    {r.emailed
                      ? <span className="text-[11px] font-semibold text-emerald-600">Sent</span>
                      : <span className="text-[11px] font-semibold text-amber-600">Not sent</span>}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right">
                    <button onClick={() => setOpen(open === r.id ? null : r.id)} className="text-[11px] font-bold text-primary hover:underline">
                      {open === r.id ? 'Hide' : 'Details'}
                    </button>
                    <button onClick={() => remove(r.id)} aria-label="Delete lead" className="ml-3 text-muted-foreground hover:text-red-500">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
                {open === r.id && (
                  <tr className="border-b border-border/60 bg-muted/20">
                    <td colSpan={8} className="px-4 py-4">
                      <dl className="grid grid-cols-1 gap-x-8 gap-y-3 text-[11px] sm:grid-cols-3 lg:grid-cols-4">
                        {detailFields(r).map(([k, v]) => (
                          <div key={k} className="min-w-0">
                            <dt className="font-bold uppercase tracking-wide text-muted-foreground">{k}</dt>
                            <dd className="mt-0.5 whitespace-pre-line break-words">{v}</dd>
                          </div>
                        ))}
                      </dl>
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-10 text-center text-sm text-muted-foreground">No leads yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{total} total · showing {rows.length ? (page - 1) * PAGE + 1 : 0}–{(page - 1) * PAGE + rows.length}</span>
        <div className="flex items-center gap-2">
          <button disabled={page === 1 || loading} onClick={() => load(page - 1)} className="flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 font-semibold hover:bg-muted/40 disabled:opacity-40">
            <ChevronLeft className="h-3.5 w-3.5" /> Prev
          </button>
          <button disabled={page * PAGE >= total || loading} onClick={() => load(page + 1)} className="flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 font-semibold hover:bg-muted/40 disabled:opacity-40">
            Next <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
