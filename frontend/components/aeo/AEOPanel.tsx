'use client'

import { Fragment, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Lock, RefreshCw, AlertCircle, Plus, X, Printer, ChevronDown, ChevronRight } from 'lucide-react'
import { api } from '@/lib/api'
import { useBillingStatus } from '@/hooks/useBilling'
import { Button } from '@/components/ui/button'
import { SurfaceLogo } from './brandMarks'

const ACCENT = '#2F63E6'   // score gauge + coverage bar

// Brand colour per AI surface for the presence bars (matches the mockup).
const SURFACE_COLOR: Record<string, string> = {
  chatgpt: '#10A37F',
  google_ai_overview: '#2F63E6',
  gemini: '#7A5AF0',
  google_ai_mode: '#1E9E6A',
  perplexity: '#C6871B',
}
const surfaceColor = (key: string) => SURFACE_COLOR[key] ?? ACCENT

interface SurfaceStat { key: string; label: string; present_pct: number; mentions: number }
interface QuerySurface { present: boolean; rank: number | null }
interface QueryRow { query: string; surfaces: Record<string, QuerySurface>; competitors: string[]; sources: string[]; snippet?: string }
interface SovRow { name: string; pct: number; self: boolean }
type Rec = string | { title: string; detail: string }
interface AEOResult {
  ai_visibility_score: number; score_delta: number; queries_tracked: number
  surfaces: SurfaceStat[]; queries: QueryRow[]; share_of_voice?: SovRow[]; recommendations: Rec[]
}
interface Scan {
  id: number; tier: string; status: string; ai_visibility_score: number | null
  score_delta: number | null; queries_tracked: number
  result: AEOResult | Record<string, never>; error: string | null; created_at: string
}
interface ScanSummary { id: number; tier: string; status: string; ai_visibility_score: number | null; score_delta: number | null; queries_tracked: number; error: string | null; created_at: string }
const fmtDateTime = (iso: string) => new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
interface Quota { per_month: number; used_this_month: boolean; tier: string | null; in_trial: boolean; resets_on: string }
interface Queries { auto: string[]; custom: string[]; auto_enabled: boolean; max_custom: number; max_queries: number }

const fmtDate = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

