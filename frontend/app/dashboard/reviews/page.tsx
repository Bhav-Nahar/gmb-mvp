'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import {
  Star,
  RefreshCw,
  MessageCircle,
  MessageSquare,
  AlertTriangle,
  CheckCircle2,
  Send,
  User as UserIcon,
  Sparkles,
  Clock,
  ThumbsUp,
  Inbox,
  Filter
} from 'lucide-react'

import { resolveTemplateVariables } from '@/lib/utils/template-utils'
import { AnalyticsTab } from './AnalyticsTab'

interface ReplyTemplate {
  id: number;
  title: string;
  body: string;
}

interface Location {
  id: number
  location_name: string
}

interface Review {
  id: number
  location_id: number
  reviewer_name: string
  reviewer_profile_photo?: string
  rating?: number
  comment?: string
  is_replied: boolean
  reply_text?: string
  reply_created_at?: string | null
  review_created_at: string
  sentiment?: string | null
  issue_category?: string | null
  sentiment_tagged_at?: string | null
  location_name: string
  suggested_templates?: ReplyTemplate[]
}

interface SLAMetrics {
  sla_enabled: boolean
  sla_tracking_started_at: string | null
  total_replied: number
  avg_response_hours: number | null
  avg_sla_tier: string | null
  pending_count: number
  overdue_count: number
}

interface ReviewListResponse {
  reviews: Review[]
  total: number
  page: number
  pages: number
}

interface ReviewSummary {
  avg_rating: number | null
  rated_location_count: number
  total_reviews: number
  total_reviews_all_time: number
  response_rate: number | null
}

