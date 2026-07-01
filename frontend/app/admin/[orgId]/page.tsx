'use client'

import { useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { api } from '@/lib/api'
import { ArrowLeft, RefreshCw } from 'lucide-react'

interface OrgDetail {
  id: number
  name: string
  plan: string | null
  plan_tier: string
  subscription_status: string | null
  location_quota: number | null
  location_count: number
  user_count: number
  monthly_ai_credits_balance: number | null
  topup_ai_credits_balance: number | null
  trial_ends_at: string | null
  grace_period_ends_at: string | null
  subscription_ends_at: string | null
  billing_cycle: string | null
  ai_credits_reset_date: string | null
  razorpay_customer_id: string | null
  razorpay_subscription_id: string | null
  subscription_needs_remandate: boolean
  paid_location_quota: number | null
  remandate_due_at: string | null
  created_at: string
  deleted_at: string | null
  custom_price_paise: number | null
  custom_credits_per_location: number | null
}
interface OrgUser { id: number; email: string; name: string; role: string; is_active: boolean; viewer_scope: string | null; created_at: string; deleted_at: string | null }
interface OrgLocation { id: number; location_name: string; billing_status: string | null; sync_status: string | null; average_rating: number | null; total_reviews: number | null; last_synced_at: string | null }
interface OrgTx { id: number; type: string | null; amount_paise: number | null; credits: number | null; status: string | null; source: string | null; invoice_url: string | null; created_at: string }
interface OrgAudit { id: number; action: string; details: string | null; actor_user_id: number | null; target_user_id: number | null; created_at: string }
interface OrgSyncState { sync_in_progress: boolean; sync_started_at: string | null; last_sync_status: string | null; last_sync_error: string | null; last_review_sync_at: string | null }
interface DetailResponse { organization: OrgDetail; users: OrgUser[]; locations: OrgLocation[]; transactions: OrgTx[]; audit: OrgAudit[]; sync_state: OrgSyncState }

const ROLES = ['Owner', 'Admin', 'Regional Manager', 'Store Manager', 'Viewer']
const inputCls = 'w-full rounded-lg border border-border bg-card px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30'

function toLocalInput(iso: string | null): string {
  // "2026-06-21T10:30:00+00:00" -> "2026-06-21T10:30" for datetime-local inputs.
  return iso ? iso.slice(0, 16) : ''
}
function paise(p: number | null): string {
  if (p == null) return '—'
  return `₹${(p / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
}
function fmt(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString() : '—'
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-[10px] uppercase font-bold tracking-wider text-muted-foreground mb-1.5">{label}</span>
      {children}
    </label>
  )
}
function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase font-bold tracking-wider">{label}</div>
      <div className="text-foreground break-words">{value}</div>
    </div>
  )
}

export default function AdminOrgDetailPage() {
  const params = useParams()
  const orgId = params?.orgId as string
  const [data, setData] = useState<DetailResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [form, setForm] = useState<any>(null)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)

  const flash = (m: string) => { setMsg(m); setTimeout(() => setMsg(''), 3500) }

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const d = await api.get<DetailResponse>(`/admin/organizations/${orgId}`)
      setData(d)
      const o = d.organization
      setForm({
        subscription_status: o.subscription_status || '',
        plan_tier: o.plan_tier || 'basic',
        location_quota: o.location_quota ?? '',
        monthly_ai_credits_balance: o.monthly_ai_credits_balance ?? '',
        topup_ai_credits_balance: o.topup_ai_credits_balance ?? '',
        trial_ends_at: toLocalInput(o.trial_ends_at),
        grace_period_ends_at: toLocalInput(o.grace_period_ends_at),
        custom_price_rupees: o.custom_price_paise != null ? o.custom_price_paise / 100 : '',
        custom_credits_per_location: o.custom_credits_per_location ?? '',
      })
    } catch (e: any) {
      setError(e.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { if (orgId) load() }, [orgId])

  const saveBilling = async () => {
    if (!form) return
    setSaving(true)
    setError('')
    try {
      const body: any = {
        reason: reason || null,
        subscription_status: form.subscription_status || null,
        plan_tier: form.plan_tier || null,
        location_quota: form.location_quota === '' ? null : Number(form.location_quota),
        monthly_ai_credits_balance: form.monthly_ai_credits_balance === '' ? null : Number(form.monthly_ai_credits_balance),
        topup_ai_credits_balance: form.topup_ai_credits_balance === '' ? null : Number(form.topup_ai_credits_balance),
        trial_ends_at: form.trial_ends_at || null,
        grace_period_ends_at: form.grace_period_ends_at || null,
        custom_price_paise: form.custom_price_rupees === '' ? null : Math.round(Number(form.custom_price_rupees) * 100),
        custom_credits_per_location: form.custom_credits_per_location === '' ? null : Number(form.custom_credits_per_location),
      }
      await api.patch(`/admin/organizations/${orgId}`, body)
      setReason('')
      flash('Saved.')
      load()
    } catch (e: any) {
      setError(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const clearCustomPricing = async () => {
    if (!confirm('Remove custom pricing and revert this org to standard tier pricing?')) return
    setSaving(true); setError('')
    try {
      await api.patch(`/admin/organizations/${orgId}`, { clear_custom_pricing: true, reason: reason || 'remove custom pricing' })
      setReason(''); flash('Custom pricing removed.'); load()
    } catch (e: any) {
      setError(e.message || 'Failed to remove custom pricing')
    } finally { setSaving(false) }
  }

  const patchUser = async (userId: number, payload: any, confirmMsg?: string) => {
    if (confirmMsg && !confirm(confirmMsg)) return
    setError('')
    try {
      await api.patch(`/admin/users/${userId}`, payload)
      flash('User updated.')
      load()
    } catch (e: any) {
      setError(e.message || 'Update failed')
    }
  }

  const orgAction = async (path: string, confirmMsg: string, okMsg: string) => {
    if (!confirm(confirmMsg)) return
    setError('')
    try {
      await api.post(`/admin/organizations/${orgId}/${path}`, { reason: `super-admin ${path}` })
      flash(okMsg)
      load()
    } catch (e: any) {
      setError(e.message || 'Action failed')
    }
  }

  const deleteOrg = async () => {
    if (!confirm(`Delete "${o.name}" and ALL its data? It can be restored for 14 days, then it's permanently purged.`)) return
    setError('')
    try {
      await api.delete(`/admin/organizations/${orgId}`)
      flash('Organization deleted — restorable for 14 days.')
      load()
    } catch (e: any) { setError(e.message || 'Delete failed') }
  }

  const restoreOrg = async () => {
    setError('')
    try {
      await api.post(`/admin/organizations/${orgId}/restore`, { reason: 'super-admin restore' })
      flash('Organization restored.')
      load()
    } catch (e: any) { setError(e.message || 'Restore failed') }
  }

  const deleteUser = async (u: OrgUser) => {
    if (!confirm(`Delete ${u.email}? They lose access now and are purged after 14 days (restorable until then).`)) return
    setError('')
    try {
      await api.delete(`/admin/users/${u.id}`)
      flash('User deleted.')
      load()
    } catch (e: any) { setError(e.message || 'Delete failed') }
  }

  const restoreUser = async (u: OrgUser) => {
    setError('')
    try {
      await api.post(`/admin/users/${u.id}/restore`, { reason: 'super-admin restore' })
      flash('User restored.')
      load()
    } catch (e: any) { setError(e.message || 'Restore failed') }
  }

  const toggleLocationBilling = async (loc: OrgLocation) => {
    const next = loc.billing_status === 'active' ? 'pending_payment' : 'active'
    if (!confirm(`Set "${loc.location_name}" billing to ${next}?`)) return
    setError('')
    try {
      await api.patch(`/admin/locations/${loc.id}`, { billing_status: next, reason: 'super-admin toggle' })
      flash('Location updated.')
      load()
    } catch (e: any) {
      setError(e.message || 'Update failed')
    }
  }

  if (loading || !data || !form) {
    return <div className="text-sm text-muted-foreground">Loading…</div>
  }

  const o = data.organization

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/admin" className="inline-flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground mb-2">
            <ArrowLeft className="h-3.5 w-3.5" /> All accounts
          </Link>
          <h1 className="text-lg font-bold">{o.name} <span className="text-muted-foreground font-normal">#{o.id}</span></h1>
          <p className="text-xs text-muted-foreground mt-0.5">Created {fmt(o.created_at)} · {o.user_count} users · {o.location_count} locations</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={load} className="flex items-center gap-1.5 rounded-lg border border-border bg-card px-3 py-2 text-sm font-semibold hover:bg-muted/40">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
          {!o.deleted_at && (
            <button onClick={deleteOrg} className="rounded-lg border border-red-500/40 text-red-600 px-3 py-2 text-sm font-semibold hover:bg-red-500/10">
              Delete account
            </button>
          )}
        </div>
      </div>

      {msg && <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-2.5 text-sm text-emerald-600">{msg}</div>}
      {error && <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2.5 text-sm text-red-600">{error}</div>}

      {o.deleted_at && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <span className="text-sm text-red-600 font-semibold">
            Deleted {fmt(o.deleted_at)} · permanently purged {fmt(new Date(new Date(o.deleted_at).getTime() + 14 * 864e5).toISOString())}. Restore before then to recover all data.
          </span>
          <button onClick={restoreOrg} className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:opacity-90 shrink-0">
            Restore account
          </button>
        </div>
      )}

      {/* Billing & plan */}
      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-4">Billing &amp; plan</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Subscription status">
            <select value={form.subscription_status} onChange={(e) => setForm({ ...form, subscription_status: e.target.value })} className={inputCls}>
              <option value="">— unset —</option>
              <option value="trial">trial</option>
              <option value="active">active</option>
              <option value="past_due">past_due</option>
              <option value="locked">locked</option>
            </select>
          </Field>
          <Field label="Plan tier">
            <select value={form.plan_tier} onChange={(e) => setForm({ ...form, plan_tier: e.target.value })} className={inputCls}>
              <option value="basic">basic</option>
              <option value="pro">pro</option>
            </select>
          </Field>
          <Field label="Location quota">
            <input type="number" min={0} value={form.location_quota} onChange={(e) => setForm({ ...form, location_quota: e.target.value })} className={inputCls} />
          </Field>
          <Field label="Monthly AI credits">
            <input type="number" min={0} value={form.monthly_ai_credits_balance} onChange={(e) => setForm({ ...form, monthly_ai_credits_balance: e.target.value })} className={inputCls} />
          </Field>
          <Field label="Top-up AI credits">
            <input type="number" min={0} value={form.topup_ai_credits_balance} onChange={(e) => setForm({ ...form, topup_ai_credits_balance: e.target.value })} className={inputCls} />
          </Field>
          <Field label="Trial ends at">
            <input type="datetime-local" value={form.trial_ends_at} onChange={(e) => setForm({ ...form, trial_ends_at: e.target.value })} className={inputCls} />
          </Field>
          <Field label="Grace period ends at">
            <input type="datetime-local" value={form.grace_period_ends_at} onChange={(e) => setForm({ ...form, grace_period_ends_at: e.target.value })} className={inputCls} />
          </Field>
          <Field label="Reason (audited)">
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="why are you making this change?" className={inputCls} />
          </Field>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button disabled={saving} onClick={saveBilling} className="rounded-lg bg-primary px-4 py-2 text-sm font-bold text-white hover:opacity-90 disabled:opacity-50">
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          {o.subscription_needs_remandate && (
            <span className="text-xs text-amber-600 font-semibold">⚠ UPI re-mandate pending (paid quota {o.paid_location_quota ?? '—'})</span>
          )}
        </div>
        <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-muted-foreground">
          <Meta label="Renews / ends" value={fmt(o.subscription_ends_at)} />
          <Meta label="Credits reset" value={fmt(o.ai_credits_reset_date)} />
          <Meta label="Razorpay sub" value={o.razorpay_subscription_id || '—'} />
          <Meta label="Billing cycle" value={o.billing_cycle || '—'} />
        </div>
      </section>

      {/* Enterprise custom pricing (Flavor B: per-location) */}
      <section className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-sm font-bold uppercase tracking-wider">Enterprise custom pricing</h2>
          {(o.custom_price_paise != null || o.custom_credits_per_location != null) && (
            <span className="text-[10px] font-bold uppercase text-emerald-600">Active</span>
          )}
        </div>
        <p className="text-xs text-muted-foreground mb-4">
          Overrides standard tiers for this org only. Price is charged per location; annual = rate × 12 (no extra discount).
          Leave blank for standard pricing. Uses the &quot;Reason&quot; field above for the audit log; click &quot;Save changes&quot; to apply.
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Field label="Price per location (₹ / month)">
            <input type="number" min={0} value={form.custom_price_rupees}
                   onChange={(e) => setForm({ ...form, custom_price_rupees: e.target.value })}
                   placeholder="standard" className={inputCls} />
          </Field>
          <Field label="AI credits per location">
            <input type="number" min={0} value={form.custom_credits_per_location}
                   onChange={(e) => setForm({ ...form, custom_credits_per_location: e.target.value })}
                   placeholder="standard" className={inputCls} />
          </Field>
          <div className="flex items-end">
            {(o.custom_price_paise != null || o.custom_credits_per_location != null) && (
              <button onClick={clearCustomPricing} disabled={saving}
                      className="rounded-lg border border-red-500/40 text-red-600 px-4 py-2 text-sm font-semibold hover:bg-red-500/10 disabled:opacity-50">
                Remove custom pricing
              </button>
            )}
          </div>
        </div>
        {form.custom_price_rupees !== '' && (
          <p className="mt-3 text-xs text-muted-foreground">
            Preview at quota {o.location_quota ?? '—'}: {o.location_quota
              ? `₹${(Number(form.custom_price_rupees) * o.location_quota).toLocaleString('en-IN')}/mo`
              : 'set a location quota to preview'}
            {form.custom_credits_per_location !== '' && o.location_quota
              ? ` · ${Number(form.custom_credits_per_location) * o.location_quota} credits/mo`
              : ''}
          </p>
        )}
      </section>

      {/* Users */}
      <section className="rounded-xl border border-border bg-card p-5">
        <h2 className="text-sm font-bold uppercase tracking-wider mb-4">Users</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2 font-bold">User</th>
                <th className="px-3 py-2 font-bold">Role</th>
                <th className="px-3 py-2 font-bold">Active</th>
                <th className="px-3 py-2 font-bold text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.users.map((u) => (
                <tr key={u.id} className="border-b border-border/60">
                  <td className="px-3 py-2">
                    <div className="font-semibold">
                      {u.name}
                      {u.deleted_at && <span className="ml-2 text-[10px] font-bold uppercase text-red-600">deleted</span>}
                    </div>
                    <div className="text-[11px] text-muted-foreground">{u.email}</div>
                  </td>
                  <td className="px-3 py-2">
                    <select
                      value={u.role}
                      onChange={(e) => patchUser(u.id, { role: e.target.value, reason: 'super-admin role change' }, `Change ${u.email} to ${e.target.value}? This logs them out of all sessions.`)}
                      className="rounded-md border border-border bg-card px-2 py-1 text-xs"
                    >
                      {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <span className={`text-xs font-semibold ${u.is_active ? 'text-emerald-600' : 'text-red-600'}`}>{u.is_active ? 'Active' : 'Inactive'}</span>
                  </td>
                  <td className="px-3 py-2 text-right space-x-3 whitespace-nowrap">
                    <button
                      onClick={() => patchUser(u.id, { is_active: !u.is_active, reason: 'super-admin toggle' }, `${u.is_active ? 'Deactivate' : 'Reactivate'} ${u.email}?`)}
                      className="text-xs font-semibold text-muted-foreground hover:text-foreground underline"
                    >
                      {u.is_active ? 'Deactivate' : 'Reactivate'}
                    </button>
                    <button
                      onClick={() => patchUser(u.id, { force_logout: true, reason: 'super-admin force logout' }, `Force-logout ${u.email} from all sessions?`)}
                      className="text-xs font-semibold text-muted-foreground hover:text-red-500 underline"
                    >
                      Force logout
                    </button>
                    {u.deleted_at ? (
                      <button onClick={() => restoreUser(u)} className="text-xs font-semibold text-primary hover:underline">
                        Restore
                      </button>
                    ) : (
                      <button onClick={() => deleteUser(u)} className="text-xs font-semibold text-red-600 hover:underline">
                        Delete
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Locations & sync operations */}
      <section className="rounded-xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
          <h2 className="text-sm font-bold uppercase tracking-wider">Locations &amp; sync</h2>
          <div className="flex items-center gap-2">
            {data.sync_state.sync_in_progress && (
              <span className="text-[11px] font-semibold text-amber-600">sync in progress…</span>
            )}
            <button
              onClick={() => orgAction('sync', 'Queue an org-wide review re-sync now?', 'Review sync queued.')}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold hover:bg-muted/40"
            >
              Force review sync
            </button>
            <button
              onClick={() => orgAction('reset-sync', 'Clear the stuck sync lock for this org?', 'Sync state reset.')}
              className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold hover:bg-muted/40"
            >
              Reset stuck sync
            </button>
          </div>
        </div>
        <div className="mb-3 text-[11px] text-muted-foreground">
          Last review sync: {fmt(data.sync_state.last_review_sync_at)} · Status: {data.sync_state.last_sync_status || '—'}
          {data.sync_state.last_sync_error ? ` · Error: ${data.sync_state.last_sync_error}` : ''}
        </div>
        {data.locations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No locations.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2 font-bold">Name</th>
                  <th className="px-3 py-2 font-bold">Billing</th>
                  <th className="px-3 py-2 font-bold">Sync</th>
                  <th className="px-3 py-2 font-bold">Rating</th>
                  <th className="px-3 py-2 font-bold">Reviews</th>
                  <th className="px-3 py-2 font-bold">Last sync</th>
                  <th className="px-3 py-2 font-bold text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.locations.map((l) => (
                  <tr key={l.id} className="border-b border-border/60">
                    <td className="px-3 py-2 font-semibold">{l.location_name}</td>
                    <td className="px-3 py-2">
                      <span className={`text-xs font-semibold ${l.billing_status === 'active' ? 'text-emerald-600' : 'text-amber-600'}`}>{l.billing_status || '—'}</span>
                    </td>
                    <td className="px-3 py-2">{l.sync_status || '—'}</td>
                    <td className="px-3 py-2">{l.average_rating ?? '—'}</td>
                    <td className="px-3 py-2">{l.total_reviews ?? '—'}</td>
                    <td className="px-3 py-2 text-muted-foreground">{fmt(l.last_synced_at)}</td>
                    <td className="px-3 py-2 text-right whitespace-nowrap">
                      <button onClick={() => toggleLocationBilling(l)} className="text-xs font-semibold text-muted-foreground hover:text-foreground underline">
                        {l.billing_status === 'active' ? 'Mark pending' : 'Mark active'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Transactions + Audit */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="text-sm font-bold uppercase tracking-wider mb-4">Recent transactions</h2>
          {data.transactions.length === 0 ? (
            <p className="text-sm text-muted-foreground">None.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.transactions.map((t) => (
                <li key={t.id} className="flex items-center justify-between border-b border-border/50 pb-2">
                  <div>
                    <div className="font-semibold">{t.type || 'charge'}{t.source ? <span className="text-[10px] text-muted-foreground"> ({t.source})</span> : null}</div>
                    <div className="text-[11px] text-muted-foreground">{fmt(t.created_at)} · {t.status}</div>
                  </div>
                  <div className="text-right">
                    <div className="font-semibold">{paise(t.amount_paise)}</div>
                    {t.credits != null && <div className="text-[11px] text-muted-foreground">{t.credits} credits</div>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <h2 className="text-sm font-bold uppercase tracking-wider mb-4">Audit trail</h2>
          {data.audit.length === 0 ? (
            <p className="text-sm text-muted-foreground">No entries.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {data.audit.map((a) => (
                <li key={a.id} className="border-b border-border/50 pb-2">
                  <div className="font-semibold">{a.action}</div>
                  {a.details && <div className="text-[11px] text-muted-foreground break-words">{a.details}</div>}
                  <div className="text-[10px] text-muted-foreground mt-0.5">{fmt(a.created_at)}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  )
}