export function AEOPanel({ locationId, locationName }: { locationId: number; locationName?: string }) {
  const qc = useQueryClient()
  const { data: billing } = useBillingStatus()
  const isPro = billing?.plan_tier === 'pro'

  const { data: quota } = useQuery<Quota>({
    queryKey: ['aeo-quota', locationId],
    queryFn: () => api.get(`/aeo/locations/${locationId}/quota`),
  })
  const { data: scans = [] } = useQuery<ScanSummary[]>({
    queryKey: ['aeo-scans', locationId],
    queryFn: () => api.get(`/aeo/locations/${locationId}/scans`),
  })

  const [scanId, setScanId] = useState<number | null>(null)
  useEffect(() => { if (scanId == null && scans[0]) setScanId(scans[0].id) }, [scans, scanId])

  const { data: scan } = useQuery<Scan>({
    queryKey: ['aeo-scan', scanId],
    enabled: !!scanId,
    queryFn: () => api.get(`/aeo/locations/${locationId}/scans/${scanId}`),
    refetchInterval: (q) => (q.state.data?.status === 'Pending' ? 2000 : false),
  })

  const run = useMutation({
    mutationFn: () => api.post<Scan>(`/aeo/locations/${locationId}/scan`),
    onSuccess: (s) => {
      setScanId(s.id)
      qc.invalidateQueries({ queryKey: ['aeo-scans', locationId] })
      qc.invalidateQueries({ queryKey: ['aeo-quota', locationId] })
    },
  })

  const inTrial = !!quota?.in_trial
  const used = !!quota?.used_this_month
  const running = scan?.status === 'Pending' || run.isPending
  const failed = scan?.status === 'Failed'
  const result = scan?.status === 'Completed' ? (scan.result as AEOResult) : null

  return (
    <div className="space-y-5">
      <div className="no-print"><TrackedQueries locationId={locationId} /></div>

      {/* Control bar */}
      <div className="no-print flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
        <div>
          <div className="flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="h-4 w-4 text-primary" /> Monthly AI Visibility sync
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {quota?.tier === 'full'
              ? 'Google AI + ChatGPT, Gemini & Perplexity + share of voice'
              : 'Google AI Overview & AI Mode'}
            {' · '}1 sync / location / month
          </p>
        </div>
        <div className="flex items-center gap-3">
          {inTrial ? (
            <a href="/dashboard/settings/billing" className="text-xs font-semibold text-primary hover:underline">
              Activate subscription to unlock
            </a>
          ) : used && !running ? (
            <span className="text-xs text-muted-foreground">
              Resets {quota?.resets_on ? fmtDate(quota.resets_on) : ''}
            </span>
          ) : null}
          {result && (
            <button
              onClick={() => window.print()}
              className="inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-semibold hover:bg-muted/40"
            >
              <Printer className="h-4 w-4" /> Download PDF
            </button>
          )}
          <Button onClick={() => run.mutate()} disabled={inTrial || used || running}>
            {inTrial ? 'Locked in trial'
              : running ? <><RefreshCw className="h-4 w-4 animate-spin" /> Scanning…</>
              : used ? 'Synced this month' : 'Run monthly sync'}
          </Button>
        </div>
      </div>

      {run.isError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-600">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {(run.error as any)?.message || 'Could not start the sync. Please try again.'}
        </div>
      )}

      {/* States */}
      {!scanId && !running && (
        <EmptyState onRun={() => run.mutate()} disabled={used || inTrial} inTrial={inTrial} />
      )}
      {running && <RunningState />}
      {failed && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-sm text-red-600">
          <AlertCircle className="h-4 w-4 shrink-0" />
          Scan failed — {scan?.error || 'provider error'}. Your monthly sync was refunded; try again.
        </div>
      )}

      {result && (
        <div className="aeo-print space-y-5">
          {/* Print-only report header (hidden on screen, shown in the PDF) */}
          <div className="aeo-print-only mb-4 border-b pb-3">
            <div className="text-lg font-bold">AI Visibility Report</div>
            <div className="text-sm">{locationName || `Location #${locationId}`}</div>
            <div className="text-xs">{scan?.created_at ? fmtDateTime(scan.created_at) : ''}</div>
          </div>
          <div className="grid gap-4 md:grid-cols-[280px_1fr]">
            <ScoreCard result={result} />
            <SurfaceCard surfaces={result.surfaces} />
          </div>
          <QueryTable result={result} />
          <div className="grid gap-4 md:grid-cols-2">
            <AnswerCoverageCard result={result} isPro={isPro} />
            <RecommendationsCard recs={result.recommendations} />
          </div>
        </div>
      )}

      {scans.length > 0 && (
        <div className="no-print">
          <ScanHistory scans={scans} selectedId={scanId} onSelect={setScanId} />
        </div>
      )}
    </div>
  )
}