export default function ReviewsPage(props: any) {
  const locationId = props.locationId;
  const [view, setView] = useState<'inbox' | 'analytics'>('inbox')
  // Read ?tab= after mount — reading the URL in the initializer breaks SSR hydration.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('tab') === 'analytics') setView('analytics')
  }, [])
  const [reviews, setReviews] = useState<Review[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [selectedReviewId, setSelectedReviewId] = useState<number | null>(null)
  
  // Pagination
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  
  // Filters
  const [filterRating, setFilterRating] = useState<number | ''>('')
  const [filterReplied, setFilterReplied] = useState<'all' | 'replied' | 'unreplied'>('all')
  const [filterLocation, setFilterLocation] = useState<number | ''>(locationId || '')
  const [filterSentiment, setFilterSentiment] = useState<string>('')
  const [filterCategory, setFilterCategory] = useState<string>('')
  const [filterSlaTier, setFilterSlaTier] = useState<string>('')
  const [filterOverdue, setFilterOverdue] = useState<boolean>(false)
  const [showAdvancedFilters, setShowAdvancedFilters] = useState(false)

  // SLA State
  const [slaMetrics, setSlaMetrics] = useState<SLAMetrics | null>(null)
  const [reviewSummary, setReviewSummary] = useState<ReviewSummary | null>(null)
  const [showSlaModal, setShowSlaModal] = useState(false)
  const [enablingSla, setEnablingSla] = useState(false)

  // Reply state
  const [replyingTo, setReplyingTo] = useState<number | null>(null)
  const [replyText, setReplyText] = useState('')
  const [replyingTemplateId, setReplyingTemplateId] = useState<number | null>(null)
  const [replying, setReplying] = useState(false)
  // Pending template selection awaiting overwrite confirmation
  const [pendingTemplate, setPendingTemplate] = useState<{ id: number; text: string } | null>(null)

  // AI Generation state
  const [generatingFor, setGeneratingFor] = useState<number | null>(null)
  const [generatedReplies, setGeneratedReplies] = useState<Record<number, {
    reply: string
    tone: string
    variants?: { recommended: string; short: string; warm_or_professional: string }
    manualReviewRequired?: boolean
    riskLevel?: string
  }>>({})
  const [generationError, setGenerationError] = useState<Record<number, string>>({})

  // Retag state
  const [retagging, setRetagging] = useState(false)
  const [retagDisabled, setRetagDisabled] = useState(false)

  // Alerts
  const [errorAlert, setErrorAlert] = useState('')
  const [successAlert, setSuccessAlert] = useState('')
  
  const { user } = useAuth()
  const userRole = user?.role || 'Viewer'

  useEffect(() => {
    loadLocations()
  }, [])

  useEffect(() => {
    if (locationId) {
      setFilterLocation(locationId)
    }
  }, [locationId])

  useEffect(() => {
    if (filterLocation !== '') {
      loadSlaMetrics(filterLocation)
    } else {
      setSlaMetrics(null)
    }
  }, [filterLocation])

  // Reputation KPIs (avg rating, total reviews, response rate) — scoped to the
  // selected location, or org-wide when no location filter is applied.
  useEffect(() => {
    const loadReviewSummary = async () => {
      try {
        const qs = filterLocation !== '' ? `?location_id=${filterLocation}` : ''
        const data = await api.get<ReviewSummary>(`/insights/summary${qs}`)
        setReviewSummary(data)
      } catch (e: any) {
        console.error('Failed to load review summary', e)
      }
    }
    loadReviewSummary()
  }, [filterLocation])

  useEffect(() => {
    setCurrentPage(1)
  }, [filterRating, filterReplied, filterLocation, filterSentiment, filterCategory, filterSlaTier, filterOverdue])

  useEffect(() => {
    loadReviews()
  }, [currentPage, filterRating, filterReplied, filterLocation, filterSentiment, filterCategory, filterSlaTier, filterOverdue])

  const loadSlaMetrics = async (locId: number) => {
    try {
      const data = await api.get<SLAMetrics>(`/locations/${locId}/sla`)
      setSlaMetrics(data)
    } catch (e: any) {
      console.error('Failed to load SLA metrics', e)
    }
  }

  const loadLocations = async () => {
    try {
      const data = await api.get<Location[]>('/locations/')
      setLocations(data)
    } catch (e: any) {
      console.error('Failed to load locations', e)
    }
  }

  const loadReviews = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', currentPage.toString())
      if (filterRating !== '') params.append('rating', filterRating.toString())
      if (filterReplied === 'replied') params.append('is_replied', 'true')
      if (filterReplied === 'unreplied') params.append('is_replied', 'false')
      if (filterLocation !== '') params.append('location_id', filterLocation.toString())
      if (filterSentiment !== '') params.append('sentiment', filterSentiment)
      if (filterCategory !== '') params.append('issue_category', filterCategory)
      if (filterSlaTier !== '') params.append('sla_tier', filterSlaTier)
      if (filterOverdue) params.append('overdue_only', 'true')

      const data = await api.get<ReviewListResponse>(`/reviews/?${params.toString()}`)
      setReviews(data.reviews || [])
      setTotalPages(data.pages || 1)
    } catch (e: any) {
      console.error(e)
      setErrorAlert(e.message || 'Failed to load reviews.')
    } finally {
      setLoading(false)
    }
  }

  // Auto-select first review on load
  useEffect(() => {
    if (reviews.length > 0 && !selectedReviewId) {
      setSelectedReviewId(reviews[0].id)
    } else if (reviews.length === 0) {
      setSelectedReviewId(null)
    }
  }, [reviews])

  const handleTriggerSync = async () => {
    setSyncing(true)
    setErrorAlert('')
    setSuccessAlert('')
    try {
      const response: any = await api.post('/reviews/sync')
      setSuccessAlert(response.message || 'Reviews sync queued successfully.')
      setTimeout(() => {
        loadReviews()
        setSyncing(false)
      }, 3000)
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to trigger background synchronization.')
      setSyncing(false)
    }
  }

  const handleRetag = async () => {
    if (!filterLocation || retagDisabled) return
    setRetagging(true)
    setRetagDisabled(true)
    setErrorAlert('')
    try {
      await api.post(`/reviews/locations/${filterLocation}/retag-sentiment`)
      setSuccessAlert('Sentiment retagging queued.')
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to queue sentiment retagging.')
    } finally {
      setRetagging(false)
      // Disable the button for 5 seconds to prevent spam
      setTimeout(() => setRetagDisabled(false), 5000)
    }
  }

  const handleEnableSla = async () => {
    if (!filterLocation) return
    setEnablingSla(true)
    setErrorAlert('')
    try {
      await api.post(`/locations/${filterLocation}/sla/enable`)
      setSuccessAlert('SLA Tracking enabled successfully!')
      setShowSlaModal(false)
      loadSlaMetrics(filterLocation)
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to enable SLA tracking.')
    } finally {
      setEnablingSla(false)
    }
  }

  const renderSlaBadge = (review: Review) => {
    if (!slaMetrics?.sla_enabled || !slaMetrics.sla_tracking_started_at) return null
    if (new Date(review.review_created_at) < new Date(slaMetrics.sla_tracking_started_at)) return null

    if (review.is_replied && review.reply_created_at) {
      const hours = (new Date(review.reply_created_at).getTime() - new Date(review.review_created_at).getTime()) / 3600000
      if (hours <= 12) return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">⚡ Best</span>
      if (hours <= 24) return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">✓ Good</span>
      if (hours <= 72) return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">~ Avg</span>
      return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30">✗ Poor</span>
    } else if (!review.is_replied) {
      const hours = (new Date().getTime() - new Date(review.review_created_at).getTime()) / 3600000
      if (hours > 72) return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30">Overdue</span>
      if (hours > 24) return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">Pending</span>
      return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-muted/20 text-muted-foreground border border-border">Awaiting</span>
    }
    return null
  }

  const handlePostReply = async (reviewId: number) => {
    if (!replyText.trim()) return

    setReplying(true)
    setErrorAlert('')
    try {
      await api.post(`/reviews/${reviewId}/reply`, {
        reply_text: replyText,
        template_id: replyingTemplateId || undefined
      })
      setSuccessAlert('Reply posted successfully.')
      setReplyingTo(null)
      setReplyText('')
      setReplyingTemplateId(null)
      loadReviews()
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to post reply.')
    } finally {
      setReplying(false)
    }
  }

  const handleGenerateReply = async (reviewId: number) => {
    setGeneratingFor(reviewId)
    setGenerationError(prev => {
      const copy = { ...prev }
      delete copy[reviewId]
      return copy
    })
    try {
      const response = await api.post<{
        review_id: number; generated_reply: string; tone: string
        recommended_reply?: string; short_reply?: string; warm_or_professional_reply?: string
        manual_review_required?: boolean; risk_level?: string
      }>(`/reviews/${reviewId}/generate-reply`)
      setGeneratedReplies(prev => ({
        ...prev,
        [reviewId]: {
          reply: response.recommended_reply ?? response.generated_reply,
          tone: response.tone,
          variants: response.recommended_reply ? {
            recommended: response.recommended_reply,
            short: response.short_reply ?? response.recommended_reply,
            warm_or_professional: response.warm_or_professional_reply ?? response.recommended_reply,
          } : undefined,
          manualReviewRequired: response.manual_review_required,
          riskLevel: response.risk_level,
        }
      }))
    } catch (err: any) {
      console.error('Failed to generate reply:', err)
      setGenerationError(prev => ({
        ...prev,
        [reviewId]: 'Could not generate reply. Please try again.'
      }))
    } finally {
      setGeneratingFor(null)
    }
  }

  const handlePostAiReply = async (reviewId: number) => {
    const aiReply = generatedReplies[reviewId]
    if (!aiReply || !aiReply.reply.trim()) return

    setReplying(true)
    setErrorAlert('')
    try {
      const updatedReview = await api.post<Review>(`/reviews/${reviewId}/reply`, {
        reply_text: aiReply.reply
      })
      
      setReviews(reviews.map(r => r.id === reviewId ? updatedReview : r))
      setSuccessAlert('Reply posted successfully!')
      
      setGeneratedReplies(prev => {
        const copy = { ...prev }
        delete copy[reviewId]
        return copy
      })
      setReplyingTo(null)
    } catch (err: any) {
      setErrorAlert(err.message || 'Failed to post reply.')
    } finally {
      setReplying(false)
    }
  }


  const selectedReview = reviews.find(r => r.id === selectedReviewId)

  return (
    <div className={locationId ? "" : "min-h-screen bg-background text-foreground"}>
      <main className={locationId ? "space-y-6" : "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6"}>
          
          {/* Header Row */}
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            {!locationId && (<div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground flex items-center gap-2">
                <Inbox className="h-7 w-7 sm:h-8 sm:w-8 text-primary shrink-0" />
                Review Inbox
              </h1>
              <p className="text-muted-foreground mt-2">Manage and respond to customer feedback.</p>
            </div>)}
            
            {userRole !== 'Viewer' && (
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={handleTriggerSync}
                  disabled={syncing}
                  className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-4 py-2 min-h-[44px] sm:min-h-0 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
                >
                  <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
                  <span>{syncing ? 'Syncing...' : 'Sync Reviews'}</span>
                </button>
                {filterLocation !== '' && (
                  <button
                    onClick={handleRetag}
                    disabled={retagging || retagDisabled}
                    className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-4 py-2 min-h-[44px] sm:min-h-0 rounded-lg text-sm font-semibold text-teal-300 border border-teal-500/40 hover:bg-teal-500/10 disabled:opacity-50 transition-colors shadow-sm"
                  >
                    <RefreshCw className={`h-4 w-4 ${retagging ? 'animate-spin' : ''}`} />
                    <span>{retagging ? 'Retagging...' : 'Retag Sentiment'}</span>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Inbox / Analytics view toggle */}
          <div className="inline-flex items-center gap-1 rounded-full border border-border bg-card p-1 text-sm">
            <button onClick={() => setView('inbox')}
              className={`rounded-full px-5 py-1.5 font-semibold transition ${view === 'inbox' ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
              Inbox
            </button>
            <button onClick={() => setView('analytics')}
              className={`rounded-full px-5 py-1.5 font-semibold transition ${view === 'analytics' ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
              Analytics
            </button>
          </div>

          {view === 'analytics' && (
            <AnalyticsTab
              locations={locations}
              initialLocationId={filterLocation}
              onDrillToUnreplied={(locId) => {
                setFilterLocation(locId)
                setFilterReplied('unreplied')
                setView('inbox')
              }}
            />
          )}

          {view === 'inbox' && (<>
          {/* Reputation KPI row */}
          {reviewSummary && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
              <div className="glass-panel p-4 sm:p-5 flex items-center gap-3 rounded-2xl">
                <div className="p-2 rounded-xl bg-amber-400/10 text-amber-400 shrink-0">
                  <Star className="h-4 w-4 sm:h-5 sm:w-5 fill-amber-400" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl sm:text-2xl font-extrabold text-foreground leading-none">
                    {reviewSummary.avg_rating && reviewSummary.avg_rating > 0 ? reviewSummary.avg_rating.toFixed(1) : '—'}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 truncate uppercase tracking-wider font-bold">Avg rating</div>
                </div>
              </div>

              <div className="glass-panel p-4 sm:p-5 flex items-center gap-3 rounded-2xl">
                <div className="p-2 rounded-xl bg-sky-400/10 text-sky-400 shrink-0">
                  <MessageCircle className="h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl sm:text-2xl font-extrabold text-foreground leading-none tabular-nums">
                    {reviewSummary.total_reviews_all_time.toLocaleString()}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 truncate uppercase tracking-wider font-bold">Total reviews</div>
                </div>
              </div>

              <div className="glass-panel p-4 sm:p-5 flex items-center gap-3 rounded-2xl">
                <div className="p-2 rounded-xl bg-emerald-400/10 text-emerald-400 shrink-0">
                  <Send className="h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl sm:text-2xl font-extrabold text-foreground leading-none">
                    {reviewSummary.response_rate !== null && reviewSummary.response_rate !== undefined ? `${reviewSummary.response_rate.toFixed(0)}%` : '—'}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 truncate uppercase tracking-wider font-bold">Response rate</div>
                </div>
              </div>
            </div>
          )}

          {errorAlert && (
            <div className="flex items-center gap-3 rounded-xl bg-red-500/10 border border-red-500/20 p-4 text-sm font-medium text-red-400 shadow-sm animate-fade-in">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <span>{errorAlert}</span>
            </div>
          )}

          {successAlert && (
            <div className="flex items-center gap-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-4 text-sm font-medium text-emerald-400 shadow-sm animate-fade-in">
              <CheckCircle2 className="h-5 w-5 shrink-0" />
              <span>{successAlert}</span>
            </div>
          )}

          {/* SLA Tracking Bar */}
          {filterLocation !== '' && slaMetrics && (
            <div className="glass-panel border-primary/20 p-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 animate-fade-in">
              {!slaMetrics.sla_enabled ? (
                <>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Clock className="w-4 h-4" />
                    SLA Tracking is not enabled for this location.
                  </div>
                  <button onClick={() => setShowSlaModal(true)} className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 transition-colors shadow-sm">Enable SLA Tracking</button>
                </>
              ) : (
                <div className="flex flex-wrap items-center gap-6 w-full">
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Avg Response</span>
                    <span className="text-sm font-bold text-foreground">
                      {slaMetrics.avg_response_hours !== null ? `${slaMetrics.avg_response_hours}h — ${slaMetrics.avg_sla_tier}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Replied</span>
                    <span className="text-sm font-bold text-foreground">{slaMetrics.total_replied}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Overdue</span>
                    <span className="text-sm font-bold text-red-400">{slaMetrics.overdue_count}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Pending</span>
                    <span className="text-sm font-bold text-amber-400">{slaMetrics.pending_count}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Split-Pane Inbox Layout */}
          <div className="flex flex-col lg:flex-row gap-6 h-[calc(100vh-14rem)] lg:h-[calc(100vh-20rem)] min-h-[700px]">
             
             {/* Left Sidebar - Review Queue */}
             <div className={`w-full lg:w-[35%] flex-col glass-panel rounded-2xl border border-border shadow-sm overflow-hidden ${selectedReview ? 'hidden lg:flex' : 'flex'}`}>
                {/* Sleek Filter Toolbar (Sticky at top of Queue) */}
                <div className="bg-card/80 backdrop-blur-md border-b border-border p-3 shrink-0 flex flex-col gap-3">
                   <div className="flex items-center bg-background border border-border rounded-xl p-1 shrink-0">
                     <button onClick={() => setFilterReplied('all')} className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${filterReplied === 'all' ? 'bg-foreground text-background shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>All</button>
                     <button onClick={() => setFilterReplied('unreplied')} className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${filterReplied === 'unreplied' ? 'bg-foreground text-background shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Action Needed</button>
                     <button onClick={() => setFilterReplied('replied')} className={`flex-1 py-1.5 rounded-lg text-xs font-bold transition-all ${filterReplied === 'replied' ? 'bg-foreground text-background shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>Replied</button>
                   </div>
                   
                   <div className="flex items-center gap-2 flex-wrap pb-1">
                     <select
                       className="bg-background border border-border rounded-lg text-xs font-semibold px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary shrink-0 text-foreground cursor-pointer"
                       value={filterRating}
                       onChange={e => setFilterRating(e.target.value ? Number(e.target.value) : '')}
                     >
                       <option value="">All Ratings</option>
                       <option value="5">5 Stars</option>
                       <option value="4">4 Stars</option>
                       <option value="3">3 Stars</option>
                       <option value="2">2 Stars</option>
                       <option value="1">1 Star</option>
                     </select>
                     
                     <button 
                       onClick={() => setShowAdvancedFilters(!showAdvancedFilters)}
                       className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition-all border ${showAdvancedFilters ? 'bg-primary/10 text-primary border-primary/30' : 'bg-background text-muted-foreground border-border hover:bg-muted/50 hover:text-foreground'}`}
                     >
                       <Filter className="w-3.5 h-3.5" />
                       Filters
                       {(filterSentiment || filterLocation !== '' || filterCategory || filterSlaTier || filterOverdue) ? (
                         <span className="bg-primary text-primary-foreground text-[9px] px-1.5 py-0.5 rounded-full ml-1">
                           {[!!filterSentiment, filterLocation !== '', !!filterCategory, !!filterSlaTier, filterOverdue].filter(Boolean).length}
                         </span>
                       ) : null}
                     </button>
                   </div>
                   
                   {/* Advanced Filters Container */}
                   {showAdvancedFilters && (
                     <div className="flex items-center gap-2 flex-wrap bg-muted/30 p-2.5 rounded-xl border border-border mt-1 animate-fade-in">
                       <select
                         className="bg-background border border-border rounded-lg text-xs font-semibold px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary shrink-0 text-foreground cursor-pointer"
                         value={filterSentiment}
                         onChange={e => setFilterSentiment(e.target.value)}
                       >
                         <option value="">Sentiment</option>
                         <option value="Positive">Positive</option>
                         <option value="Neutral">Neutral</option>
                         <option value="Negative">Negative</option>
                         <option value="Angry">Angry</option>
                       </select>

                       {!locationId && (
                         <select
                           className="bg-background border border-border rounded-lg text-xs font-semibold px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary shrink-0 text-foreground cursor-pointer max-w-[120px] truncate"
                           value={filterLocation}
                           onChange={e => setFilterLocation(e.target.value ? Number(e.target.value) : '')}
                         >
                           <option value="">All Locations</option>
                           {locations.map(loc => (
                             <option key={loc.id} value={loc.id}>{loc.location_name}</option>
                           ))}
                         </select>
                       )}

                       <select
                         className="bg-background border border-border rounded-lg text-xs font-semibold px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary shrink-0 text-foreground cursor-pointer"
                         value={filterCategory}
                         onChange={e => { setFilterCategory(e.target.value); setCurrentPage(1); }}
                       >
                         <option value="">Category</option>
                         <option value="Staff Praise">Staff Praise</option>
                         <option value="Service Issue">Service Issue</option>
                         <option value="Pricing Concern">Pricing Concern</option>
                         <option value="Cleanliness">Cleanliness</option>
                         <option value="Delivery Issue">Delivery Issue</option>
                         <option value="Wait Time">Wait Time</option>
                         <option value="Product Quality">Product Quality</option>
                         <option value="General Feedback">General Feedback</option>
                       </select>

                       <select
                         className="bg-background border border-border rounded-lg text-xs font-semibold px-2 py-1.5 outline-none focus:ring-1 focus:ring-primary shrink-0 text-foreground cursor-pointer"
                         value={filterSlaTier}
                         onChange={e => { setFilterSlaTier(e.target.value); setCurrentPage(1); }}
                       >
                         <option value="">SLA Tier</option>
                         <option value="Best">Best</option>
                         <option value="Good">Good</option>
                         <option value="Average">Average</option>
                         <option value="Poor">Poor</option>
                       </select>

                       <label className="text-xs font-bold text-foreground flex items-center gap-1.5 cursor-pointer whitespace-nowrap bg-background border border-border rounded-lg px-2 py-1.5 shrink-0 transition-colors hover:bg-muted/50">
                          <input
                            type="checkbox"
                            className="rounded border-input text-primary focus:ring-primary h-3 w-3"
                            checked={filterOverdue}
                            onChange={e => { setFilterOverdue(e.target.checked); setCurrentPage(1); }}
                          />
                          Overdue Only
                       </label>
                     </div>
                   )}
                </div>

                {/* Queue List */}
                <div className="flex-1 overflow-y-auto p-3 space-y-2 bg-muted/10">
                  {loading ? (
                    <div className="flex h-full w-full items-center justify-center">
                      <RefreshCw className="h-6 w-6 animate-spin text-primary opacity-50" />
                    </div>
                  ) : reviews.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center p-6 opacity-60">
                      <Inbox className="h-10 w-10 text-muted-foreground mb-3" />
                      <p className="text-sm font-bold text-foreground">Inbox Zero!</p>
                      <p className="text-xs text-muted-foreground mt-1">No reviews match your filters.</p>
                    </div>
                  ) : (
                    reviews.map(review => (
                      <button 
                        key={review.id}
                        onClick={() => setSelectedReviewId(review.id)} 
                        className={`w-full text-left p-4 rounded-xl border transition-all relative ${
                          selectedReviewId === review.id 
                            ? 'bg-card border-primary shadow-md ring-1 ring-primary/20' 
                            : 'bg-card border-border hover:border-primary/40 hover:shadow-sm'
                        }`}
                      >
                        {/* Unread indicator */}
                        {!review.is_replied && (
                          <span className="absolute top-4 right-4 w-2 h-2 rounded-full bg-primary ring-2 ring-primary/20 animate-pulse" />
                        )}
                        <div className="flex justify-between items-start gap-3 mb-2 pr-4">
                          <div className="flex items-center gap-2">
                             {review.reviewer_profile_photo ? (
                               <img src={review.reviewer_profile_photo} alt={review.reviewer_name} className="w-7 h-7 rounded-full border border-border shrink-0" referrerPolicy="no-referrer" />
                             ) : (
                               <div className="w-7 h-7 rounded-full bg-muted/40 border border-border flex items-center justify-center shrink-0">
                                 <UserIcon className="h-3 w-3 text-muted-foreground" />
                               </div>
                             )}
                             <h4 className="font-bold text-sm text-foreground truncate">{review.reviewer_name}</h4>
                          </div>
                        </div>
                        <div className="flex justify-between items-center mb-2">
                          <div className="flex items-center gap-0.5">
                            {Array.from({ length: 5 }).map((_, i) => (
                              <Star key={i} className={`h-3 w-3 ${i < (review.rating || 0) ? 'text-amber-500 fill-amber-500' : 'text-muted-foreground/30'}`} />
                            ))}
                          </div>
                          <span className="text-[10px] font-semibold text-muted-foreground">
                            {new Date(review.review_created_at).toLocaleDateString(undefined, {month:'short', day:'numeric'})}
                          </span>
                        </div>
                        {review.comment ? (
                          <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
                            {review.comment}
                          </p>
                        ) : (
                          <p className="text-xs text-muted-foreground/50 italic">No comment provided.</p>
                        )}
                        
                        {/* Mini Badges */}
                        <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                           {review.sentiment && (
                             <span className={`w-2 h-2 rounded-full ${
                               review.sentiment === 'Positive' ? 'bg-emerald-500' :
                               review.sentiment === 'Neutral'  ? 'bg-slate-400' :
                               review.sentiment === 'Negative' ? 'bg-red-500' :
                               review.sentiment === 'Angry'    ? 'bg-rose-600' :
                               'bg-muted'
                             }`} title={review.sentiment} />
                           )}
                           {review.is_replied && (
                             <span className="text-[9px] font-bold uppercase tracking-wider text-primary border border-primary/20 bg-primary/10 px-1.5 rounded-sm">
                               Replied
                             </span>
                           )}
                        </div>
                      </button>
                    ))
                  )}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="bg-card border-t border-border p-3 flex justify-between items-center shrink-0">
                    <button
                      onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                      disabled={currentPage === 1 || loading}
                      className="px-3 py-1.5 rounded-md text-xs font-semibold border border-border text-foreground hover:bg-muted/50 disabled:opacity-50"
                    >
                      Prev
                    </button>
                    <span className="text-xs font-bold text-muted-foreground">
                      {currentPage} / {totalPages}
                    </span>
                    <button
                      onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                      disabled={currentPage === totalPages || loading}
                      className="px-3 py-1.5 rounded-md text-xs font-semibold border border-border text-foreground hover:bg-muted/50 disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                )}
             </div>

             {/* Right Main Panel - Workspace */}
             <div className={`w-full lg:w-[65%] flex-col glass-panel rounded-2xl border border-border shadow-sm bg-card overflow-hidden ${!selectedReview ? 'hidden lg:flex' : 'flex'}`}>
                {!selectedReview ? (
                   <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground p-8 text-center opacity-60">
                       <MessageSquare className="w-16 h-16 mb-4 opacity-50" />
                       <p className="text-xl font-bold text-foreground">Select a conversation</p>
                       <p className="text-sm mt-2 max-w-md">Choose a review from the queue to view details and draft your response.</p>
                   </div>
                ) : (
                   <div className="flex-1 overflow-y-auto flex flex-col">
                      {/* Review Details Header */}
                      <div className="p-4 lg:p-8 border-b border-border bg-muted/5">
                        <button 
                          onClick={() => setSelectedReviewId(null)}
                          className="lg:hidden mb-4 flex items-center gap-1.5 text-xs font-bold text-muted-foreground hover:text-foreground"
                        >
                          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
                          Back to Inbox
                        </button>
                        <div className="flex flex-wrap justify-between items-start gap-4 mb-6">
                           <div className="flex items-center gap-4 min-w-0">
                             {selectedReview.reviewer_profile_photo ? (
                               <img src={selectedReview.reviewer_profile_photo} alt={selectedReview.reviewer_name} className="w-14 h-14 rounded-full border-2 border-background shadow-md" referrerPolicy="no-referrer" />
                             ) : (
                               <div className="w-14 h-14 rounded-full bg-muted/40 border-2 border-background shadow-md flex items-center justify-center">
                                 <UserIcon className="h-6 w-6 text-muted-foreground" />
                               </div>
                             )}
                             <div className="min-w-0">
                               <h2 className="text-xl font-bold text-foreground">{selectedReview.reviewer_name}</h2>
                               <div className="flex flex-wrap items-center gap-2 mt-1">
                                 <span className="text-xs font-medium text-muted-foreground bg-background border border-border px-2 py-0.5 rounded-full">
                                   {locations.find(l => l.id === selectedReview.location_id)?.location_name || 'Unknown Location'}
                                 </span>
                                 <span className="text-xs text-muted-foreground">
                                   {new Date(selectedReview.review_created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                 </span>
                               </div>
                             </div>
                           </div>
                           
                           <div className="flex flex-col items-end gap-2">
                              <div className="flex items-center gap-1 bg-background border border-border px-3 py-1.5 rounded-full shadow-sm">
                                {Array.from({ length: 5 }).map((_, i) => (
                                  <Star key={i} className={`h-4 w-4 ${i < (selectedReview.rating || 0) ? 'text-amber-500 fill-amber-500' : 'text-muted-foreground/20'}`} />
                                ))}
                              </div>
                           </div>
                        </div>

                        {/* Tags & SLA */}
                        <div className="flex items-center gap-2 flex-wrap mb-6">
                          {renderSlaBadge(selectedReview)}
                          {selectedReview.sentiment && (
                            <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-bold ${
                              selectedReview.sentiment === 'Positive' ? 'bg-emerald-500/15 text-emerald-500 border border-emerald-500/30' :
                              selectedReview.sentiment === 'Neutral'  ? 'bg-slate-500/15 text-slate-400 border border-slate-500/30' :
                              selectedReview.sentiment === 'Negative' ? 'bg-red-500/15 text-red-500 border border-red-500/30' :
                              selectedReview.sentiment === 'Angry'    ? 'bg-rose-700/20 text-rose-400 border border-rose-700/40' :
                              'bg-muted/20 text-muted-foreground border border-border'
                            }`}>
                              {selectedReview.sentiment}
                            </span>
                          )}
                          {selectedReview.issue_category && (
                            <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold bg-slate-700/10 text-primary border border-primary/20">
                              {selectedReview.issue_category}
                            </span>
                          )}
                        </div>

                        {/* The Review Comment */}
                        <div className="bg-background border border-border rounded-2xl p-6 shadow-sm relative">
                           <div className="absolute -top-3 left-6 bg-card px-2 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Customer Wrote</div>
                           {selectedReview.comment ? (
                             <p className="text-foreground text-sm leading-relaxed whitespace-pre-wrap">
                               &ldquo;{selectedReview.comment}&rdquo;
                             </p>
                           ) : (
                             <p className="text-muted-foreground italic text-sm">Customer left a star rating with no comment.</p>
                           )}
                        </div>
                      </div>

                      {/* Reply Workspace */}
                      <div className="p-6 lg:p-8 flex-1 bg-card">
                         {selectedReview.is_replied ? (
                           <div className="bg-primary/5 border border-primary/20 rounded-2xl p-6 relative">
                             <div className="absolute -top-3 left-6 bg-card px-2 text-[10px] font-bold uppercase tracking-widest text-primary flex items-center gap-1">
                               <CheckCircle2 className="w-3 h-3" /> Replied
                             </div>
                             <p className="text-foreground text-sm leading-relaxed whitespace-pre-wrap mt-2">
                               {selectedReview.reply_text}
                             </p>
                             <div className="mt-4 pt-4 border-t border-primary/10 flex items-center justify-between text-xs text-muted-foreground">
                               <span>Responded on {selectedReview.reply_created_at ? new Date(selectedReview.reply_created_at).toLocaleDateString() : 'Unknown date'}</span>
                             </div>
                           </div>
                         ) : generatedReplies[selectedReview.id] ? (
                            /* AI Generated Reply Active Workspace */
                            <div className="space-y-4 animate-fade-up">
                              <div className="flex items-center justify-between bg-purple-500/10 border border-purple-500/20 rounded-xl p-3">
                                <div className="flex items-center gap-3">
                                  <div className="bg-purple-500/20 p-1.5 rounded-lg text-purple-400">
                                    <Sparkles className="w-4 h-4" />
                                  </div>
                                  <span className="text-sm font-bold text-foreground">AI Draft Generated</span>
                                </div>
                                <span className={`text-xs font-semibold ${generatedReplies[selectedReview.id].reply.trim().split(/\s+/).filter(Boolean).length > 80 ? 'text-amber-500' : 'text-muted-foreground'}`}>
                                  {generatedReplies[selectedReview.id].reply.trim().split(/\s+/).filter(Boolean).length} words
                                </span>
                              </div>

                              {generatedReplies[selectedReview.id].manualReviewRequired && (
                                <div className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-amber-500/10 text-amber-500 border border-amber-500/30 w-full">
                                  <AlertTriangle className="w-4 h-4" /> Please review carefully before sending.
                                </div>
                              )}

                              {generatedReplies[selectedReview.id].variants && (
                                <div className="flex flex-wrap gap-2">
                                  {([
                                    ['recommended', 'Recommended'],
                                    ['short', 'Shorter'],
                                    ['warm_or_professional', 'Alternative'],
                                  ] as const).map(([key, label]) => {
                                    const v = generatedReplies[selectedReview.id].variants![key]
                                    if (!v) return null;
                                    const active = generatedReplies[selectedReview.id].reply === v
                                    return (
                                      <button
                                        key={key}
                                        type="button"
                                        onClick={() => setGeneratedReplies({
                                          ...generatedReplies,
                                          [selectedReview.id]: { ...generatedReplies[selectedReview.id], reply: v },
                                        })}
                                        className={`px-4 py-1.5 rounded-full text-xs font-bold transition-all border ${
                                          active 
                                            ? 'bg-purple-500 text-white border-purple-500 shadow-sm' 
                                            : 'bg-background text-muted-foreground border-border hover:border-purple-500/40 hover:text-foreground'
                                        }`}
                                      >
                                        {label}
                                      </button>
                                    )
                                  })}
                                </div>
                              )}
                              
                              <textarea
                                value={generatedReplies[selectedReview.id].reply}
                                onChange={(e) => {
                                  setGeneratedReplies({
                                    ...generatedReplies,
                                    [selectedReview.id]: {
                                      ...generatedReplies[selectedReview.id],
                                      reply: e.target.value
                                    }
                                  });
                                }}
                                className="min-h-[200px] w-full rounded-2xl border border-input bg-background text-foreground p-5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500/50 shadow-inner resize-y leading-relaxed"
                              />
                              
                              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end mt-4">
                                <button
                                  onClick={() => {
                                    const newReplies = { ...generatedReplies };
                                    delete newReplies[selectedReview.id];
                                    setGeneratedReplies(newReplies);
                                  }}
                                  className="px-6 py-2.5 text-sm font-bold text-muted-foreground hover:text-foreground transition-colors rounded-xl"
                                >
                                  Discard Draft
                                </button>
                                <button
                                  onClick={() => handlePostAiReply(selectedReview.id)}
                                  disabled={replying || !generatedReplies[selectedReview.id].reply.trim()}
                                  className="flex items-center justify-center gap-2 px-8 py-2.5 rounded-xl text-sm font-bold text-white bg-gradient-to-r from-purple-600 to-indigo-600 hover:brightness-110 shadow-md shadow-purple-500/20 disabled:opacity-50 transition-all"
                                >
                                  {replying ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                  {replying ? 'Sending...' : 'Send AI Reply'}
                                </button>
                              </div>
                            </div>
                         ) : replyingTo === selectedReview.id ? (
                            /* Manual Reply Active Workspace */
                            <div className="space-y-4 animate-fade-up">
                              {selectedReview.suggested_templates && selectedReview.suggested_templates.length > 0 && (
                                <div className="mb-4">
                                  <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-3">Quick Insert Templates</p>
                                  <div className="flex flex-wrap gap-2">
                                    {selectedReview.suggested_templates.map(template => (
                                      <button
                                        key={template.id}
                                        onClick={() => {
                                          const text = resolveTemplateVariables(template.body, selectedReview.reviewer_name, selectedReview.location_name, { rating: String(selectedReview.rating ?? '') })
                                          if (replyText.trim()) {
                                            setPendingTemplate({ id: template.id, text })
                                            return
                                          }
                                          setReplyText(text)
                                          setReplyingTemplateId(template.id)
                                        }}
                                        className={`inline-flex items-center px-4 py-1.5 rounded-full border text-xs font-bold transition-all ${
                                          replyingTemplateId === template.id
                                            ? 'border-primary bg-primary text-primary-foreground shadow-sm'
                                            : 'bg-background text-muted-foreground border-border hover:border-primary/40 hover:text-foreground'
                                        }`}
                                      >
                                        {template.title}
                                      </button>
                                    ))}
                                  </div>
                                </div>
                              )}
                              
                              <textarea
                                value={replyText}
                                onChange={(e) => {
                                  setReplyText(e.target.value)
                                  if (replyingTemplateId) setReplyingTemplateId(null)
                                }}
                                placeholder="Type your response here..."
                                className="min-h-[150px] w-full rounded-2xl border border-input bg-background text-foreground p-5 text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 shadow-inner resize-y leading-relaxed"
                              />
                              
                              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end mt-4">
                                <button
                                  onClick={() => { setReplyingTo(null); setReplyText(''); setReplyingTemplateId(null); }}
                                  className="px-6 py-2.5 text-sm font-bold text-muted-foreground hover:text-foreground transition-colors rounded-xl"
                                >
                                  Cancel
                                </button>
                                <button
                                  onClick={() => handlePostReply(selectedReview.id)}
                                  disabled={replying || !replyText.trim()}
                                  className="flex items-center justify-center gap-2 px-8 py-2.5 rounded-xl text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 shadow-md disabled:opacity-50 transition-all"
                                >
                                  {replying ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                                  {replying ? 'Sending...' : 'Post Reply'}
                                </button>
                              </div>
                            </div>
                         ) : userRole !== 'Viewer' ? (
                            /* Idle Workspace - Call to Actions */
                            <div className="flex flex-col items-center justify-center h-full pt-4">
                               <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full max-w-lg">
                                  <button
                                    onClick={() => handleGenerateReply(selectedReview.id)}
                                    disabled={generatingFor === selectedReview.id}
                                    className="group relative flex flex-col items-center justify-center gap-3 p-6 rounded-2xl border border-purple-500/30 bg-purple-500/5 hover:bg-purple-500/10 transition-all overflow-hidden"
                                  >
                                    <div className="absolute inset-0 bg-gradient-to-br from-purple-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                                    {generatingFor === selectedReview.id ? (
                                      <RefreshCw className="h-8 w-8 text-purple-500 animate-spin" />
                                    ) : (
                                      <Sparkles className="h-8 w-8 text-purple-500 group-hover:scale-110 transition-transform" />
                                    )}
                                    <div className="text-center">
                                      <span className="block text-sm font-extrabold text-foreground mb-1">Generate AI Magic</span>
                                      <span className="block text-xs text-muted-foreground">Draft a perfect response in seconds</span>
                                    </div>
                                  </button>
                                  
                                  <button
                                    onClick={() => { setReplyingTo(selectedReview.id); setReplyText(''); }}
                                    className="group relative flex flex-col items-center justify-center gap-3 p-6 rounded-2xl border border-border bg-background hover:border-primary/40 hover:bg-muted/10 transition-all"
                                  >
                                    <MessageSquare className="h-8 w-8 text-muted-foreground group-hover:text-primary group-hover:scale-110 transition-all" />
                                    <div className="text-center">
                                      <span className="block text-sm font-extrabold text-foreground mb-1">Write Manually</span>
                                      <span className="block text-xs text-muted-foreground">Type your own response</span>
                                    </div>
                                  </button>
                               </div>

                               {selectedReview.suggested_templates && selectedReview.suggested_templates.length > 0 && (
                                 <div className="mt-8 w-full max-w-lg text-center animate-fade-up" style={{ animationDelay: '100ms', opacity: 0 }}>
                                   <p className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest mb-3">Or use a Quick Template</p>
                                   <div className="flex flex-wrap justify-center gap-2">
                                     {selectedReview.suggested_templates.map(template => (
                                       <button
                                         key={template.id}
                                         onClick={() => {
                                           const text = resolveTemplateVariables(template.body, selectedReview.reviewer_name, selectedReview.location_name, { rating: String(selectedReview.rating ?? '') })
                                           setReplyText(text)
                                           setReplyingTemplateId(template.id)
                                           setReplyingTo(selectedReview.id)
                                         }}
                                         className="inline-flex items-center px-4 py-1.5 rounded-full border text-xs font-bold transition-all bg-background text-muted-foreground border-border hover:border-primary/40 hover:text-foreground shadow-sm"
                                       >
                                         {template.title}
                                       </button>
                                     ))}
                                   </div>
                                 </div>
                               )}
                            </div>
                         ) : (
                           <div className="flex flex-col items-center justify-center h-full opacity-60">
                             <UserIcon className="w-12 h-12 mb-2 text-muted-foreground" />
                             <p className="text-sm font-bold">Viewer Access</p>
                             <p className="text-xs text-muted-foreground">You do not have permission to reply.</p>
                           </div>
                         )}
                      </div>
                   </div>
                )}
             </div>
          </div>

          {/* SLA Modal */}
          {showSlaModal && (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 sm:backdrop-blur-sm animate-in fade-in duration-200">
              <div className="bg-card border border-border w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl p-6 shadow-2xl animate-in slide-in-from-bottom-4 sm:slide-in-from-bottom-0 sm:zoom-in-95">
                <h3 className="text-xl font-bold text-foreground mb-2">Enable SLA Tracking</h3>
                <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
                  Start tracking response times from today? Historical reviews will remain visible but will not affect SLA metrics or rankings.
                </p>
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
                  <button
                    onClick={() => setShowSlaModal(false)}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-6 py-2.5 rounded-xl text-sm font-bold text-muted-foreground hover:bg-muted/50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleEnableSla}
                    disabled={enablingSla}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-6 py-2.5 rounded-xl text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
                  >
                    {enablingSla ? 'Enabling...' : 'Enable from Today'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Template Overwrite Modal */}
          {pendingTemplate && (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 sm:backdrop-blur-sm animate-in fade-in duration-200">
              <div className="bg-card border border-border w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-2xl p-6 shadow-2xl animate-in slide-in-from-bottom-4 sm:slide-in-from-bottom-0 sm:zoom-in-95">
                <h3 className="text-xl font-bold text-foreground mb-2">Replace your draft?</h3>
                <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
                  Applying this template will overwrite the reply you&apos;ve already started typing. This cannot be undone.
                </p>
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
                  <button
                    onClick={() => setPendingTemplate(null)}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-6 py-2.5 rounded-xl text-sm font-bold text-muted-foreground hover:bg-muted/50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => {
                      setReplyText(pendingTemplate.text)
                      setReplyingTemplateId(pendingTemplate.id)
                      setPendingTemplate(null)
                    }}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-6 py-2.5 rounded-xl text-sm font-bold text-primary-foreground bg-primary hover:bg-primary/90 transition-colors shadow-sm"
                  >
                    Replace Draft
                  </button>
                </div>
              </div>
            </div>
          )}
          </>)}

      </main>
    </div>
  )
}
