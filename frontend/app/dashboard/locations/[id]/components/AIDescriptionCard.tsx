'use client'

import { useEffect, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Sparkles, Loader2, Copy, Check, RefreshCw, AlertTriangle } from 'lucide-react'

import { api } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/dialog'
import { useAuth } from '@/hooks/useAuth'
import { useLocationWorkspace } from '@/hooks/useLocationWorkspace'
import { useBillingStatus } from '@/hooks/useBilling'

interface PolicyFlags { hard: string[]; soft: string[] }
interface DescriptionResponse {
  charged: boolean
  credits_charged: number
  is_valid: boolean
  description: string
  char_count: number
  status: string
  policy_flags: PolicyFlags
  improvement_notes: string[]
  seo_terms: string[]
  category_mentioned: string
  locality_used: string
}
interface ValidateResponse { is_valid: boolean; hard_flags: string[]; soft_flags: string[]; char_count: number }

const FLAG_LABELS: Record<string, string> = {
  exceeds_750_chars: 'Too long (over 750 characters)',
  contains_link: 'Contains a link or web address',
  contains_email: 'Contains an email address',
  contains_html: 'Contains HTML tags',
  contains_phone: 'Contains a phone number',
  promotion_language: 'Promotional wording (sale / offer / discount)',
  price_language: 'Mentions a price',
  unverified_claim: 'Unverifiable claim (No.1, guaranteed, top-rated)',
  keyword_stuffing: 'A word is repeated too many times',
  thin_description: 'Too short — aim for 550–700 characters',
  soft_superlative: 'Soft superlative (best / leading / free / offer)',
  robotic_phrase: 'Robotic phrase — sounds AI-generated',
  no_category_mention: 'Does not mention your business category',
}
const flagLabel = (f: string) => FLAG_LABELS[f] || f

const TONES = ['professional', 'friendly', 'premium', 'local', 'expert', 'clinic_safe', 'luxury']
const AUDIENCE_SUGGESTIONS = ['Local customers', 'Families', 'Patients', 'Diners', 'Students', 'Brides', 'Professionals', 'Homeowners', 'Seniors']
const EDIT_STATUS_LABEL: Record<string, string> = {
  Draft: 'Draft', Pending: 'Pending approval', Approved: 'Approved',
  Publishing: 'Publishing', Published: 'Published', Failed: 'Failed',
}

// GBP service_items -> a comma-separated list of service names to prefill the form.
function extractServiceNames(items: any): string {
  if (!Array.isArray(items)) return ''
  const names = items
    .map((it) => it?.freeFormServiceItem?.label?.displayName || it?.structuredServiceItem?.description || (typeof it === 'string' ? it : ''))
    .filter(Boolean)
  // Cap the prefill — 5-6 core services beat cramming 10+ (which overshoots length + stuffs keywords).
  return Array.from(new Set(names)).slice(0, 6).join(', ')
}
const NUDGES = [
  { key: 'shorter', label: 'Shorter' },
  { key: 'warmer', label: 'Warmer' },
  { key: 'local', label: 'More local' },
  { key: 'premium', label: 'More premium' },
  { key: 'seo', label: 'SEO' },
]

function charColor(n: number): string {
  if (n === 0) return 'text-muted-foreground'
  if (n < 350 || n > 750) return 'text-destructive'
  if (n >= 550 && n <= 740) return 'text-emerald-600'
  return 'text-amber-600'
}

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  Good: 'default', Weak: 'destructive', Thin: 'secondary', Missing: 'outline',
}

interface Props { locationId: number }

