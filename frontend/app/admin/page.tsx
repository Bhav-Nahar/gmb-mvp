'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, actAsOrg } from '@/lib/api'
import { Search, RefreshCw, ChevronRight, LogIn } from 'lucide-react'

function enterWorkspace(org: { id: number; name: string }) {
  actAsOrg(org.id)
  // Full nav (not router.push) so every cached query refetches with the new header.
  window.location.href = '/dashboard'
}

interface OrgRow {
  id: number
  name: string
  plan_tier: string
  subscription_status: string | null
  location_quota: number | null
  location_count: number
  user_count: number
  monthly_ai_credits_balance: number | null
  topup_ai_credits_balance: number | null
  trial_ends_at: string | null
  created_at: string
}

interface Metrics {
  total_organizations: number
  total_users: number
  total_locations: number
  by_status: Record<string, number>
  active_organizations: number
  trial_organizations: number
  past_due_organizations: number
  locked_organizations: number
  needs_remandate: number
  failed_syncs_7d: number
  credits_in_circulation: number
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20',
  trial: 'bg-blue-500/10 text-blue-600 border-blue-500/20',
  past_due: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
  locked: 'bg-red-500/10 text-red-600 border-red-500/20',
}

function StatusBadge({ status }: { status: string | null }) {
  const s = status || 'unknown'
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${STATUS_STYLES[s] || 'bg-muted/40 text-muted-foreground border-border'}`}>
      {s}
    </span>
  )
}

export default function AdminOrgsPage() {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  const [orgs, setOrgs] = useState<OrgRow[]>([])
  const [total, setTotal] = useState(0)
  const [q, setQ] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const params: Record<string, string> = {}
      if (q.trim()) params.q = q.trim()
      if (statusFilter) params.subscription_status = statusFilter
      const [m, list] = await Promise.all([
        api.get<Metrics>('/admin/metrics'),
        api.get<{ total: number; items: OrgRow[] }>('/admin/organizations', params),
      ])
      setMetrics(m)
      setOrgs(list.items)
      setTotal(list.total)
    } catch (e: any) {
      setError(e.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  // Reload on status change; search submits via the form.
  useEffect(() => { load() }, [statusFilter])

  const cards = metrics
    ? [
        { label: 'Organizations', value: metrics.total_organizations, alert: false },
        { label: 'Active', value: metrics.active_organizations, alert: false },
        { label: 'Trial', value: metrics.trial_organizations, alert: false },
        { label: 'Past due', value: metrics.past_due_organizations, alert: true },
        { label: 'Locked', value: metrics.locked_organizations, alert: true },
        { label: 'Re-mandate due', value: metrics.needs_remandate, alert: true },
        { label: 'Failed syncs (7d)', value: metrics.failed_syncs_7d, alert: true },
        { label: 'Users', value: metrics.total_users, alert: false },
        { label: 'Locations', value: metrics.total_locations, alert: false },
        { label: 'Credits in circ.', value: metrics.credits_in_circulation, alert: false },
      ]
    : []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold">Accounts</h1>
        <p className="text-xs text-muted-foreground mt-0.5">Overview and controls for every organization.</p>
      </div>

      {metrics && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {cards.map((c) => (
            <div key={c.label} className="rounded-xl border border-border bg-card px-4 py-3">
              <div className="text-[10px] uppercase font-bold tracking-wider text-muted-foreground">{c.label}</div>
              <div className={`text-xl font-bold mt-1 ${c.alert && c.value > 0 ? 'text-red-600' : ''}`}>{c.value}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={(e) => { e.preventDefault(); load() }} className="flex items-center gap-2 flex-1 min-w-[220px]">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name…"
              className="w-full rounded-lg border border-border bg-card pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
        </form>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded-lg border border-border bg-card px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="trial">Trial</option>
          <option value="active">Active</option>
          <option value="past_due">Past due</option>
          <option value="locked">Locked</option>
        </select>
        <button onClick={load} className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-semibold hover:bg-muted/40">
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-3 text-sm text-red-600">{error}</div>}

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-4 py-3 font-bold">Organization</th>
                <th className="px-4 py-3 font-bold">Status</th>
                <th className="px-4 py-3 font-bold">Plan</th>
                <th className="px-4 py-3 font-bold">Locations</th>
                <th className="px-4 py-3 font-bold">Users</th>
                <th className="px-4 py-3 font-bold">Credits</th>
                <th className="px-4 py-3 font-bold"></th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((o) => (
                <tr key={o.id} className="border-b border-border/60 hover:bg-muted/20">
                  <td className="px-4 py-3">
                    <Link href={`/admin/${o.id}`} className="font-semibold hover:text-primary">{o.name}</Link>
                    <div className="text-[11px] text-muted-foreground">#{o.id}</div>
                  </td>
                  <td className="px-4 py-3"><StatusBadge status={o.subscription_status} /></td>
                  <td className="px-4 py-3 capitalize">{o.plan_tier}</td>
                  <td className="px-4 py-3">{o.location_count}{o.location_quota != null ? ` / ${o.location_quota}` : ''}</td>
                  <td className="px-4 py-3">{o.user_count}</td>
                  <td className="px-4 py-3">{(o.monthly_ai_credits_balance ?? 0) + (o.topup_ai_credits_balance ?? 0)}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <button
                        onClick={() => enterWorkspace(o)}
                        title={`Enter ${o.name}'s workspace`}
                        className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-[11px] font-semibold hover:bg-muted/40"
                      >
                        <LogIn className="h-3.5 w-3.5" /> Enter
                      </button>
                      <Link href={`/admin/${o.id}`} className="inline-flex items-center text-muted-foreground hover:text-primary"><ChevronRight className="h-4 w-4" /></Link>
                    </div>
                  </td>
                </tr>
              ))}
              {!loading && orgs.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-sm text-muted-foreground">No organizations found.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="text-[11px] text-muted-foreground">{total} total</div>
    </div>
  )
}
