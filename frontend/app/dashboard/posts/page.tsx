'use client'

import { useEffect, useState, useRef } from 'react'
import { api } from '@/lib/api'
import {
  Sparkles,
  Plus,
  FileText,
  History,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Search,
  Upload,
  Send,
  Loader2,
  X,
  Lock,
  ChevronLeft,
  ChevronRight,
  RotateCw,
} from 'lucide-react'

interface Location {
  id: number
  location_name: string
  primary_category?: string
  address?: string
  phone?: string
  billing_status?: string  // 'active' | 'pending_payment' (locked, can't publish)
}

interface CampaignJob {
  id: number
  location_id: number
  status: string
  retry_count?: number
  last_error?: string | null
  google_post_id?: string | null
}

interface CampaignAuditLog {
  id: number
  action: string
  previous_status?: string | null
  new_status: string
  created_at: string
}

interface CampaignPrimaryPost {
  id: number
  title?: string | null
  summary?: string | null
  cta_type?: string | null
  cta_url?: string | null
  scheduled_at?: string | null
}

interface Campaign {
  id: number
  name: string
  status: string
  total_locations: number
  total_pending: number
  total_published: number
  total_failed: number
  scheduled_at?: string | null
  created_at: string
  jobs?: CampaignJob[]
  audit_logs?: CampaignAuditLog[]
  primary_post?: CampaignPrimaryPost | null
}

const CTA_LABELS: Record<string, string> = {
  LEARN_MORE: 'Learn More',
  BOOK: 'Book',
  ORDER: 'Order',
  SHOP: 'Shop',
  SIGN_UP: 'Sign Up',
  CALL: 'Call',
}

const SUMMARY_MAX = 1500
const TITLE_MAX = 100

// Relative time — handles both past ("3h ago") and future ("in 2h").
function relativeTime(dateStr?: string | null): string {
  if (!dateStr) return ''
  const diffMs = Date.now() - new Date(dateStr).getTime()
  const absMins = Math.floor(Math.abs(diffMs) / 60000)
  const future = diffMs < 0
  if (absMins < 1) return 'just now'
  if (absMins < 60) return future ? `in ${absMins}m` : `${absMins}m ago`
  const hrs = Math.floor(absMins / 60)
  if (hrs < 24) return future ? `in ${hrs}h` : `${hrs}h ago`
  const days = Math.floor(hrs / 24)
  return future ? `in ${days}d` : `${days}d ago`
}

// Today's date as YYYY-MM-DD in the user's *local* timezone. Using toISOString()
// here would yield the UTC date, which can be a day off from the local date the
// <input type="time"> comparison uses — letting through (or wrongly blocking) values.
function localToday(): string {
  const d = new Date()
  const tzOffsetMs = d.getTimezoneOffset() * 60000
  return new Date(d.getTime() - tzOffsetMs).toISOString().split('T')[0]
}

// Split an ISO datetime into local <input type="date"> / <input type="time"> values.
function isoToLocalParts(iso?: string | null): { date: string; time: string } {
  if (!iso) return { date: '', time: '' }
  const d = new Date(iso)
  if (isNaN(d.getTime())) return { date: '', time: '' }
  const pad = (n: number) => String(n).padStart(2, '0')
  return {
    date: `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`,
    time: `${pad(d.getHours())}:${pad(d.getMinutes())}`,
  }
}

// Format a datetime string to a readable local date+time like "Jun 18, 2:30 PM".
function formatScheduled(dateStr?: string | null): string {
  if (!dateStr) return ''
  return new Date(dateStr).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'
  })
}

// Campaign-level badge — full status coverage with readable contrast on white.
function CampaignBadge({ status }: { status: string }) {
  const s = (status || '').toUpperCase().replace(/[_\s]/g, '')
  const base = 'px-2 py-0.5 rounded text-[10px] font-bold border'
  switch (s) {
    case 'DRAFT':
      return <span className={`${base} bg-zinc-100 text-zinc-700 border-zinc-300 dark:bg-zinc-500/15 dark:text-zinc-300 dark:border-zinc-500/30`}>Draft</span>
    case 'QUEUED':
      return <span className={`${base} bg-sky-100 text-sky-700 border-sky-300 dark:bg-sky-500/15 dark:text-sky-300 dark:border-sky-500/30`}>Queued</span>
    case 'SCHEDULED':
      return <span className={`${base} bg-purple-100 text-purple-700 border-purple-300 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30`}>Scheduled</span>
    case 'PROCESSING':
    case 'RUNNING':
      return <span className={`${base} bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30 animate-pulse`}>Running</span>
    case 'PAUSED':
      return <span className={`${base} bg-orange-100 text-orange-700 border-orange-300 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-500/30`}>Paused</span>
    case 'COMPLETED':
      return <span className={`${base} bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30`}>Completed</span>
    case 'PARTIALLYCOMPLETED':
      return <span className={`${base} bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30`}>Partial</span>
    case 'FAILED':
      return <span className={`${base} bg-red-100 text-red-800 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30`}>Failed</span>
    case 'CANCELLED':
      return <span className={`${base} bg-zinc-100 text-zinc-600 border-zinc-300 dark:bg-zinc-500/15 dark:text-zinc-400 dark:border-zinc-500/30`}>Cancelled</span>
    default:
      return <span className={`${base} bg-zinc-100 text-zinc-700 border-zinc-300`}>{status}</span>
  }
}

// Per-location job badge.
function JobBadge({ status }: { status: string }) {
  const s = (status || '').toUpperCase()
  const base = 'inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border'
  switch (s) {
    case 'SUCCESS':
    case 'PUBLISHED':
      return <span className={`${base} bg-emerald-100 text-emerald-800 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30`}>Published</span>
    case 'RUNNING':
      return <span className={`${base} bg-amber-100 text-amber-800 border-amber-300 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30 animate-pulse`}>Running</span>
    case 'RETRYING':
      return <span className={`${base} bg-orange-100 text-orange-700 border-orange-300 dark:bg-orange-500/15 dark:text-orange-300 dark:border-orange-500/30`}>Retrying</span>
    case 'FAILED':
      return <span className={`${base} bg-red-100 text-red-800 border-red-300 dark:bg-red-500/15 dark:text-red-300 dark:border-red-500/30`}>Failed</span>
    default:
      return <span className={`${base} bg-zinc-100 text-zinc-600 border-zinc-300 dark:bg-zinc-500/15 dark:text-zinc-400 dark:border-zinc-500/30`}>Pending</span>
  }
}