function TrackedQueries({ locationId }: { locationId: number }) {
  const qc = useQueryClient()
  const { data } = useQuery<Queries>({
    queryKey: ['aeo-queries', locationId],
    queryFn: () => api.get(`/aeo/locations/${locationId}/queries`),
  })
  const [input, setInput] = useState('')
  const save = useMutation({
    mutationFn: (payload: { custom: string[]; auto_enabled: boolean }) =>
      api.put<Queries>(`/aeo/locations/${locationId}/queries`, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['aeo-queries', locationId] }),
  })

  const auto = data?.auto ?? []
  const custom = data?.custom ?? []
  const autoEnabled = data?.auto_enabled ?? true
  const atMax = custom.length >= (data?.max_custom ?? 10)
  const maxQueries = data?.max_queries ?? 20
  // Custom queries run first, autos fill the rest up to the plan's per-scan cap.
  const effectiveCount = Math.min((autoEnabled ? auto.length : 0) + custom.length, maxQueries)

  const add = () => {
    const q = input.trim()
    if (q.length >= 3 && !custom.includes(q) && !auto.includes(q) && !atMax) {
      save.mutate({ custom: [...custom, q], auto_enabled: autoEnabled })
      setInput('')
    }
  }
  const remove = (q: string) => save.mutate({ custom: custom.filter((x) => x !== q), auto_enabled: autoEnabled })
  const toggleAuto = () => {
    // Guard: can't turn auto off with no custom queries — nothing would run.
    if (autoEnabled && custom.length === 0) return
    save.mutate({ custom, auto_enabled: !autoEnabled })
  }

  return (
    <Card title="Tracked queries">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          We check these searches against the AI engines. Fewer queries = lower cost.
        </p>
        <span className="shrink-0 text-xs font-semibold tabular-nums text-muted-foreground">
          {effectiveCount}/{maxQueries} quer{effectiveCount === 1 ? 'y' : 'ies'} / scan · {custom.length}/{data?.max_custom ?? 10} custom
        </span>
      </div>

      {/* Auto on/off toggle */}
      <label className="mb-3 flex w-fit cursor-pointer items-center gap-2 text-xs font-medium">
        <button
          type="button"
          role="switch"
          aria-checked={autoEnabled}
          onClick={toggleAuto}
          disabled={autoEnabled && custom.length === 0}
          className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors disabled:opacity-50 ${autoEnabled ? 'bg-primary' : 'bg-muted-foreground/40'}`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${autoEnabled ? 'translate-x-4' : 'translate-x-0.5'}`} />
        </button>
        <span>Include auto-generated queries</span>
        {autoEnabled && custom.length === 0 && (
          <span className="text-[11px] text-muted-foreground">(add a custom query to turn off)</span>
        )}
      </label>

      <div className="flex flex-wrap gap-2">
        {autoEnabled && auto.map((q) => (
          <span key={q} className="inline-flex items-center gap-1.5 rounded-full bg-muted/50 px-3 py-1 text-xs text-muted-foreground">
            {q}<span className="rounded bg-muted px-1 text-[9px] font-bold uppercase tracking-wide">auto</span>
          </span>
        ))}
        {custom.map((q) => (
          <span key={q} className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-medium text-primary">
            {q}
            <button onClick={() => remove(q)} aria-label={`Remove ${q}`} className="rounded-full hover:bg-primary/20">
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
          placeholder={atMax ? 'Custom query limit reached' : 'Add a query, e.g. bridal jewellery Bandra'}
          disabled={atMax}
          maxLength={120}
          className="h-9 flex-1 rounded-md border border-border bg-background px-3 text-sm disabled:opacity-60"
        />
        <button
          onClick={add}
          disabled={atMax || input.trim().length < 3}
          className="inline-flex h-9 items-center gap-1 rounded-md border border-border px-3 text-sm font-semibold hover:bg-muted/40 disabled:opacity-50"
        >
          <Plus className="h-4 w-4" /> Add
        </button>
      </div>
      {save.isError && <p className="mt-2 text-xs text-red-600">Couldn&apos;t save — {(save.error as any)?.message || 'try again'}.</p>}
    </Card>
  )
}

function ScanHistory({ scans, selectedId, onSelect }: { scans: ScanSummary[]; selectedId: number | null; onSelect: (id: number) => void }) {
  const statusStyle = (s: string) =>
    s === 'Completed' ? 'bg-emerald-500/15 text-emerald-600'
      : s === 'Failed' ? 'bg-red-500/15 text-red-600'
      : 'bg-amber-500/15 text-amber-600'
  return (
    <Card title="Scan history">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase text-muted-foreground">
              <th className="py-2 pl-1 text-left font-semibold">Date</th>
              <th className="px-2 py-2 text-left font-semibold">Tier</th>
              <th className="px-2 py-2 text-center font-semibold">Queries</th>
              <th className="px-2 py-2 text-center font-semibold">Score</th>
              <th className="px-2 py-2 text-center font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {scans.map((s) => (
              <tr
                key={s.id}
                onClick={() => onSelect(s.id)}
                className={`cursor-pointer border-b border-border/60 last:border-0 hover:bg-muted/30 ${s.id === selectedId ? 'bg-primary/5' : ''}`}
              >
                <td className="py-2.5 pl-1">{fmtDateTime(s.created_at)}</td>
                <td className="px-2 py-2.5 capitalize">{s.tier === 'full' ? 'Pro' : 'Google'}</td>
                <td className="px-2 py-2.5 text-center tabular-nums">{s.queries_tracked}</td>
                <td className="px-2 py-2.5 text-center font-bold tabular-nums">{s.ai_visibility_score ?? '—'}</td>
                <td className="px-2 py-2.5 text-center">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${statusStyle(s.status)}`}>{s.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function Card({ title, children, className = '' }: { title?: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-border bg-card p-5 ${className}`}>
      {title && <h3 className="mb-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>}
      {children}
    </div>
  )
}

function ScoreCard({ result }: { result: AEOResult }) {
  const score = result.ai_visibility_score
  const circ = 2 * Math.PI * 52
  const offset = circ * (1 - score / 100)
  const delta = result.score_delta
  const presentAvg = result.surfaces.length
    ? Math.round(result.surfaces.reduce((a, s) => a + s.present_pct, 0) / result.surfaces.length)
    : 0
  return (
    <Card title="AI Visibility Score" className="flex flex-col items-center text-center">
      <div className="relative my-1 h-[130px] w-[130px]">
        <svg width="130" height="130" viewBox="0 0 130 130" className="-rotate-90">
          <circle cx="65" cy="65" r="52" fill="none" stroke="currentColor" strokeWidth="11" className="text-muted-foreground/15" />
          <circle cx="65" cy="65" r="52" fill="none" stroke="#2F63E6" strokeWidth="11" strokeLinecap="round"
            strokeDasharray={circ} strokeDashoffset={offset} />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-4xl font-extrabold tabular-nums" style={{ color: '#2F63E6' }}>{score}</span>
        </div>
      </div>
      {delta != null && (
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold tabular-nums ${
          delta >= 0 ? 'bg-emerald-500/15 text-emerald-600' : 'bg-red-500/15 text-red-600'}`}>
          {delta >= 0 ? '▲' : '▼'} {Math.abs(delta)} vs last
        </span>
      )}
      <p className="mt-2 text-xs text-muted-foreground">
        Present in <b className="tabular-nums text-foreground">{presentAvg}%</b> of AI answers
      </p>
    </Card>
  )
}

function SurfaceCard({ surfaces }: { surfaces: SurfaceStat[] }) {
  return (
    <Card title="Presence by AI surface">
      <div className="space-y-3">
        {surfaces.map((s) => {
          const c = surfaceColor(s.key)
          return (
            <div key={s.key} className="grid grid-cols-[150px_1fr_64px] items-center gap-3">
              <span className="flex items-center gap-2 truncate text-sm font-medium">
                <SurfaceLogo surfaceKey={s.key} className="h-4 w-4 shrink-0" />
                {s.label}
              </span>
              <div className="h-2.5 overflow-hidden rounded-full bg-muted/40">
                <div className="h-full rounded-full" style={{ width: `${s.present_pct}%`, background: c }} />
              </div>
              <span className="text-right text-sm font-bold tabular-nums" style={{ color: c }}>
                {s.present_pct}%<span className="ml-1 text-[10px] font-medium text-muted-foreground">{s.mentions}×</span>
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

function PresenceChip({ s }: { s?: QuerySurface }) {
  if (!s || !s.present) return <span className="inline-flex min-w-[28px] justify-center rounded-md bg-muted/40 px-1.5 py-0.5 text-xs font-bold text-muted-foreground">—</span>
  if (s.rank != null) return <span className="inline-flex min-w-[28px] justify-center rounded-md bg-primary/15 px-1.5 py-0.5 text-xs font-bold text-primary">#{s.rank}</span>
  return <span className="inline-flex min-w-[28px] justify-center rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-xs font-bold text-emerald-600">✓</span>
}

function QueryTable({ result }: { result: AEOResult }) {
  const cols = result.surfaces
  const [open, setOpen] = useState<number | null>(null)
  return (
    <Card title="Per-query breakdown">
      <p className="mb-2 text-xs text-muted-foreground">Tap a query to see what the AI said and which sources it cited.</p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="border-b border-border text-[11px] uppercase text-muted-foreground">
              <th className="py-2 pl-1 text-left font-semibold">Query</th>
              {cols.map((c) => <th key={c.key} className="px-1 py-2 text-center font-semibold">{c.label}</th>)}
            </tr>
          </thead>
          <tbody>
            {result.queries.map((q, i) => {
              const expanded = open === i
              const hasDetail = !!(q.snippet || q.sources?.length || q.competitors?.length)
              return (
                <Fragment key={i}>
                  <tr
                    onClick={() => hasDetail && setOpen(expanded ? null : i)}
                    className={`border-b border-border/60 ${hasDetail ? 'cursor-pointer hover:bg-muted/30' : ''} ${expanded ? 'bg-muted/20' : ''}`}
                  >
                    <td className="py-2.5 pl-1">
                      <div className="flex items-center gap-1.5 font-medium">
                        {hasDetail
                          ? (expanded ? <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" /> : <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />)
                          : <span className="w-3.5" />}
                        {q.query}
                      </div>
                    </td>
                    {cols.map((c) => (
                      <td key={c.key} className="px-1 py-2.5 text-center"><PresenceChip s={q.surfaces[c.key]} /></td>
                    ))}
                  </tr>
                  {expanded && (
                    <tr className="bg-muted/10">
                      <td colSpan={cols.length + 1} className="px-4 py-3 pl-8"><QueryDetail q={q} /></td>
                    </tr>
                  )}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function QueryDetail({ q }: { q: QueryRow }) {
  const Label = ({ children }: { children: React.ReactNode }) => (
    <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">{children}</div>
  )
  return (
    <div className="space-y-3">
      {q.snippet && (
        <div>
          <Label>What the AI said</Label>
          <p className="border-l-2 border-primary/30 pl-3 text-sm italic text-foreground/75">“{q.snippet}”</p>
        </div>
      )}
      {q.sources?.length > 0 && (
        <div>
          <Label>Sources the AI cited</Label>
          <div className="flex flex-wrap gap-1.5">
            {q.sources.map((s) => (
              <span key={s} className="rounded-full bg-muted/60 px-2.5 py-0.5 text-xs text-muted-foreground">{s}</span>
            ))}
          </div>
        </div>
      )}
      {q.competitors?.length > 0 && (
        <div>
          <Label>Also named</Label>
          <div className="flex flex-wrap gap-1.5">
            {q.competitors.map((c) => (
              <span key={c} className="rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs text-amber-700 dark:text-amber-400">{c}</span>
            ))}
          </div>
        </div>
      )}
      {!q.snippet && !q.sources?.length && !q.competitors?.length && (
        <p className="text-xs text-muted-foreground">No answer detail captured for this query.</p>
      )}
    </div>
  )
}

// Honest "coverage" — how often the business is named across all tracked answers.
// (Real competitor share-of-voice needs the AI-Mentions data we don't have yet.)
function AnswerCoverageCard({ result, isPro }: { result: AEOResult; isPro: boolean }) {
  const you = result.share_of_voice?.find((r) => r.self)?.pct
    ?? (result.surfaces.length ? Math.round(result.surfaces.reduce((a, s) => a + s.present_pct, 0) / result.surfaces.length) : 0)
  if (!isPro) {
    return (
      <Card title="AI answer coverage">
        <div className="flex flex-col items-center gap-2 py-6 text-center">
          <Lock className="h-5 w-5 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Track how often AI answers name your business, on Pro.</p>
          <a href="/dashboard/settings/billing" className="text-sm font-bold text-primary hover:underline">Upgrade to Pro →</a>
        </div>
      </Card>
    )
  }
  return (
    <Card title="AI answer coverage">
      <div className="flex items-baseline gap-2">
        <span className="text-3xl font-extrabold tabular-nums" style={{ color: ACCENT }}>{you}%</span>
        <span className="text-sm text-muted-foreground">of AI answers name your business</span>
      </div>
      <div className="mt-3 h-3 overflow-hidden rounded-full bg-muted/40">
        <div className="h-full rounded-full" style={{ width: `${you}%`, background: ACCENT }} />
      </div>
      <p className="mt-3 text-xs text-muted-foreground">Across every tracked query and AI surface — higher means you’re named more often.</p>
    </Card>
  )
}

function RecommendationsCard({ recs }: { recs: Rec[] }) {
  return (
    <Card title="Recommended actions">
      <ol className="space-y-3.5">
        {recs.map((r, i) => {
          const title = typeof r === 'string' ? r : r.title
          const detail = typeof r === 'string' ? '' : r.detail
          return (
            <li key={i} className="flex gap-3 text-sm">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-bold" style={{ background: 'rgba(47,99,230,.12)', color: ACCENT }}>{i + 1}</span>
              <div>
                <p className="font-semibold text-foreground">{title}</p>
                {detail && <p className="mt-0.5 text-muted-foreground">{detail}</p>}
              </div>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}

function EmptyState({ onRun, disabled, inTrial }: { onRun: () => void; disabled: boolean; inTrial?: boolean }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-border bg-card/50 p-10 text-center">
      <Sparkles className="h-7 w-7 text-primary" />
      <h3 className="text-base font-bold">Run your first AI Visibility scan</h3>
      <p className="max-w-md text-sm text-muted-foreground">
        See where this location shows up when people ask AI — ChatGPT, Gemini, Perplexity and Google&apos;s AI answers — for local searches.
      </p>
      {inTrial ? (
        <a href="/dashboard/settings/billing" className="mt-1 text-sm font-bold text-primary hover:underline">
          Activate your subscription to unlock →
        </a>
      ) : !disabled ? (
        <Button onClick={onRun} className="mt-1">Run monthly sync</Button>
      ) : null}
    </div>
  )
}

function RunningState() {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-border bg-card p-10 text-center">
      <RefreshCw className="h-7 w-7 animate-spin text-primary" />
      <p className="text-sm font-medium">Querying AI surfaces…</p>
      <p className="text-xs text-muted-foreground">This takes a few seconds.</p>
    </div>
  )
}