export function AIDescriptionCard({ locationId }: Props) {
  const { isAdmin } = useAuth()
  const queryClient = useQueryClient()
  const { location, healthScore, edits, createEditMutation, submitMutation, approveMutation, publishMutation } = useLocationWorkspace(locationId)
  const { data: billing } = useBillingStatus()

  const current: string = location?.description || ''
  const descBreakdown = healthScore?.breakdown?.description
  // Undefined = not scored yet (e.g. health score predates this feature). Never
  // guess "Weak" for an existing description — that's what misled before.
  const status = descBreakdown?.status ?? (current ? undefined : 'Missing')

  const available = (billing?.monthly_ai_credits_balance ?? 0) + (billing?.topup_ai_credits_balance ?? 0)
  // First generation can cost 5; regenerations cost 2. Gate each on its own worst case
  // so the button is never enabled for a click the server will 402 (price is server-decided).
  const tooFewForGenerate = available < 5
  const tooFewForRegen = available < 2

  const [tone, setTone] = useState('professional')
  const [draft, setDraft] = useState<DescriptionResponse | null>(null)
  const [editedText, setEditedText] = useState('')
  const [liveFlags, setLiveFlags] = useState<ValidateResponse | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  // §5 inputs — the difference between generic and good output.
  const [usp, setUsp] = useState('')
  const [servicesText, setServicesText] = useState('')
  const [audience, setAudience] = useState('')
  const didPrefill = useRef(false)
  // Track the latest textarea value so out-of-order /validate responses can be discarded.
  const editedTextRef = useRef('')
  editedTextRef.current = editedText

  // Prefill services from the location's GBP service list once it loads (user can curate).
  useEffect(() => {
    if (location && !didPrefill.current) {
      didPrefill.current = true
      const s = extractServiceNames(location.service_items)
      if (s) setServicesText(s)
    }
  }, [location])

  const generateMutation = useMutation({
    mutationFn: (body: Record<string, any>) =>
      api.post<DescriptionResponse>(`/locations/${locationId}/description/generate`, body),
    onMutate: () => setLiveFlags(null),  // drop stale flags while a (re)generation is in flight
    onSuccess: (data) => {
      setDraft(data)
      setEditedText(data.description)
      setLiveFlags(null)
      queryClient.invalidateQueries({ queryKey: ['billing_status'] })
      if (!data.charged) {
        toast.warning("Couldn't produce a fully policy-safe version — you were not charged. Edit the highlighted issues.")
      } else {
        toast.success(`Description ready · ${data.credits_charged} credits used`)
      }
    },
    onError: (err: any) => toast.error(err.message || 'Generation failed'),
  })

  const validateMutation = useMutation({
    mutationFn: (text: string) =>
      api.post<ValidateResponse>(`/locations/${locationId}/description/validate`, { text }),
    // Ignore a response whose text is no longer what's in the box (out-of-order resolve).
    onSuccess: (data, text) => { if (text === editedTextRef.current) setLiveFlags(data) },
  })

  // Debounced live validation while the user hand-edits the draft.
  useEffect(() => {
    if (!draft || !editedText.trim()) return
    const t = setTimeout(() => validateMutation.mutate(editedText), 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editedText, draft])

  const run = (mode: 'generate_new' | 'improve_existing', nudge?: string) => {
    const services = servicesText.split(',').map((s) => s.trim()).filter(Boolean)
    generateMutation.mutate({
      mode, tone, nudge,
      usp: usp.trim() || undefined,
      services: services.length ? services : undefined,
      audience: audience.trim() || undefined,
      base_text: mode === 'improve_existing' ? (editedText || current) : undefined,
    })
  }

  const onPrimary = () => {
    if (status === 'Good' && !draft) { setConfirmOpen(true); return }
    run(current ? 'improve_existing' : 'generate_new')
  }

  const copy = () => {
    navigator.clipboard.writeText(editedText)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  // In-card publish via the existing listing-edit pipeline (no Tasks-tab detour).
  const descEdit = edits?.find((e) => e.field_name === 'description' &&
    ['Draft', 'Pending', 'Approved', 'Publishing', 'Failed'].includes(e.status))
  const save = () => createEditMutation.mutate(
    { field_name: 'description', new_value: editedText, warning_acknowledged: false },
  )
  const approveAndPublish = () => descEdit && approveMutation.mutate(
    { editId: descEdit.id, version: descEdit.version },
    { onSuccess: () => publishMutation.mutate({ editId: descEdit.id }) },
  )

  const busy = generateMutation.isPending
  const charCount = editedText.length
  const hard = liveFlags?.hard_flags ?? draft?.policy_flags.hard ?? []
  const soft = liveFlags?.soft_flags ?? draft?.policy_flags.soft ?? []

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium text-foreground border-b border-border/50 pb-2">AI Business Description</h3>

      <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm space-y-4">
        {/* Header: status + score */}
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium">Description status</span>
            {status
              ? <Badge variant={STATUS_VARIANT[status] || 'outline'}>{status === 'Good' ? 'Optimized' : status}</Badge>
              : <span className="text-xs text-muted-foreground">Not scored yet</span>}
          </div>
          {descBreakdown && (
            <span className="text-xs text-muted-foreground">{descBreakdown.score} / {descBreakdown.max_score} · {descBreakdown.char_count} chars</span>
          )}
        </div>

        {/* §5 inputs — the difference between generic and good output. Prefilled where possible. */}
        <div className="space-y-3 rounded-lg bg-muted/20 border border-border/50 p-3">
          <div className="space-y-1">
            <Label htmlFor="desc-usp" className="text-xs">What makes your business special?</Label>
            <Textarea id="desc-usp" value={usp} onChange={(e) => setUsp(e.target.value)}
              placeholder="e.g. certified lab-grown diamonds, transparent pricing, 40 years of family craftsmanship"
              className="min-h-[56px] text-sm" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="desc-services" className="text-xs">Top services / products</Label>
            <Input id="desc-services" value={servicesText} onChange={(e) => setServicesText(e.target.value)}
              placeholder="comma-separated — prefilled from your Google profile" className="text-sm" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="desc-audience" className="text-xs">Who do you serve?</Label>
              <Input id="desc-audience" list="desc-audience-list" value={audience}
                onChange={(e) => setAudience(e.target.value)} placeholder="e.g. families, brides" className="text-sm" />
              <datalist id="desc-audience-list">
                {AUDIENCE_SUGGESTIONS.map((a) => <option key={a} value={a} />)}
              </datalist>
            </div>
            <div className="space-y-1">
              <Label htmlFor="desc-tone" className="text-xs">Tone</Label>
              <select id="desc-tone" value={tone} onChange={(e) => setTone(e.target.value)}
                className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm">
                {TONES.map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}
              </select>
            </div>
          </div>
        </div>

        {/* Pre-generation: show current description + free checklist */}
        {!draft && (
          <>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap rounded-lg bg-muted/30 border border-border/50 p-3 min-h-[60px]">
              {current || 'No description yet.'}
            </p>
            {descBreakdown && (descBreakdown.hard_flags.length > 0 || descBreakdown.soft_flags.length > 0) && (
              <ul className="space-y-1">
                {[...descBreakdown.hard_flags, ...descBreakdown.soft_flags].map((f) => (
                  <li key={f} className="flex items-center gap-2 text-xs text-muted-foreground">
                    <AlertTriangle className="h-3 w-3 text-amber-600 shrink-0" /> {flagLabel(f)}
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={onPrimary} disabled={busy || tooFewForGenerate} title={tooFewForGenerate ? 'Not enough AI credits' : ''}>
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {current ? 'Improve with AI' : 'Generate description'}
              </Button>
              <span className="text-xs text-muted-foreground">
                First generation 5 credits · regenerations 2 · you have {available}
              </span>
            </div>
          </>
        )}

        {/* Post-generation: editable draft */}
        {draft && (
          <>
            {!draft.is_valid && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>Not fully policy-safe — not charged</AlertTitle>
                <AlertDescription>We rewrote it once but some issues remain. Edit the highlighted items below, then save.</AlertDescription>
              </Alert>
            )}

            <Textarea value={editedText} onChange={(e) => setEditedText(e.target.value)} className="min-h-[140px] text-sm" />
            <div className="flex items-center justify-between text-xs">
              <span className={charColor(charCount)}>{charCount} characters {charCount > 750 ? '(over Google limit)' : charCount >= 700 && charCount <= 740 ? '(ideal)' : ''}</span>
              <button onClick={copy} className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground transition-colors">
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />} {copied ? 'Copied' : 'Copy'}
              </button>
            </div>

            {(hard.length > 0 || soft.length > 0) && (
              <ul className="space-y-1">
                {hard.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-xs text-destructive">
                    <AlertTriangle className="h-3 w-3 shrink-0" /> {flagLabel(f)}
                  </li>
                ))}
                {soft.map((f) => (
                  <li key={f} className="flex items-center gap-2 text-xs text-amber-600">
                    <AlertTriangle className="h-3 w-3 shrink-0" /> {flagLabel(f)}
                  </li>
                ))}
              </ul>
            )}

            {draft.improvement_notes.length > 0 && (
              <div className="text-xs text-muted-foreground">
                <span className="font-medium text-foreground">What the AI focused on: </span>
                {draft.improvement_notes.join(' · ')}
              </div>
            )}

            {/* Regenerate controls (tone/inputs live in the form above) */}
            <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border/50">
              <span className="text-xs text-muted-foreground self-center mr-1">Regenerate:</span>
              {NUDGES.map((n) => (
                <Button key={n.key} variant="outline" size="sm" disabled={busy || tooFewForRegen}
                        onClick={() => run('improve_existing', n.key)}>
                  {n.label}
                </Button>
              ))}
              <Button variant="ghost" size="sm" disabled={busy || tooFewForRegen} onClick={() => run('improve_existing')}>
                <RefreshCw className="h-3 w-3" /> Regenerate
              </Button>
            </div>

            {/* Publish to Google — in-card, reuses the listing-edit pipeline */}
            <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-border/50">
              {!isAdmin ? (
                <span className="text-xs text-muted-foreground">An admin reviews &amp; publishes description changes.</span>
              ) : !descEdit ? (
                <>
                  <Button variant="secondary" disabled={hard.length > 0 || !editedText.trim() || createEditMutation.isPending} onClick={save}>
                    Save &amp; publish to Google
                  </Button>
                  <span className="text-xs text-muted-foreground">Submits this as a Google profile update.</span>
                </>
              ) : (
                <>
                  <Badge variant={descEdit.status === 'Failed' ? 'destructive' : descEdit.status === 'Publishing' ? 'secondary' : 'outline'}>
                    {EDIT_STATUS_LABEL[descEdit.status] || descEdit.status}
                  </Badge>
                  {descEdit.status === 'Draft' && (
                    <Button size="sm" disabled={submitMutation.isPending}
                      onClick={() => submitMutation.mutate({ editId: descEdit.id, version: descEdit.version })}>Submit for approval</Button>
                  )}
                  {descEdit.status === 'Pending' && (
                    <Button size="sm" disabled={approveMutation.isPending || publishMutation.isPending} onClick={approveAndPublish}>Approve &amp; publish</Button>
                  )}
                  {descEdit.status === 'Approved' && (
                    <Button size="sm" disabled={publishMutation.isPending}
                      onClick={() => publishMutation.mutate({ editId: descEdit.id })}>Publish to Google</Button>
                  )}
                  {descEdit.status === 'Publishing' && (
                    <span className="text-xs text-muted-foreground inline-flex items-center gap-1"><Loader2 className="h-3 w-3 animate-spin" /> Publishing to Google…</span>
                  )}
                  {descEdit.status === 'Failed' && (
                    <span className="text-xs text-destructive">Failed: {descEdit.failure_reason || 'unknown error'}</span>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </div>

      {/* Improve-anyway confirm for an already-optimized description */}
      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Regenerate an already-optimized description?</DialogTitle>
            <DialogDescription>
              Your description already scores well. Regenerating will cost AI credits. Continue?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>Cancel</Button>
            <Button onClick={() => { setConfirmOpen(false); run('improve_existing') }}>Improve anyway</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
