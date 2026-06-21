'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Search, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react'

interface AuditRow {
  id: number
  action: string
  details: string | null
  organization_id: number | null
  org_name: string | null
  actor_user_id: number | null
  actor_email: string | null
  target_user_id: number | null
  created_at: string
}

const PAGE = 50

function fmt(iso: string): string {
  return new Date(iso).toLocaleString()
}

export default function AdminAuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState('')
  const [orgId, setOrgId] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async (newOffset = offset) => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string> = { limit: String(PAGE), offset: String(newOffset) }
      if (action.trim()) params.action = action.trim()
      if (orgId.trim()) params.organization_id = orgId.trim()
      const data = await api.get<{ total: number; items: AuditRow[] }>('/admin/audit', params)
      setRows(data.items)
      setTotal(data.total)
      setOffset(newOffset)
    } catch (e: any) {
      setError(e.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load(0) }, [])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold">Audit log</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Every super-admin and team action, across all organizations.</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={(e) => { e.preventDefault(); load(0) }} className="flex flex-1 items-center gap-3 min-w-[260px]">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input value={action} onChange={(e) => setAction(e.target.value)} placeholder="Filter by action… (e.g. superadmin)" className="w-full rounded-lg border border-border bg-card pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <input value={orgId} onChange={(e) => setOrgId(e.target.value)} placeholder="Org ID" className="w-28 rounded-lg border border-border bg-card px-3 py-2 text-sm" />
          <button type="submit" className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:opacity-90">Filter</button>
        </form>
        <button onClick={() => load(0)} className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-semibold hover:bg-muted/40">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-600">{error}</div>}

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-3 font-bold">When</th>
                <th className="px-4 py-3 font-bold">Action</th>
                <th className="px-4 py-3 font-bold">Org</th>
                <th className="px-4 py-3 font-bold">Actor</th>
                <th className="px-4 py-3 font-bold">Details</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-border/60 align-top">
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{fmt(r.created_at)}</td>
                  <td className="px-4 py-3 font-semibold whitespace-nowrap">{r.action}</td>
                  <td className="px-4 py-3 whitespace-nowrap">{r.org_name || (r.organization_id != null ? `#${r.organization_id}` : '—')}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">{r.actor_email || (r.actor_user_id != null ? `#${r.actor_user_id}` : '—')}</td>
                  <td className="px-4 py-3 text-[11px] text-muted-foreground break-words max-w-md">{r.details || '—'}</td>
                </tr>
              ))}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-sm text-muted-foreground">No audit entries.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{total} total · showing {rows.length ? offset + 1 : 0}–{offset + rows.length}</span>
        <div className="flex items-center gap-2">
          <button disabled={offset === 0 || loading} onClick={() => load(Math.max(0, offset - PAGE))} className="flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 font-semibold disabled:opacity-40 hover:bg-muted/40">
            <ChevronLeft className="h-3.5 w-3.5" /> Prev
          </button>
          <button disabled={offset + PAGE >= total || loading} onClick={() => load(offset + PAGE)} className="flex items-center gap-1 rounded-lg border border-border bg-card px-3 py-1.5 font-semibold disabled:opacity-40 hover:bg-muted/40">
            Next <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  )
}
