'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useAuth } from '@/hooks/useAuth'
import {
  ReplyTemplate,
  CreateTemplatePayload,
  UpdateTemplatePayload,
  STAR_RATING_LIMITS,
  MIN_TEMPLATES_FOR_AUTO_REPLY,
  INSERTABLE_VARIABLES,
  fetchTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  getAutoReplyStatus,
  setAutoReply,
  type AutoReplyMode,
  getTemplateAnalytics,
  getAutoReplyLocations,
  setLocationAutoReply,
  getAutoReplyLogs,
  type AutoReplyLocation,
  type AutoReplyLogEntry,
} from '@/lib/api/reply-templates'
import { resolveTemplateVariables } from '@/lib/utils/template-utils'
import { Plus, Edit2, Trash2, Save, X, Star, Sparkles } from 'lucide-react'

const AUTO_REPLY_MODES: { key: AutoReplyMode; label: string; blurb: string; meta: string }[] = [
  {
    key: 'template',
    label: 'From my templates',
    blurb: 'Posts one of your saved 4★/5★ templates, rotating the least-used one.',
    meta: 'Free · 4–5★ · new reviews only',
  },
  {
    key: 'ai',
    label: 'Written by AI',
    blurb: 'Writes a fresh reply for each review, and works through your older unanswered ones too.',
    meta: '1 AI credit per reply · 3–5★ · 10–20 older reviews a day, spread out',
  },
]

// Placeholder UI components for standard shadcn patterns since we don't have
// direct access to the actual UI components library in this environment, we'll
// build tailwind equivalents or use standard HTML elements styled nicely.
// In a real shadcn environment, we'd import Tabs, Dialog, AlertDialog, Button, etc.