export default function PostsPage(props: any) {
  const locationId = props.locationId;
  const [locations, setLocations] = useState<Location[]>([])
  const [campaigns, setCampaigns] = useState<Campaign[]>([])
  const [loadError, setLoadError] = useState('')

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [step, setStep] = useState(1) // 1 Content · 2 Media · 3 Locations
  const [campaignName, setCampaignName] = useState('')
  const [title, setTitle] = useState('')
  const [summary, setSummary] = useState('')
  const [ctaType, setCtaType] = useState('NONE')
  const [ctaUrl, setCtaUrl] = useState('')
  const [locationSearch, setLocationSearch] = useState('')
  const [selectedLocationIds, setSelectedLocationIds] = useState<number[]>(locationId ? [locationId] : [])
  const [publishMode, setPublishMode] = useState<'NOW' | 'SCHEDULED'>('NOW')
  const [scheduledDate, setScheduledDate] = useState('')
  const [scheduledTime, setScheduledTime] = useState('')

  // Media
  const [uploading, setUploading] = useState(false)
  const [mediaUrl, setMediaUrl] = useState('')
  const [mediaPayload, setMediaPayload] = useState<any>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Guard refs
  const isMounted = useRef(true)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Submitting / feedback
  const [submitting, setSubmitting] = useState(false)
  const [errorAlert, setErrorAlert] = useState('')
  const [successAlert, setSuccessAlert] = useState('')

  // Selected Campaign + monitor
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null)
  const [pollingActive, setPollingActive] = useState(false)
  const [pollNonce, setPollNonce] = useState(0)
  const [jobSearch, setJobSearch] = useState('')
  const [retryingJobId, setRetryingJobId] = useState<number | null>(null)
  const [retryingAll, setRetryingAll] = useState(false)

  // Edit / reschedule a SCHEDULED campaign before it fires
  const [scheduleModal, setScheduleModal] = useState<null | 'edit' | 'reschedule'>(null)
  const [schedTitle, setSchedTitle] = useState('')
  const [schedSummary, setSchedSummary] = useState('')
  const [schedCta, setSchedCta] = useState('NONE')
  const [schedCtaUrl, setSchedCtaUrl] = useState('')
  const [schedDate, setSchedDate] = useState('')
  const [schedTime, setSchedTime] = useState('')
  const [savingSchedule, setSavingSchedule] = useState(false)

  const getCityFromAddress = (address?: string, name?: string) => {
    if (!address) return name || ''
    const parts = address.split(',').map(p => p.trim())
    for (let i = 0; i < parts.length; i++) {
      if (/\b\d{5}\b/.test(parts[i]) || /\b[A-Z]{2}\s\d{5}\b/.test(parts[i])) {
        if (i > 0) return parts[i - 1]
      }
    }
    if (parts.length >= 3) return parts[parts.length - 3]
    return name || ''
  }

  const getLivePreview = () => {
    if (selectedLocationIds.length === 0) return 'Select a location to see a live preview…'
    const firstLoc = locations.find(l => l.id === selectedLocationIds[0])
    if (!firstLoc) return 'Select a location to see a live preview…'
    const city = getCityFromAddress(firstLoc.address, firstLoc.location_name)
    const phone = firstLoc.phone || ''
    return (summary || 'Your post body will appear here…')
      .replaceAll('{{location}}', firstLoc.location_name)
      .replaceAll('{{city}}', city)
      .replaceAll('{{phone}}', phone)
  }

  // Insert a {{variable}} at the textarea cursor.
  const insertVariable = (variable: string) => {
    const textarea = textareaRef.current
    const token = `{{${variable}}}`
    if (!textarea) {
      setSummary(s => (s + token).slice(0, SUMMARY_MAX))
      return
    }
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const next = (summary.slice(0, start) + token + summary.slice(end)).slice(0, SUMMARY_MAX)
    setSummary(next)
    setTimeout(() => {
      textarea.focus()
      const pos = start + token.length
      textarea.setSelectionRange(pos, pos)
    }, 10)
  }

  const handleCampaignAction = async (action: 'pause' | 'resume' | 'cancel') => {
    if (!selectedCampaignId) return
    try {
      setSuccessAlert('')
      setErrorAlert('')
      const updated: Campaign = await api.post(`/posts/campaigns/${selectedCampaignId}/${action}`)
      setCampaigns(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c))
      setSuccessAlert(`Campaign ${action}d successfully.`)
      setPollNonce(n => n + 1)
    } catch (err: any) {
      setErrorAlert(err.message || `Failed to ${action} campaign.`)
    }
  }

  const handleRetryAll = async () => {
    if (!selectedCampaignId) return
    setRetryingAll(true)
    setErrorAlert('')
    try {
      await api.post(`/posts/campaigns/${selectedCampaignId}/retry-failed`)
      setSuccessAlert('Retrying all failed locations…')
      await loadCampaignProgress()
      setPollNonce(n => n + 1)
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to retry campaign.')
    } finally {
      setRetryingAll(false)
    }
  }

  const handleRetryJob = async (jobId: number) => {
    setRetryingJobId(jobId)
    setErrorAlert('')
    try {
      await api.post(`/posts/jobs/${jobId}/retry`)
      await loadCampaignProgress()
      setPollNonce(n => n + 1)
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to retry location.')
    } finally {
      setRetryingJobId(null)
    }
  }

  const openScheduleModal = (mode: 'edit' | 'reschedule') => {
    const c = campaigns.find(x => x.id === selectedCampaignId)
    const p = c?.primary_post
    const parts = isoToLocalParts(p?.scheduled_at || c?.scheduled_at)
    setSchedTitle(p?.title || '')
    setSchedSummary(p?.summary || '')
    setSchedCta(p?.cta_type || 'NONE')
    setSchedCtaUrl(p?.cta_url || '')
    setSchedDate(parts.date)
    setSchedTime(parts.time)
    setErrorAlert('')
    setSuccessAlert('')
    setScheduleModal(mode)
  }

  const handleSaveSchedule = async () => {
    if (!selectedCampaignId) return
    if (scheduleModal === 'edit' && !schedSummary.trim()) {
      setErrorAlert('Post summary is required.'); return
    }
    if (schedCta !== 'NONE' && schedCta !== 'CALL' && schedCtaUrl && !validateUrl(schedCtaUrl)) {
      setErrorAlert('CTA URL must be a valid http or https URL.'); return
    }
    if (!schedDate || !schedTime) {
      setErrorAlert('Please select both date and time.'); return
    }
    const when = new Date(`${schedDate}T${schedTime}`)
    if (when <= new Date()) {
      setErrorAlert('Scheduled time must be in the future.'); return
    }

    const payload: any = { scheduled_at: when.toISOString() }
    if (scheduleModal === 'edit') {
      payload.title = schedTitle || null
      payload.summary = schedSummary
      payload.cta_type = schedCta !== 'NONE' ? schedCta : null
      payload.cta_url = schedCta !== 'NONE' && schedCta !== 'CALL' && schedCtaUrl ? schedCtaUrl : null
    }

    setSavingSchedule(true)
    setErrorAlert('')
    try {
      const updated: Campaign = await api.patch(`/posts/campaigns/${selectedCampaignId}/schedule`, payload)
      setCampaigns(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c))
      setSuccessAlert(scheduleModal === 'edit' ? 'Scheduled post updated.' : 'Campaign rescheduled.')
      setScheduleModal(null)
      await loadCampaignProgress()
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to update schedule.')
    } finally {
      setSavingSchedule(false)
    }
  }

  const handleCancelSchedule = async () => {
    if (!selectedCampaignId) return
    if (!confirm('Cancel this scheduled publish? The campaign will revert to Draft.')) return
    setErrorAlert('')
    try {
      const updated: Campaign = await api.post(`/posts/campaigns/${selectedCampaignId}/cancel-schedule`)
      setCampaigns(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c))
      setSuccessAlert('Schedule cancelled. Campaign moved to Draft.')
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to cancel schedule.')
    }
  }

  const handleDeleteCampaign = async (id: number) => {
    if (!confirm('Are you sure you want to delete this campaign?')) return
    setErrorAlert('')
    try {
      await api.delete(`/posts/campaigns/${id}`)
      setCampaigns(prev => prev.filter(c => c.id !== id))
      if (selectedCampaignId === id) setSelectedCampaignId(null)
      setSuccessAlert('Campaign deleted successfully.')
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to delete campaign.')
    }
  }

  useEffect(() => {
    isMounted.current = true
    loadLocations()
    loadCampaigns()
    return () => { isMounted.current = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (locationId) setSelectedLocationIds([locationId])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [locationId])

  useEffect(() => {
    if (!selectedCampaignId) {
      setPollingActive(false)
      return
    }
    const terminal = ['COMPLETED', 'FAILED', 'CANCELLED', 'PARTIALLYCOMPLETED']
    const isTerminal = (st?: string) => !!st && terminal.includes(st.toUpperCase().replace(/[_\s]/g, ''))

    loadCampaignProgress()
    const current = campaigns.find(c => c.id === selectedCampaignId)
    if (isTerminal(current?.status)) {
      setPollingActive(false)
      return
    }
    setPollingActive(true)
    const interval = setInterval(async () => {
      // Skip polling while the tab is hidden to avoid wasting API calls.
      if (document.visibilityState === 'hidden') return
      const updated = await loadCampaignProgress()
      if (isTerminal(updated?.status)) {
        clearInterval(interval)
        setPollingActive(false)
      }
    }, 3000)
    return () => { clearInterval(interval); setPollingActive(false) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCampaignId, pollNonce])

  const loadLocations = async () => {
    try {
      const data = await api.get<Location[]>('/locations/')
      setLocations(data)
    } catch (e: any) {
      setLoadError(e.message || 'Failed to load locations.')
    }
  }

  const loadCampaigns = async () => {
    try {
      const url = locationId ? `/posts/campaigns?size=50&location_id=${locationId}` : '/posts/campaigns?size=50'
      const data: any = await api.get(url)
      const allCampaigns = data.campaigns || []
      setCampaigns(allCampaigns)
      if (allCampaigns.length > 0 && !selectedCampaignId) {
        setSelectedCampaignId(allCampaigns[0].id)
      }
    } catch (e: any) {
      setLoadError(e.message || 'Failed to load campaigns.')
    }
  }

  const loadCampaignProgress = async (): Promise<Campaign | undefined> => {
    if (!selectedCampaignId) return
    try {
      const updated: Campaign = await api.get(`/posts/campaigns/${selectedCampaignId}/progress`)
      setCampaigns(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c))
      return updated
    } catch (e) { return undefined }
  }

  const validateUrl = (url: string): boolean => {
    if (!url) return true
    try {
      const parsed = new URL(url)
      return parsed.protocol === 'http:' || parsed.protocol === 'https:'
    } catch {
      return false
    }
  }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return
    const file = files[0]
    // Google Business Profile posts accept images only (JPG/PNG/WEBP).
    if (!file.type.startsWith('image/')) {
      setErrorAlert('Please upload an image (JPG, PNG or WEBP). Google does not accept video in posts.')
      if (fileInputRef.current) fileInputRef.current.value = ''
      return
    }
    setUploading(true)
    setErrorAlert('')
    const formData = new FormData()
    formData.append('file', file)
    try {
      const resMedia: any = await api.post('/media/upload', formData)
      setMediaUrl(resMedia.cdn_url)
      setMediaPayload(resMedia)
    } catch (err: any) {
      setErrorAlert(err.message || 'File upload failed.')
    } finally {
      setUploading(false)
    }
  }

  const handleRemoveMedia = () => {
    setMediaUrl('')
    setMediaPayload(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const handleToggleSelectAll = () => {
    const selectable = filteredLocations.filter(l => l.billing_status !== 'pending_payment')
    if (selectedLocationIds.length === selectable.length && selectable.length > 0) {
      setSelectedLocationIds([])
    } else {
      setSelectedLocationIds(selectable.map(l => l.id))
    }
  }

  const resetForm = () => {
    setStep(1)
    setCampaignName('')
    setTitle('')
    setSummary('')
    setCtaType('NONE')
    setCtaUrl('')
    setMediaUrl('')
    setMediaPayload(null)
    setLocationSearch('')
    setSelectedLocationIds(locationId ? [locationId] : [])
    setPublishMode('NOW')
    setScheduledDate('')
    setScheduledTime('')
  }

  const openModal = () => { resetForm(); setErrorAlert(''); setIsModalOpen(true) }

  const handleCreateCampaign = async () => {
    if (!campaignName || !summary || selectedLocationIds.length === 0) {
      setErrorAlert('Please provide a campaign name, post summary, and select at least one location.')
      return
    }
    if (ctaType !== 'NONE' && ctaType !== 'CALL' && ctaUrl && !validateUrl(ctaUrl)) {
      setErrorAlert('CTA URL must be a valid http or https URL.')
      return
    }
    if (publishMode === 'SCHEDULED') {
      if (!scheduledDate || !scheduledTime) {
        setErrorAlert('Please select both date and time for scheduled publishing.')
        return
      }
      const scheduledDateTime = new Date(`${scheduledDate}T${scheduledTime}`)
      if (scheduledDateTime <= new Date()) {
        setErrorAlert('Scheduled time must be in the future.')
        return
      }
    }
    setSubmitting(true)
    setErrorAlert('')
    setSuccessAlert('')
    try {
      const camp: any = await api.post('/posts/campaigns', {
        name: campaignName,
        total_locations: selectedLocationIds.length
      })
      
      const postPayload: any = {
        title: title || null,
        summary,
        post_type: 'UPDATE',
        cta_type: ctaType !== 'NONE' ? ctaType : null,
        // CALL CTAs use the location phone — never a URL.
        cta_url: ctaType !== 'NONE' && ctaType !== 'CALL' && ctaUrl ? ctaUrl : null,
        is_bulk_post: true,
        campaign_id: camp.id,
        publish_mode: publishMode,
        location_ids: selectedLocationIds
      }
      
      if (publishMode === 'SCHEDULED') {
        postPayload.scheduled_at = new Date(`${scheduledDate}T${scheduledTime}`).toISOString()
      }
      
      const post: any = await api.post('/posts/draft', postPayload)
      if (mediaPayload) {
        await api.post(`/posts/${post.id}/media`, {
          storage_provider: mediaPayload.storage_provider,
          storage_key: mediaPayload.storage_key || null,
          media_type: 'PHOTO',
          original_filename: mediaPayload.original_filename,
          mime_type: mediaPayload.mime_type,
          file_size: mediaPayload.file_size,
          width: mediaPayload.width,
          height: mediaPayload.height,
          sha256_hash: mediaPayload.sha256_hash,
          cdn_url: mediaPayload.cdn_url
        })
      }
      
      if (publishMode === 'NOW') {
        await api.post(`/posts/campaigns/${camp.id}/launch`, { location_ids: selectedLocationIds })
        setSuccessAlert('Campaign launched successfully!')
      } else {
        setSuccessAlert('Campaign scheduled successfully!')
      }
      
      setTimeout(() => {
        if (!isMounted.current) return
        setIsModalOpen(false)
        resetForm()
        loadCampaigns()
        setSelectedCampaignId(camp.id)
        setPollNonce(n => n + 1)
      }, 800)
    } catch (e: any) {
      console.error('Campaign creation error:', e)
      setErrorAlert(e.message || 'Failed to launch campaign.')
    } finally {
      setSubmitting(false)
    }
  }

  const filteredLocations = locations.filter(l => l.location_name.toLowerCase().includes(locationSearch.toLowerCase()))
  const selectedCampaign = campaigns.find(c => c.id === selectedCampaignId)
  const mediaReady = mediaPayload?.is_ready === true

  // Step gating
  const canLeaveStep1 = !!campaignName.trim() && !!summary.trim() && (ctaType === 'NONE' || ctaType === 'CALL' || !ctaUrl || validateUrl(ctaUrl))
  const canLaunch = canLeaveStep1 && selectedLocationIds.length > 0
  const lastStep = locationId ? 2 : 3 // single-location mode collapses the targeting step

  const pct = (n: number, d: number) => Math.round((n / (d || 1)) * 100)

  return (
    <div className={locationId ? "" : "min-h-screen bg-background text-foreground"}>
      <main className={locationId ? "" : "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8"}>

        {!locationId && (
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-center bg-card shadow-sm border border-border p-4 sm:p-6 rounded-2xl relative overflow-hidden">
            <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full bg-primary/5 blur-2xl"></div>
            <div>
              <h2 className="text-2xl sm:text-3xl font-bold flex items-center gap-2 text-foreground">
                <Sparkles className="h-6 w-6 text-primary" />
                Campaign Orchestrator
              </h2>
              <p className="text-muted-foreground text-sm mt-1">Manage bulk publishing campaigns across thousands of locations.</p>
            </div>
            <button onClick={openModal} className="shrink-0 bg-primary hover:bg-primary/90 px-4 py-2 rounded-lg font-bold text-sm text-primary-foreground flex items-center justify-center gap-2 transition-colors cursor-pointer">
              <Plus className="h-4 w-4" /> New Campaign
            </button>
          </div>
        )}

        {locationId && (
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-xl font-bold flex items-center gap-2 text-foreground">
              <FileText className="h-5 w-5 text-primary" />
              Location Posts
            </h2>
            <button onClick={openModal} className="bg-primary hover:bg-primary/90 px-4 py-2 rounded-lg font-bold text-sm text-primary-foreground flex items-center gap-2 transition-colors cursor-pointer">
              <Plus className="h-4 w-4" /> New Post
            </button>
          </div>
        )}

        {loadError && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm font-medium rounded-lg">
            <AlertTriangle className="h-4 w-4 shrink-0" /> {loadError}
          </div>
        )}
        {successAlert && (
          <div className="flex items-center gap-2 p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-sm font-medium rounded-lg">
            <CheckCircle2 className="h-4 w-4 shrink-0" /> {successAlert}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Campaign list — richer scannable cards */}
          <div className="lg:col-span-1 bg-card shadow-sm border border-border rounded-2xl p-5 h-fit">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold uppercase text-muted-foreground flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary" /> Campaigns
              </h3>
              <button onClick={loadCampaigns} title="Refresh campaigns" className="p-1 text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
                <RotateCw className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
              {campaigns.length === 0 ? (
                <div className="text-center py-8">
                  <FileText className="h-8 w-8 text-muted-foreground/30 mx-auto mb-2" />
                  <p className="text-xs text-muted-foreground">No campaigns yet. Create one to start publishing.</p>
                </div>
              ) : (
                campaigns.map(c => {
                  const published = c.total_published ?? 0
                  const failed = c.total_failed ?? 0
                  return (
                    <button
                      key={c.id}
                      onClick={() => setSelectedCampaignId(c.id)}
                      className={`w-full text-left p-4 rounded-xl border transition-all cursor-pointer ${selectedCampaignId === c.id ? 'bg-primary/5 border-primary/40 ring-1 ring-primary/20' : 'bg-background border-border/50 hover:bg-muted/30 hover:border-border text-foreground'}`}
                    >
                      <div className="flex justify-between items-start gap-2 mb-2">
                        <span className="font-bold truncate text-sm">{c.name}</span>
                        <CampaignBadge status={c.status} />
                      </div>
                      <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden mb-2">
                        <div className="h-full bg-primary transition-all" style={{ width: `${pct(published, c.total_locations)}%` }} />
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                        <span className="flex items-center gap-2">
                          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">{published} sent</span>
                          {failed > 0 && <span className="text-red-600 dark:text-red-400 font-semibold">{failed} failed</span>}
                          <span>· {c.total_locations} loc</span>
                        </span>
                        {c.status.toUpperCase() === 'SCHEDULED' && c.scheduled_at ? (
                          <span className="text-purple-600 dark:text-purple-400 font-semibold" title={formatScheduled(c.scheduled_at)}>
                            {relativeTime(c.scheduled_at)}
                          </span>
                        ) : (
                          <span>{relativeTime(c.created_at)}</span>
                        )}
                      </div>
                    </button>
                  )
                })
              )}
            </div>
          </div>

          {/* Monitor */}
          <div className="lg:col-span-2 space-y-6">
            {selectedCampaign ? (
              <div className="bg-card shadow-sm border border-border rounded-2xl p-4 sm:p-6">
                <div className="flex justify-between items-center mb-6 flex-wrap gap-3">
                  <div>
                    <h3 className="text-lg font-bold flex items-center gap-2 text-foreground">
                      <History className="w-5 h-5 text-primary" /> Campaign Progress
                      {pollingActive && <span className="h-2 w-2 rounded-full bg-emerald-500 animate-ping ml-1"></span>}
                    </h3>
                    {selectedCampaign.status.toUpperCase() === 'SCHEDULED' && selectedCampaign.scheduled_at && (
                      <p className="text-xs text-purple-600 dark:text-purple-400 font-semibold mt-0.5">
                        Scheduled for {formatScheduled(selectedCampaign.scheduled_at)}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {['QUEUED', 'PROCESSING'].includes(selectedCampaign.status.toUpperCase()) && (
                      <button onClick={() => handleCampaignAction('pause')} className="bg-amber-500 hover:bg-amber-600 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer">Pause</button>
                    )}
                    {selectedCampaign.status.toUpperCase() === 'PAUSED' && (
                      <button onClick={() => handleCampaignAction('resume')} className="bg-primary hover:bg-primary/90 text-primary-foreground px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer">Resume</button>
                    )}
                    {selectedCampaign.status.toUpperCase() === 'SCHEDULED' && (
                      <>
                        <button onClick={() => openScheduleModal('edit')} className="bg-primary/10 text-primary hover:bg-primary/20 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer border border-primary/20">Edit</button>
                        <button onClick={() => openScheduleModal('reschedule')} className="bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer border border-purple-500/20">Reschedule</button>
                        <button onClick={handleCancelSchedule} className="bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer border border-amber-500/20">Cancel schedule</button>
                      </>
                    )}
                    {['DRAFT', 'SCHEDULED'].includes(selectedCampaign.status.toUpperCase()) && (
                      <button onClick={() => handleDeleteCampaign(selectedCampaign.id)} className="bg-red-500/10 text-red-600 hover:bg-red-500/20 px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer border border-red-500/20">Delete</button>
                    )}
                    {selectedCampaign.total_failed > 0 && (
                      <button onClick={handleRetryAll} disabled={retryingAll} className="flex items-center gap-1.5 bg-orange-500 hover:bg-orange-600 disabled:opacity-50 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer">
                        {retryingAll ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCw className="h-3 w-3" />} Retry failed
                      </button>
                    )}
                    {['QUEUED', 'PROCESSING', 'PAUSED'].includes(selectedCampaign.status.toUpperCase()) && (
                      <button onClick={() => handleCampaignAction('cancel')} className="bg-red-500/90 hover:bg-red-600 text-white px-3 py-1.5 rounded-lg text-xs font-bold transition-colors cursor-pointer">Cancel</button>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                  <div className="bg-muted/30 p-4 rounded-xl border border-border text-center">
                    <div className="text-2xl font-bold text-foreground">{selectedCampaign.total_locations}</div>
                    <div className="text-xs text-muted-foreground uppercase mt-1">Total</div>
                  </div>
                  <div className="bg-emerald-500/10 p-4 rounded-xl border border-emerald-500/20 text-center">
                    <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">{selectedCampaign.total_published}</div>
                    <div className="text-xs text-emerald-600/70 dark:text-emerald-500/70 uppercase mt-1">Published</div>
                  </div>
                  <div className="bg-amber-500/10 p-4 rounded-xl border border-amber-500/20 text-center">
                    <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">{selectedCampaign.total_pending}</div>
                    <div className="text-xs text-amber-600/70 dark:text-amber-500/70 uppercase mt-1">Pending</div>
                  </div>
                  <div className="bg-red-500/10 p-4 rounded-xl border border-red-500/20 text-center">
                    <div className="text-2xl font-bold text-red-600 dark:text-red-400">{selectedCampaign.total_failed}</div>
                    <div className="text-xs text-red-600/70 dark:text-red-500/70 uppercase mt-1">Failed</div>
                  </div>
                </div>

                <div className="space-y-2 mb-6">
                  <div className="flex justify-between text-xs font-bold text-muted-foreground">
                    <span>Publishing Progress</span>
                    <span>{pct(selectedCampaign.total_published, selectedCampaign.total_locations)}%</span>
                  </div>
                  <div className="h-3 w-full bg-muted rounded-full overflow-hidden">
                    <div className="h-full bg-primary transition-all duration-500" style={{ width: `${pct(selectedCampaign.total_published, selectedCampaign.total_locations)}%` }} />
                  </div>
                </div>

                {/* Full per-location status table */}
                {selectedCampaign.jobs && selectedCampaign.jobs.length > 0 && (
                  <div className="mt-2">
                    <div className="flex items-center justify-between mb-3 gap-3">
                      <h4 className="text-sm font-bold text-foreground flex items-center gap-2">
                        <FileText className="w-4 h-4 text-muted-foreground" /> Locations ({selectedCampaign.jobs.length})
                      </h4>
                      <div className="relative shrink-0">
                        <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-muted-foreground" />
                        <input
                          type="text"
                          placeholder="Find location…"
                          value={jobSearch}
                          onChange={e => setJobSearch(e.target.value)}
                          className="bg-background border border-input text-foreground rounded-lg pl-8 pr-3 py-1.5 text-xs outline-none focus:ring-1 focus:ring-primary w-32 sm:w-44"
                        />
                      </div>
                    </div>
                    <div className="bg-background border border-border rounded-xl overflow-x-auto max-h-[360px] overflow-y-auto">
                      <table className="w-full min-w-[480px] text-sm text-left">
                        <thead className="bg-muted text-[10px] uppercase text-muted-foreground sticky top-0 backdrop-blur-md">
                          <tr>
                            <th className="px-4 py-3 font-bold">Location</th>
                            <th className="px-4 py-3 font-bold">Status</th>
                            <th className="px-4 py-3 font-bold">Detail</th>
                            <th className="px-4 py-3 font-bold text-right">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedCampaign.jobs
                            .map(job => ({ job, name: locations.find(l => l.id === job.location_id)?.location_name || `Location ${job.location_id}` }))
                            .filter(({ name }) => name.toLowerCase().includes(jobSearch.toLowerCase()))
                            .map(({ job, name }) => {
                              const isFailed = job.status.toUpperCase() === 'FAILED'
                              return (
                                <tr key={job.id} className="border-t border-border/60 hover:bg-muted/30 transition-colors">
                                  <td className="px-4 py-3 font-medium text-foreground">{name}</td>
                                  <td className="px-4 py-3"><JobBadge status={job.status} />{(job.retry_count ?? 0) > 0 && <span className="ml-1.5 text-[10px] text-muted-foreground">·{job.retry_count}×</span>}</td>
                                  <td className="px-4 py-3 text-xs">
                                    {isFailed ? (
                                      <span className="text-red-600 dark:text-red-400 font-mono line-clamp-1" title={job.last_error || ''}>{job.last_error || 'Unknown error'}</span>
                                    ) : job.google_post_id ? (
                                      <span className="text-emerald-600 dark:text-emerald-400">Live on Google</span>
                                    ) : (
                                      <span className="text-muted-foreground">—</span>
                                    )}
                                  </td>
                                  <td className="px-4 py-3 text-right">
                                    {isFailed && (
                                      <button onClick={() => handleRetryJob(job.id)} disabled={retryingJobId === job.id} className="inline-flex items-center gap-1 text-xs font-bold text-orange-600 dark:text-orange-400 hover:underline disabled:opacity-50 cursor-pointer">
                                        {retryingJobId === job.id ? <Loader2 className="h-3 w-3 animate-spin" /> : <RotateCw className="h-3 w-3" />} Retry
                                      </button>
                                    )}
                                  </td>
                                </tr>
                              )
                            })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-card shadow-sm border border-border rounded-2xl p-12 text-center text-muted-foreground">
                Select a campaign to view the live monitor
              </div>
            )}
          </div>
        </div>
      </main>

      {/* New Campaign — stepper modal with sticky live preview */}
      {isModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/60 backdrop-blur-sm"
          onClick={() => setIsModalOpen(false)}
          onKeyDown={(e) => { if (e.key === 'Escape') setIsModalOpen(false) }}
        >
          <div className="bg-background border border-border rounded-t-2xl sm:rounded-2xl w-full sm:w-[calc(100%-2rem)] max-w-5xl h-[92vh] sm:h-auto sm:max-h-[90vh] overflow-hidden shadow-2xl flex flex-col" onClick={e => e.stopPropagation()}>
            {/* Header + step indicator */}
            <div className="p-4 sm:p-5 flex justify-between items-start sm:items-center gap-3 border-b border-border">
              <div className="min-w-0">
                <h3 className="text-base sm:text-lg font-bold text-foreground flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-primary shrink-0" /> <span className="truncate">{locationId ? 'New Post' : 'New Multi-Location Campaign'}</span>
                </h3>
                <div className="flex items-center flex-wrap gap-x-2 gap-y-1 mt-2">
                  {['Content', 'Media', ...(locationId ? [] : ['Locations'])].map((label, i) => {
                    const n = i + 1
                    const active = step === n
                    const done = step > n
                    return (
                      <div key={label} className="flex items-center gap-2">
                        <span className={`flex items-center gap-1.5 text-xs font-bold ${active ? 'text-primary' : done ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
                          <span className={`flex items-center justify-center h-6 w-6 sm:h-5 sm:w-5 rounded-full text-xs sm:text-[10px] border ${active ? 'border-primary bg-primary/10' : done ? 'border-emerald-500 bg-emerald-500/10' : 'border-border'}`}>
                            {done ? '✓' : n}
                          </span>
                          {label}
                        </span>
                        {n < lastStep && <ChevronRight className="h-3 w-3 text-muted-foreground/40" />}
                      </div>
                    )
                  })}
                </div>
              </div>
              <button onClick={() => setIsModalOpen(false)} className="shrink-0 flex h-10 w-10 sm:h-auto sm:w-auto items-center justify-center -mr-2 sm:mr-0 text-muted-foreground hover:text-foreground cursor-pointer"><X className="w-5 h-5" /></button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-5 flex-1 overflow-hidden">
              {/* Step body */}
              <div className="md:col-span-3 p-4 sm:p-6 overflow-y-auto space-y-5">
                {errorAlert && <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm font-medium rounded-lg">{errorAlert}</div>}

                {/* STEP 1 — Content */}
                {step === 1 && (
                  <div className="space-y-4">
                    <input type="text" placeholder="Campaign Name (e.g. Summer Sale)" value={campaignName} onChange={e => setCampaignName(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-base sm:text-sm focus:ring-1 focus:ring-primary outline-none" />
                    <div>
                      <input type="text" maxLength={TITLE_MAX} placeholder="Post Title (Optional)" value={title} onChange={e => setTitle(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-base sm:text-sm focus:ring-1 focus:ring-primary outline-none" />
                      <div className="text-right text-[10px] text-muted-foreground mt-1">{title.length}/{TITLE_MAX}</div>
                    </div>

                    <div>
                      <textarea
                        ref={textareaRef}
                        rows={5}
                        maxLength={SUMMARY_MAX}
                        placeholder="Post body…"
                        value={summary}
                        onChange={e => setSummary(e.target.value)}
                        className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-base sm:text-sm focus:ring-1 focus:ring-primary outline-none"
                      />
                      <div className="flex flex-wrap items-center justify-between gap-y-1.5 mt-1.5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className="text-[10px] text-muted-foreground font-semibold">Insert:</span>
                          {['location', 'city', 'phone', 'location_id'].map(v => (
                            <button key={v} type="button" onClick={() => insertVariable(v)} className="px-2 py-1 sm:px-1.5 sm:py-0.5 rounded bg-muted hover:bg-muted/70 text-xs sm:text-[10px] font-mono text-foreground transition-colors cursor-pointer">
                              {`{{${v}}}`}
                            </button>
                          ))}
                        </div>
                        <span className={`text-[10px] ${summary.length > SUMMARY_MAX - 50 ? 'text-amber-600 dark:text-amber-400 font-bold' : 'text-muted-foreground'}`}>{summary.length}/{SUMMARY_MAX}</span>
                      </div>
                    </div>

                    <div className="space-y-1.5 border border-border p-4 rounded-xl">
                      <label className="text-xs font-bold uppercase text-muted-foreground block mb-2">Publishing Timing</label>
                      <div className="flex flex-wrap gap-4 mb-3">
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                          <input type="radio" name="publishMode" value="NOW" checked={publishMode === 'NOW'} onChange={() => setPublishMode('NOW')} className="text-primary focus:ring-primary h-4 w-4" />
                          Publish Now
                        </label>
                        <label className="flex items-center gap-2 text-sm cursor-pointer">
                          <input type="radio" name="publishMode" value="SCHEDULED" checked={publishMode === 'SCHEDULED'} onChange={() => setPublishMode('SCHEDULED')} className="text-primary focus:ring-primary h-4 w-4" />
                          Schedule for Later
                        </label>
                      </div>
                      
                      {publishMode === 'SCHEDULED' && (
                        <div className="mt-3 space-y-2">
                          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                            <input type="date" value={scheduledDate} onChange={e => setScheduledDate(e.target.value)} min={localToday()} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none" required />
                            <input type="time" value={scheduledTime} onChange={e => setScheduledTime(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none" required />
                          </div>
                          <p className="text-[10px] text-muted-foreground">
                            Time is your local timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}).
                          </p>
                        </div>
                      )}
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div className="space-y-1.5">
                        <label className="text-xs font-bold uppercase text-muted-foreground">CTA Button</label>
                        <select value={ctaType} onChange={e => setCtaType(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-base sm:text-sm focus:ring-1 focus:ring-primary outline-none">
                          <option value="NONE">None (Text-only Post)</option>
                          <option value="LEARN_MORE">Learn More</option>
                          <option value="BOOK">Book</option>
                          <option value="ORDER">Order Online</option>
                          <option value="SHOP">Shop</option>
                          <option value="SIGN_UP">Sign Up</option>
                          <option value="CALL">Call Now (Uses Location Phone)</option>
                        </select>
                      </div>
                      {ctaType !== 'NONE' && ctaType !== 'CALL' && (
                        <div className="space-y-1.5">
                          <label className="text-xs font-bold uppercase text-muted-foreground">CTA URL</label>
                          <input
                            type="text"
                            placeholder="https://example.com/promo?loc={{location_id}}"
                            value={ctaUrl}
                            onChange={e => setCtaUrl(e.target.value)}
                            className={`w-full bg-background border text-foreground rounded-xl p-3 text-base sm:text-sm focus:ring-1 outline-none ${ctaUrl && !validateUrl(ctaUrl) ? 'border-red-400 focus:ring-red-400' : 'border-input focus:ring-primary'}`}
                          />
                          {ctaUrl && !validateUrl(ctaUrl) && <p className="text-[10px] text-red-500">Must be a valid http(s) URL.</p>}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* STEP 2 — Media */}
                {step === 2 && (
                  <div className="space-y-4">
                    <p className="text-xs text-muted-foreground">Add a single image (JPG, PNG or WEBP). Google Business Profile posts don&apos;t support video.</p>
                    {mediaUrl ? (
                      <div className="flex items-center justify-between gap-4 bg-muted/30 border border-border p-4 rounded-xl">
                        <div className="flex items-center gap-4">
                          <img src={mediaUrl} className="w-20 h-20 object-cover rounded-lg border border-border" />
                          <div className="text-sm">
                            {mediaReady ? (
                              <span className="text-emerald-600 dark:text-emerald-400 font-bold flex items-center gap-1"><CheckCircle2 className="w-4 h-4" /> Ready to publish</span>
                            ) : (
                              <span className="text-amber-600 dark:text-amber-400 font-bold flex items-center gap-1"><Loader2 className="w-4 h-4 animate-spin" /> Optimizing for Google…</span>
                            )}
                            <p className="text-[11px] text-muted-foreground mt-1 max-w-[220px] truncate">{mediaPayload?.original_filename}</p>
                          </div>
                        </div>
                        <button onClick={handleRemoveMedia} className="p-2 text-muted-foreground hover:text-red-500 transition-colors rounded-lg hover:bg-red-500/10 cursor-pointer"><XCircle className="w-5 h-5" /></button>
                      </div>
                    ) : (
                      <div>
                        <input type="file" accept="image/png,image/jpeg,image/webp" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
                        <button onClick={() => fileInputRef.current?.click()} disabled={uploading} className="w-full flex flex-col items-center justify-center gap-2 bg-muted/20 border-2 border-dashed border-border hover:border-primary/50 hover:bg-muted/30 px-4 py-10 rounded-xl text-sm font-bold text-foreground transition-colors cursor-pointer">
                          {uploading ? <Loader2 className="w-6 h-6 animate-spin text-primary" /> : <Upload className="w-6 h-6 text-primary" />}
                          {uploading ? 'Uploading…' : 'Click to upload an image'}
                          <span className="text-[11px] font-normal text-muted-foreground">Min 250px · JPG, PNG, WEBP</span>
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* STEP 3 — Locations (multi-location only) */}
                {step === 3 && !locationId && (
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-sm font-bold text-foreground">Target Locations</span>
                      <div className="flex items-center gap-3">
                        <button onClick={handleToggleSelectAll} className="text-xs text-primary hover:text-primary/80 font-bold cursor-pointer">
                          {selectedLocationIds.length > 0 && selectedLocationIds.length >= filteredLocations.filter(l => l.billing_status !== 'pending_payment').length ? 'Deselect All' : 'Select All'}
                        </button>
                        <span className="text-primary bg-primary/10 px-2 py-0.5 rounded text-xs font-bold">{selectedLocationIds.length} selected</span>
                      </div>
                    </div>
                    <div className="relative">
                      <Search className="w-4 h-4 absolute left-3 top-3.5 text-muted-foreground" />
                      <input type="text" placeholder="Search locations…" value={locationSearch} onChange={e => setLocationSearch(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl pl-10 p-3 text-base sm:text-sm focus:ring-1 focus:ring-primary outline-none" />
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[340px] overflow-y-auto pr-1">
                      {filteredLocations.map(loc => {
                        const isLocked = loc.billing_status === 'pending_payment'
                        const checked = selectedLocationIds.includes(loc.id)
                        return (
                          <button
                            key={loc.id}
                            disabled={isLocked}
                            title={isLocked ? 'Locked pending payment. Unlock it to publish.' : undefined}
                            onClick={() => setSelectedLocationIds(p => p.includes(loc.id) ? p.filter(id => id !== loc.id) : [...p, loc.id])}
                            className={`flex items-start text-left p-3.5 sm:p-3 rounded-xl border transition-colors ${isLocked ? 'opacity-50 cursor-not-allowed bg-muted/30 border-border' : `cursor-pointer ${checked ? 'bg-primary/5 border-primary/50' : 'bg-background border-border hover:bg-muted/50'}`}`}
                          >
                            <span className={`mt-0.5 mr-3 flex items-center justify-center h-5 w-5 sm:h-4 sm:w-4 rounded border shrink-0 ${checked ? 'bg-primary border-primary text-primary-foreground' : 'border-input'}`}>
                              {checked && <CheckCircle2 className="h-3.5 w-3.5 sm:h-3 sm:w-3" />}
                            </span>
                            <div className="min-w-0">
                              <div className="text-sm font-bold text-foreground flex items-center gap-1.5">
                                <span className="truncate">{loc.location_name}</span>
                                {isLocked && <Lock className="h-3 w-3 text-amber-500 shrink-0" />}
                              </div>
                              <div className="text-xs text-muted-foreground truncate">{isLocked ? 'Locked — upgrade to publish' : loc.address}</div>
                            </div>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )}
              </div>

              {/* Sticky live preview */}
              <div className="md:col-span-2 border-l border-border bg-muted/10 p-6 overflow-y-auto hidden md:block">
                <div className="text-xs font-bold uppercase text-muted-foreground flex items-center gap-1.5 mb-3">
                  <Sparkles className="w-3.5 h-3.5 text-primary" /> Live Preview
                </div>
                <div className="bg-card border border-border rounded-xl p-4 shadow-sm space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center font-bold text-xs text-primary">G</div>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-foreground truncate">
                        {selectedLocationIds.length > 0 ? locations.find(l => l.id === selectedLocationIds[0])?.location_name : 'Your Location'}
                      </div>
                      <div className="text-[9px] text-muted-foreground">Just now · GBP Post</div>
                    </div>
                  </div>
                  {mediaUrl && <img src={mediaUrl} className="w-full h-36 object-cover rounded-lg border border-border" />}
                  {title && <div className="text-sm font-bold text-foreground">{title}</div>}
                  <div className="text-xs text-foreground/80 whitespace-pre-wrap leading-relaxed min-h-[40px]">{getLivePreview()}</div>
                  {ctaType !== 'NONE' && (
                    <span className="inline-block bg-primary text-primary-foreground font-bold text-xs px-4 py-2 rounded-lg">{CTA_LABELS[ctaType] || 'Learn More'}</span>
                  )}
                </div>
                <p className="text-[10px] text-muted-foreground mt-3 leading-relaxed">Preview uses the first selected location. Each location renders its own {`{{variables}}`}.</p>
              </div>
            </div>

            {/* Footer nav */}
            <div className="p-4 border-t border-border flex justify-between items-center gap-3 bg-background">
              <button
                onClick={() => step > 1 ? setStep(step - 1) : setIsModalOpen(false)}
                className="flex items-center justify-center gap-1.5 px-4 h-11 sm:h-auto sm:py-2.5 rounded-lg text-sm font-bold bg-muted/50 text-foreground hover:bg-muted border border-border transition-colors cursor-pointer"
              >
                {step > 1 ? <><ChevronLeft className="w-4 h-4" /> Back</> : 'Cancel'}
              </button>
              {step < lastStep ? (
                <button
                  onClick={() => setStep(step + 1)}
                  disabled={step === 1 && !canLeaveStep1}
                  className="flex flex-1 sm:flex-none items-center justify-center gap-1.5 px-5 h-11 sm:h-auto sm:py-2.5 rounded-lg text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer"
                >
                  Next <ChevronRight className="w-4 h-4" />
                </button>
              ) : (
                <button
                  onClick={handleCreateCampaign}
                  disabled={submitting || uploading || !canLaunch}
                  className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-5 h-11 sm:h-auto sm:py-2.5 rounded-lg text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm cursor-pointer"
                >
                  {submitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} Launch
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Edit / Reschedule a scheduled campaign */}
      {scheduleModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm" onClick={() => !savingSchedule && setScheduleModal(null)}>
          <div className="bg-background border border-border rounded-2xl w-full max-w-lg shadow-2xl flex flex-col max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="p-5 flex justify-between items-center border-b border-border">
              <h3 className="text-base font-bold flex items-center gap-2 text-foreground">
                <Sparkles className="w-5 h-5 text-primary" /> {scheduleModal === 'edit' ? 'Edit scheduled post' : 'Reschedule campaign'}
              </h3>
              <button onClick={() => !savingSchedule && setScheduleModal(null)} className="text-muted-foreground hover:text-foreground cursor-pointer"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5 space-y-4 overflow-y-auto">
              {errorAlert && <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400 text-sm font-medium rounded-lg">{errorAlert}</div>}
              {scheduleModal === 'edit' && (
                <>
                  <input type="text" maxLength={TITLE_MAX} placeholder="Post Title (Optional)" value={schedTitle} onChange={e => setSchedTitle(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none" />
                  <textarea rows={4} maxLength={SUMMARY_MAX} placeholder="Post body…" value={schedSummary} onChange={e => setSchedSummary(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none" />
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <select value={schedCta} onChange={e => setSchedCta(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm outline-none focus:ring-1 focus:ring-primary">
                      <option value="NONE">None (Text-only)</option>
                      <option value="LEARN_MORE">Learn More</option>
                      <option value="BOOK">Book</option>
                      <option value="ORDER">Order Online</option>
                      <option value="SHOP">Shop</option>
                      <option value="SIGN_UP">Sign Up</option>
                      <option value="CALL">Call Now (Uses Location Phone)</option>
                    </select>
                    {schedCta !== 'NONE' && schedCta !== 'CALL' && (
                      <input type="text" placeholder="https://example.com" value={schedCtaUrl} onChange={e => setSchedCtaUrl(e.target.value)} className={`w-full bg-background border text-foreground rounded-xl p-3 text-sm outline-none focus:ring-1 ${schedCtaUrl && !validateUrl(schedCtaUrl) ? 'border-red-400 focus:ring-red-400' : 'border-input focus:ring-primary'}`} />
                    )}
                  </div>
                </>
              )}
              <div>
                <label className="text-xs font-bold uppercase text-muted-foreground block mb-2">Publish at</label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <input type="date" value={schedDate} min={localToday()} onChange={e => setSchedDate(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none" />
                  <input type="time" value={schedTime} onChange={e => setSchedTime(e.target.value)} className="w-full bg-background border border-input text-foreground rounded-xl p-3 text-sm focus:ring-1 focus:ring-primary outline-none" />
                </div>
                <p className="text-[10px] text-muted-foreground mt-1.5">Time is your local timezone ({Intl.DateTimeFormat().resolvedOptions().timeZone}).</p>
              </div>
            </div>
            <div className="p-4 border-t border-border flex justify-end gap-3">
              <button onClick={() => setScheduleModal(null)} disabled={savingSchedule} className="px-4 py-2.5 rounded-lg text-sm font-bold bg-muted/50 text-foreground hover:bg-muted border border-border transition-colors cursor-pointer disabled:opacity-50">Cancel</button>
              <button onClick={handleSaveSchedule} disabled={savingSchedule} className="flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors cursor-pointer">
                {savingSchedule ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />} {scheduleModal === 'edit' ? 'Save changes' : 'Reschedule'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