export default function ReplyTemplatesSettingsPage() {
  const { user } = useAuth()
  const userRole = user?.role || 'Viewer'

  const [templates, setTemplates] = useState<ReplyTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [errorAlert, setErrorAlert] = useState('')
  const [successAlert, setSuccessAlert] = useState('')
  
  // Tab state
  const [activeStar, setActiveStar] = useState<number>(5)

  // Dialog state
  const [isDialogOpen, setIsDialogOpen] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [editingTemplate, setEditingTemplate] = useState<ReplyTemplate | null>(null)
  
  // Form state
  const [formTitle, setFormTitle] = useState('')
  const [formBody, setFormBody] = useState('')
  const [formDisplayOrder, setFormDisplayOrder] = useState(0)
  
  // Delete dialog state
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false)
  const [templateToDelete, setTemplateToDelete] = useState<ReplyTemplate | null>(null)

  // Auto-reply (org-wide) state
  const [autoReplyEnabledAt, setAutoReplyEnabledAt] = useState<string | null>(null)
  const [autoReplyBusy, setAutoReplyBusy] = useState(false)
  const [autoReplyMode, setAutoReplyMode] = useState<AutoReplyMode>('template')
  const [aiCredits, setAiCredits] = useState<number | null>(null)

  // Analytics
  const [lastUsed, setLastUsed] = useState<Record<string, string>>({})
  const [autoReplies30d, setAutoReplies30d] = useState(0)

  // Per-location auto-reply + run log
  const [arLocations, setArLocations] = useState<AutoReplyLocation[]>([])
  const [arLogs, setArLogs] = useState<AutoReplyLogEntry[]>([])
  const [showLogs, setShowLogs] = useState(false)

  useEffect(() => {
    if (['Owner', 'Admin'].includes(userRole)) {
      loadTemplates()
    } else {
      setLoading(false)
    }
  }, [userRole])

  const loadTemplates = async () => {
    setLoading(true)
    setErrorAlert('')
    try {
      const data = await fetchTemplates()
      setTemplates(data)
    } catch (e: any) {
      console.error(e)
      setErrorAlert(e.message || 'Failed to load templates.')
    } finally {
      setLoading(false)
    }
    try {
      const status = await getAutoReplyStatus()
      setAutoReplyEnabledAt(status.enabled_at)
      setAutoReplyMode(status.mode ?? 'template')
      setAiCredits(status.ai_credits ?? null)
    } catch (e: any) {
      console.error('Failed to load auto-reply status', e)
    }
    try {
      const analytics = await getTemplateAnalytics()
      setLastUsed(analytics.last_used)
      setAutoReplies30d(analytics.auto_replies_30d)
    } catch (e: any) {
      console.error('Failed to load template analytics', e)
    }
    try {
      setArLocations(await getAutoReplyLocations())
    } catch (e: any) {
      console.error('Failed to load auto-reply locations', e)
    }
  }

  const loadLogs = async () => {
    try {
      setArLogs(await getAutoReplyLogs())
    } catch (e: any) {
      console.error('Failed to load auto-reply logs', e)
    }
  }

  const handleToggleLocation = async (loc: AutoReplyLocation) => {
    // Optimistic: a checkbox that waits for a round-trip reads as broken.
    setArLocations(prev => prev.map(l => (l.id === loc.id ? { ...l, enabled: !l.enabled } : l)))
    try {
      await setLocationAutoReply(loc.id, !loc.enabled)
    } catch (e: any) {
      setArLocations(prev => prev.map(l => (l.id === loc.id ? { ...l, enabled: loc.enabled } : l)))
      setErrorAlert(e.message || 'Failed to update this location.')
    }
  }

  // `enabled` is always explicit. It used to be derived (turningOn = !enabledAt || mode
  // !== autoReplyMode), which meant clicking the ALREADY-ACTIVE mode card silently
  // disabled auto-reply — the org kept auto_reply_mode='ai' with enabled_at NULL and
  // answered nothing.
  const handleSetAutoReply = async (enabled: boolean, mode: AutoReplyMode = autoReplyMode) => {
    const turningOn = enabled
    setAutoReplyBusy(true)
    setErrorAlert('')
    setSuccessAlert('')
    try {
      const res = await setAutoReply(turningOn, mode)
      setAutoReplyEnabledAt(turningOn ? (res.enabled_at ?? new Date().toISOString()) : null)
      if (turningOn) setAutoReplyMode(mode)
      setSuccessAlert(
        !turningOn ? 'Auto-reply disabled.'
          : mode === 'ai'
            ? 'AI auto-reply enabled for 3–5★. New reviews are answered on each sync; 10–20 older reviews are answered per location per day.'
            : 'Auto-reply enabled for new 4–5★ reviews.')
    } catch (e: any) {
      setErrorAlert(e.message || 'Failed to update auto-reply.')
    } finally {
      setAutoReplyBusy(false)
    }
  }

  if (!['Owner', 'Admin'].includes(userRole)) {
    return (
      <div className="p-8 max-w-4xl mx-auto">
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-6 text-center">
          <h2 className="text-xl font-bold text-red-500 mb-2">Access Denied</h2>
          <p className="text-muted-foreground">You do not have permission to view or manage Reply Templates. Only Owners and Admins can access this page.</p>
        </div>
      </div>
    )
  }

  // Group templates client-side
  const templatesByStar: Record<number, ReplyTemplate[]> = { 1: [], 2: [], 3: [], 4: [], 5: [] }
  templates.forEach(t => {
    if (templatesByStar[t.star_rating]) {
      templatesByStar[t.star_rating].push(t)
    }
  })
  // Keep each group ordered by display_order (then id) so newly created/edited
  // templates land in the right position without needing a full reload.
  Object.values(templatesByStar).forEach(group =>
    group.sort((a, b) => a.display_order - b.display_order || a.id - b.id)
  )

  const currentCount = templatesByStar[activeStar]?.length || 0
  const limit = STAR_RATING_LIMITS[activeStar] || 0
  const canAdd = currentCount < limit

  const positiveTemplateCount = templatesByStar[4].length + templatesByStar[5].length
  const canEnableAutoReply = autoReplyMode === 'ai' || positiveTemplateCount >= MIN_TEMPLATES_FOR_AUTO_REPLY
  // Template mode fires for 4★ and 5★ (AI mode also takes 3★, which needs no template);
  // a rating with no template is silently skipped.
  const missingPositiveRatings = [4, 5].filter(r => templatesByStar[r].length === 0)

  const openAddDialog = () => {
    setEditingTemplate(null)
    setFormTitle('')
    setFormBody('')
    setFormDisplayOrder(0)
    setIsDialogOpen(true)
    setErrorAlert('')
  }

  const openEditDialog = (template: ReplyTemplate) => {
    setEditingTemplate(template)
    setFormTitle(template.title)
    setFormBody(template.body)
    setFormDisplayOrder(template.display_order)
    setIsDialogOpen(true)
    setErrorAlert('')
  }

  const openDeleteDialog = (template: ReplyTemplate) => {
    setTemplateToDelete(template)
    setIsDeleteDialogOpen(true)
  }

  const handleSave = async () => {
    if (!formTitle.trim() || !formBody.trim()) {
      setErrorAlert('Title and Body are required.')
      return
    }
    
    setIsSaving(true)
    setErrorAlert('')
    setSuccessAlert('')
    
    try {
      if (editingTemplate) {
        const payload: UpdateTemplatePayload = {
          title: formTitle.trim(),
          body: formBody.trim(),
          display_order: formDisplayOrder
        }
        const updated = await updateTemplate(editingTemplate.id, payload)
        setTemplates(templates.map(t => t.id === updated.id ? updated : t))
        setSuccessAlert('Template updated successfully.')
      } else {
        const payload: CreateTemplatePayload = {
          star_rating: activeStar,
          title: formTitle.trim(),
          body: formBody.trim(),
          display_order: formDisplayOrder
        }
        const created = await createTemplate(payload)
        setTemplates([...templates, created])
        setSuccessAlert('Template created successfully.')
      }
      setIsDialogOpen(false)
    } catch (e: any) {
      console.error(e)
      setErrorAlert(e.message || 'Failed to save template.')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!templateToDelete) return
    setErrorAlert('')
    try {
      const res = await deleteTemplate(templateToDelete.id)
      setTemplates(templates.filter(t => t.id !== templateToDelete.id))
      setIsDeleteDialogOpen(false)
      setTemplateToDelete(null)
      if (res?.auto_reply_disabled) {
        setAutoReplyEnabledAt(null)
        setSuccessAlert('Template deleted. Auto-reply was turned off — it needs at least ' + MIN_TEMPLATES_FOR_AUTO_REPLY + ' templates for 4★/5★ reviews.')
      } else {
        setSuccessAlert('Template deleted successfully.')
      }
    } catch (e: any) {
      console.error(e)
      setErrorAlert(e.message || 'Failed to delete template.')
    }
  }

  return (
    <div className="p-6 md:p-8 max-w-5xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Reply Templates</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Pre-written replies for each star rating. Insert variables like <code className="bg-muted px-1.5 py-0.5 rounded text-primary text-xs">{'{'}{'{'}first_name{'}'}{'}'}</code>, <code className="bg-muted px-1.5 py-0.5 rounded text-primary text-xs">{'{'}{'{'}city{'}'}{'}'}</code> and more from the editor.
          </p>
        </div>
      </div>

      {/* Org-wide Auto-Reply */}
      {!loading && (
        <div className="border border-border rounded-xl overflow-hidden">
          {/* Header: what it does + on/off */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 border-b border-border bg-muted/30">
            <div className="flex items-start gap-2.5">
              <Sparkles className="w-4 h-4 mt-0.5 text-primary shrink-0" />
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-foreground text-sm">Auto-reply</span>
                  <span className={`text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                    autoReplyEnabledAt ? 'bg-green-500/15 text-green-600' : 'bg-muted text-muted-foreground'
                  }`}>
                    {autoReplyEnabledAt ? 'On' : 'Off'}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Answers{' '}
                  <span className="font-medium text-foreground">
                    {autoReplyMode === 'ai' ? '3★, 4★ and 5★' : '4★ and 5★'}
                  </span>{' '}
                  reviews across all locations.{' '}
                  {autoReplyMode === 'ai' ? '1–2★' : '1–3★'} always wait for you. Replies are public and can’t be unsent.
                </p>
              </div>
            </div>
            <button
              onClick={() => handleSetAutoReply(!autoReplyEnabledAt)}
              disabled={autoReplyBusy || (!autoReplyEnabledAt && !canEnableAutoReply)}
              className={`w-full sm:w-auto shrink-0 min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed ${
                autoReplyEnabledAt
                  ? 'bg-background border border-border text-foreground hover:bg-muted'
                  : 'text-primary-foreground bg-primary hover:bg-primary/90'
              }`}
            >
              {autoReplyBusy ? 'Saving…' : autoReplyEnabledAt ? 'Turn Off' : 'Turn On'}
            </button>
          </div>

          {/* Mode: pick where the reply text comes from */}
          <div className="p-4 grid sm:grid-cols-2 gap-3">
            {AUTO_REPLY_MODES.map(({ key, label, blurb, meta }) => {
              const active = autoReplyMode === key
              return (
                <button
                  key={key}
                  onClick={() => {
                    if (!autoReplyEnabledAt) return setAutoReplyMode(key)
                    if (key !== autoReplyMode) handleSetAutoReply(true, key)  // active card: no-op
                  }}
                  disabled={autoReplyBusy}
                  aria-pressed={active}
                  className={`text-left p-3 rounded-lg border transition-colors disabled:opacity-50 ${
                    active ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-3.5 h-3.5 rounded-full border-[4px] shrink-0 ${
                      active ? 'border-primary bg-background' : 'border-muted-foreground/30 bg-background'
                    }`} />
                    <span className="text-sm font-semibold text-foreground">{label}</span>
                    {active && autoReplyEnabledAt && (
                      <span className="text-[10px] font-bold uppercase tracking-wider text-primary">Active</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground mt-1.5">{blurb}</p>
                  <p className="text-[11px] text-muted-foreground/80 mt-1.5 font-medium">{meta}</p>
                </button>
              )
            })}
          </div>

          {/* Status / warnings */}
          {(autoReplyEnabledAt || !canEnableAutoReply || missingPositiveRatings.length > 0) && (
            <div className="px-4 pb-4 -mt-1 space-y-1 text-xs">
              {autoReplyMode === 'template' && !canEnableAutoReply && !autoReplyEnabledAt && (
                <p className="text-amber-500">
                  Add at least {MIN_TEMPLATES_FOR_AUTO_REPLY} templates for 4★/5★ reviews to turn this on ({positiveTemplateCount} so far).
                </p>
              )}
              {autoReplyEnabledAt && autoReplyMode === 'template' && missingPositiveRatings.map(r => (
                <p key={r} className="text-amber-500">
                  No {r}★ template — {r}★ reviews won’t be auto-answered.
                </p>
              ))}
              {autoReplyMode === 'ai' && aiCredits !== null && aiCredits < 20 && (
                <p className="text-amber-500">
                  {aiCredits === 0
                    ? 'No AI credits left — AI auto-reply is on but can’t post until you top up.'
                    : `Only ${aiCredits} AI credits left (1 per reply, up to 20 a day per location).`}
                </p>
              )}
              {autoReplyEnabledAt && (
                <p className="text-muted-foreground">
                  <span className="font-semibold text-green-600">{autoReplies30d}</span> auto-
                  {autoReplies30d === 1 ? 'reply' : 'replies'} in the last 30 days.
                </p>
              )}
            </div>
          )}

          {/* Which locations it runs on + proof that it ran */}
          {arLocations.length > 0 && (
            <div className="border-t border-border">
              <div className="px-4 py-2.5 flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-foreground">Locations</span>
                <button
                  onClick={() => { setShowLogs(v => !v); if (!showLogs) loadLogs() }}
                  className="text-xs font-medium text-primary hover:underline"
                >
                  {showLogs ? 'Hide activity log' : 'View activity log'}
                </button>
              </div>
              <div className="divide-y divide-border">
                {arLocations.map(loc => (
                  <label
                    key={loc.id}
                    className="flex items-center justify-between gap-3 px-4 py-2.5 cursor-pointer hover:bg-muted/40"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm text-foreground truncate">{loc.location_name}</span>
                      <span className="block text-[11px] text-muted-foreground">
                        {loc.city ? loc.city + ' · ' : ''}
                        {loc.replies_30d} replied in 30 days · {loc.waiting} waiting
                        {loc.last_run_at ? ' · last run ' + new Date(loc.last_run_at).toLocaleString() : ' · no runs in 30 days'}
                      </span>
                    </span>
                    <input
                      type="checkbox"
                      checked={loc.enabled}
                      onChange={() => handleToggleLocation(loc)}
                      className="w-4 h-4 shrink-0 accent-primary"
                      aria-label={'Auto-reply for ' + loc.location_name}
                    />
                  </label>
                ))}
              </div>

              {showLogs && (
                <div className="px-4 py-3 border-t border-border bg-muted/20 max-h-72 overflow-y-auto space-y-1.5">
                  {arLogs.length === 0 ? (
                    <p className="text-xs text-muted-foreground">
                      Nothing yet. Runs appear here once auto-reply posts a reply or hits a problem.
                    </p>
                  ) : arLogs.map(l => (
                    <p key={l.id} className="text-[11px] text-muted-foreground font-mono">
                      {new Date(l.created_at).toLocaleString()} · {l.location_name || '—'} ·{' '}
                      {l.action === 'review_auto_replied'
                        ? <>
                            replied to{' '}
                            <Link href={`/dashboard/reviews?review=${l.review_id}`}
                                  className="text-primary hover:underline">
                              review #{l.review_id}
                            </Link>
                            {' (' + (l.payload.source || 'template') + ')'}
                          </>
                        : l.payload.status === 'completed'
                          ? 'run: ' + l.payload.replied + ' replied, ' + l.payload.failed + ' failed, '
                            + l.payload.needs_human + ' left for you'
                            // An LLM outage or a bad API key stops the run early. Without
                            // this the row reads "0 replied" and looks like idleness.
                            + (l.payload.stopped ? ' — STOPPED: ' + l.payload.stopped : '')
                          : 'run skipped: ' + l.payload.reason}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {errorAlert && !isDialogOpen && (
        <div className="p-4 bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg text-sm">
          {errorAlert}
        </div>
      )}
      
      {successAlert && !isDialogOpen && (
        <div className="p-4 bg-green-500/10 border border-green-500/20 text-green-500 rounded-lg text-sm">
          {successAlert}
        </div>
      )}

      {loading ? (
        <div className="flex justify-center p-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Tabs */}
          <div className="flex overflow-x-auto border-b border-border hide-scrollbar">
            {[5, 4, 3, 2, 1].map(star => (
              <button
                key={star}
                onClick={() => setActiveStar(star)}
                className={`flex items-center gap-2 px-4 py-3 border-b-2 text-sm font-medium whitespace-nowrap transition-colors ${
                  activeStar === star 
                    ? 'border-primary text-primary' 
                    : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted'
                }`}
              >
                <span className="flex items-center">
                  {star} <Star className="h-3.5 w-3.5 ml-1 fill-amber-400 text-amber-400" />
                </span>
                <span className="bg-muted/50 text-muted-foreground px-2 py-0.5 rounded-full text-xs">
                  {templatesByStar[star]?.length || 0} / {STAR_RATING_LIMITS[star]}
                </span>
              </button>
            ))}
          </div>

          {/* Tab Content */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                {activeStar}-Star Templates
              </h3>
              
              <button
                onClick={openAddDialog}
                disabled={!canAdd}
                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title={!canAdd ? `Maximum ${limit} templates reached for this rating` : ''}
              >
                <Plus className="h-4 w-4" />
                Add Template
              </button>
            </div>

            {templatesByStar[activeStar]?.length === 0 ? (
              <div className="text-center py-12 bg-muted/20 border border-dashed border-border rounded-xl">
                <p className="text-muted-foreground">No templates configured for {activeStar} stars.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {templatesByStar[activeStar]?.map(template => (
                  <div key={template.id} className="group relative p-5 bg-card border border-border rounded-xl hover:border-primary/30 transition-colors shadow-sm">
                    <div className="absolute top-3 right-3 flex gap-2 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => openEditDialog(template)}
                        className="p-2 sm:p-1.5 text-muted-foreground hover:text-primary bg-background rounded border border-border shadow-sm"
                        title="Edit Template"
                        aria-label="Edit template"
                      >
                        <Edit2 className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
                      </button>
                      <button
                        onClick={() => openDeleteDialog(template)}
                        className="p-2 sm:p-1.5 text-muted-foreground hover:text-red-500 bg-background rounded border border-border shadow-sm"
                        title="Delete Template"
                        aria-label="Delete template"
                      >
                        <Trash2 className="h-4 w-4 sm:h-3.5 sm:w-3.5" />
                      </button>
                    </div>
                    
                    <h4 className="font-semibold text-foreground pr-16">{template.title}</h4>
                    <p className="text-sm text-muted-foreground mt-2 line-clamp-2">{template.body}</p>
                    
                    <div className="flex items-center gap-4 mt-4 text-xs text-muted-foreground">
                      <span>Order: {template.display_order}</span>
                      <span>Used: {template.usage_count} times</span>
                      {lastUsed[String(template.id)] && (
                        <span>Last used: {new Date(lastUsed[String(template.id)]).toLocaleDateString()}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add/Edit Dialog */}
      {isDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 sm:backdrop-blur-sm">
          <div className="bg-card w-full sm:max-w-lg border border-border rounded-t-2xl sm:rounded-xl shadow-lg overflow-hidden flex flex-col max-h-[92vh] sm:max-h-[90vh]">
            <div className="px-6 py-4 border-b border-border flex justify-between items-center">
              <h2 className="text-lg font-semibold">{editingTemplate ? 'Edit Template' : 'Add Template'}</h2>
              <button onClick={() => setIsDialogOpen(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto flex-1 space-y-4">
              {errorAlert && (
                <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 rounded-lg text-sm">
                  {errorAlert}
                </div>
              )}
              
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Title <span className="text-red-500">*</span></label>
                <input 
                  type="text" 
                  value={formTitle}
                  onChange={e => setFormTitle(e.target.value)}
                  maxLength={100}
                  placeholder="e.g. Apology - Service Issue"
                  className="w-full px-3 py-2 bg-background border border-input rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Body <span className="text-red-500">*</span></label>
                <textarea
                  value={formBody}
                  onChange={e => setFormBody(e.target.value)}
                  rows={4}
                  maxLength={3500}
                  placeholder="Thank you for visiting {{location_name}}, {{reviewer_name}}..."
                  className="w-full px-3 py-2 bg-background border border-input rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">Insert:</span>
                  {INSERTABLE_VARIABLES.map(v => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setFormBody(prev => `${prev}{{${v}}}`)}
                      className="px-2 py-0.5 rounded-full border border-primary/20 bg-primary/5 hover:bg-primary/10 text-primary text-xs font-mono transition-colors"
                    >
                      {`{{${v}}}`}
                    </button>
                  ))}
                </div>
              </div>
              
              <div className="space-y-2">
                <label className="text-sm font-medium text-foreground">Display Order</label>
                <input 
                  type="number" 
                  min="0"
                  value={formDisplayOrder}
                  onChange={e => setFormDisplayOrder(parseInt(e.target.value) || 0)}
                  className="w-full px-3 py-2 bg-background border border-input rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary/50"
                />
              </div>

              {/* Live Preview */}
              <div className="pt-4 mt-4 border-t border-border">
                <h4 className="text-sm font-medium text-muted-foreground mb-2">Live Preview</h4>
                <div className="p-4 bg-muted/30 border border-border rounded-lg text-sm text-foreground whitespace-pre-wrap min-h-[80px]">
                  {formBody.trim() ? resolveTemplateVariables(formBody, "John", "Your Location", { city: "Mumbai", phone: "+91 98765 43210", website: "example.com", rating: String(activeStar) }) : <span className="text-muted-foreground italic">Start typing to see preview...</span>}
                </div>
              </div>
            </div>
            
            <div className="px-6 py-4 border-t border-border bg-muted/10 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
              <button
                onClick={() => setIsDialogOpen(false)}
                className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 border border-border bg-background hover:bg-muted text-foreground text-sm font-medium rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving || !formTitle.trim() || !formBody.trim()}
                className="w-full sm:w-auto min-h-[44px] sm:min-h-0 flex items-center justify-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-md hover:bg-primary/90 disabled:opacity-50 transition-colors"
              >
                {isSaving ? (
                  <div className="h-4 w-4 border-2 border-primary-foreground border-t-transparent rounded-full animate-spin"></div>
                ) : (
                  <Save className="h-4 w-4" />
                )}
                {editingTemplate ? 'Save Changes' : 'Create Template'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {isDeleteDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 sm:backdrop-blur-sm">
          <div className="bg-card w-full sm:max-w-sm border border-border rounded-t-2xl sm:rounded-xl shadow-lg p-6 space-y-6">
            <div>
              <h3 className="text-lg font-semibold text-foreground">Delete template?</h3>
              <p className="text-sm text-muted-foreground mt-2">
                Are you sure you want to delete &quot;{templateToDelete?.title}&quot;? This action cannot be undone.
              </p>
            </div>

            <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
              <button
                onClick={() => setIsDeleteDialogOpen(false)}
                className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 border border-border bg-background hover:bg-muted text-foreground text-sm font-medium rounded-md transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-md hover:bg-red-700 transition-colors"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
