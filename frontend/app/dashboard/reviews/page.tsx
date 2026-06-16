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
} from 'lucide-react'

import { resolveTemplateVariables } from '@/lib/utils/template-utils'

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
  const [reviews, setReviews] = useState<Review[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  
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
  const [generatedReplies, setGeneratedReplies] = useState<Record<number, { reply: string; tone: string }>>({})
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
      const response = await api.post<{ review_id: number; generated_reply: string; tone: string }>(
        `/reviews/${reviewId}/generate-reply`
      )
      setGeneratedReplies(prev => ({
        ...prev,
        [reviewId]: {
          reply: response.generated_reply,
          tone: response.tone
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


  return (
    <div className={locationId ? "" : "min-h-screen bg-background text-foreground"}>
      
      <main className={locationId ? "space-y-6" : "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8"}>
          
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            {!locationId && (<div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground flex items-center gap-2">
                <MessageSquare className="h-7 w-7 sm:h-8 sm:w-8 text-primary shrink-0" />
                Customer Reviews
              </h1>
              <p className="text-muted-foreground mt-2">Manage and respond to Google Business Profile reviews.</p>
            </div>)}
            
            {userRole !== 'Viewer' && (
              <div className="flex items-center gap-2 flex-wrap">
                <button
                  onClick={handleTriggerSync}
                  disabled={syncing}
                  className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-4 py-2 min-h-[44px] sm:min-h-0 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
                  <span>{syncing ? 'Syncing...' : 'Sync Reviews'}</span>
                </button>
                {filterLocation !== '' && (
                  <button
                    onClick={handleRetag}
                    disabled={retagging || retagDisabled}
                    className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-4 py-2 min-h-[44px] sm:min-h-0 rounded-lg text-sm font-semibold text-teal-300 border border-teal-500/40 hover:bg-teal-500/10 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`h-4 w-4 ${retagging ? 'animate-spin' : ''}`} />
                    <span>{retagging ? 'Retagging...' : 'Retag Sentiment'}</span>
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Reputation KPI row — avg rating, total reviews, response rate */}
          {reviewSummary && (
            <div className="grid grid-cols-3 gap-3 sm:gap-4">
              <div className="glass-panel p-4 sm:p-5 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-amber-400/10 text-amber-400 shrink-0">
                  <Star className="h-4 w-4 sm:h-5 sm:w-5 fill-amber-400" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl sm:text-2xl font-extrabold text-foreground leading-none">
                    {reviewSummary.avg_rating && reviewSummary.avg_rating > 0 ? reviewSummary.avg_rating.toFixed(1) : '—'}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 truncate">Avg rating</div>
                </div>
              </div>

              <div className="glass-panel p-4 sm:p-5 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-sky-400/10 text-sky-400 shrink-0">
                  <MessageCircle className="h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl sm:text-2xl font-extrabold text-foreground leading-none tabular-nums">
                    {reviewSummary.total_reviews_all_time.toLocaleString()}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 truncate">Total reviews</div>
                </div>
              </div>

              <div className="glass-panel p-4 sm:p-5 flex items-center gap-3">
                <div className="p-2 rounded-lg bg-emerald-400/10 text-emerald-400 shrink-0">
                  <Send className="h-4 w-4 sm:h-5 sm:w-5" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl sm:text-2xl font-extrabold text-foreground leading-none">
                    {reviewSummary.response_rate !== null && reviewSummary.response_rate !== undefined ? `${reviewSummary.response_rate.toFixed(0)}%` : '—'}
                  </div>
                  <div className="text-[11px] text-muted-foreground mt-1 truncate">Response rate</div>
                </div>
              </div>
            </div>
          )}

          {errorAlert && (
            <div className="flex items-center gap-3 rounded-xl bg-red-500/10 border border-red-500/20 p-4 text-sm font-medium text-red-400">
              <AlertTriangle className="h-5 w-5 shrink-0" />
              <span>{errorAlert}</span>
            </div>
          )}

          {successAlert && (
            <div className="flex items-center gap-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-4 text-sm font-medium text-emerald-400">
              <CheckCircle2 className="h-5 w-5 shrink-0" />
              <span>{successAlert}</span>
            </div>
          )}

          {/* Filters */}
          <div className="bg-card border border-border p-4 rounded-xl shadow-sm flex gap-3 overflow-x-auto sm:flex-wrap sm:items-center sm:gap-4 sm:overflow-visible">
            <div className="flex flex-col gap-1.5 shrink-0">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Rating</label>
              <select
                className="bg-background border border-input rounded-lg text-sm px-3 min-h-[44px] py-1.5 sm:min-h-0 text-foreground outline-none focus:ring-1 focus:ring-primary"
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
            </div>

            <div className="flex flex-col gap-1.5 shrink-0">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Status</label>
              <select
                className="bg-background border border-input rounded-lg text-sm px-3 min-h-[44px] py-1.5 sm:min-h-0 text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={filterReplied}
                onChange={e => setFilterReplied(e.target.value as any)}
              >
                <option value="all">All Reviews</option>
                <option value="unreplied">Needs Reply</option>
                <option value="replied">Replied</option>
              </select>
            </div>

            {!locationId && (<div className="flex flex-col gap-1.5 shrink-0">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</label>
              <select
                className="bg-background border border-input rounded-lg text-sm px-3 min-h-[44px] py-1.5 sm:min-h-0 text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={filterLocation}
                onChange={e => setFilterLocation(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">All Locations</option>
                {locations.map(loc => (
                  <option key={loc.id} value={loc.id}>{loc.location_name}</option>
                ))}
              </select>
            </div>)}

            <div className="flex flex-col gap-1.5 shrink-0">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Sentiment</label>
              <select
                className="bg-background border border-input rounded-lg text-sm px-3 min-h-[44px] py-1.5 sm:min-h-0 text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={filterSentiment}
                onChange={e => setFilterSentiment(e.target.value)}
              >
                <option value="">All Sentiments</option>
                <option value="Positive">Positive</option>
                <option value="Neutral">Neutral</option>
                <option value="Negative">Negative</option>
                <option value="Angry">Angry</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5 shrink-0">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Category</label>
              <select
                className="bg-background border border-input rounded-lg text-sm px-3 min-h-[44px] py-1.5 sm:min-h-0 text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={filterCategory}
                onChange={e => { setFilterCategory(e.target.value); setCurrentPage(1); }}
              >
                <option value="">All Categories</option>
                <option value="Staff Praise">Staff Praise</option>
                <option value="Service Issue">Service Issue</option>
                <option value="Pricing Concern">Pricing Concern</option>
                <option value="Cleanliness">Cleanliness</option>
                <option value="Delivery Issue">Delivery Issue</option>
                <option value="Wait Time">Wait Time</option>
                <option value="Product Quality">Product Quality</option>
                <option value="General Feedback">General Feedback</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5 shrink-0">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">SLA Tier</label>
              <select
                className="bg-background border border-input rounded-lg text-sm px-3 min-h-[44px] py-1.5 sm:min-h-0 text-foreground outline-none focus:ring-1 focus:ring-primary"
                value={filterSlaTier}
                onChange={e => { setFilterSlaTier(e.target.value); setCurrentPage(1); }}
              >
                <option value="">All Tiers</option>
                <option value="Best">Best</option>
                <option value="Good">Good</option>
                <option value="Average">Average</option>
                <option value="Poor">Poor</option>
              </select>
            </div>

            <div className="flex items-center gap-2 shrink-0 sm:pt-5">
              <label className="text-sm font-bold text-foreground flex items-center gap-2 cursor-pointer whitespace-nowrap min-h-[44px] sm:min-h-0">
                <input
                  type="checkbox"
                  className="rounded bg-background border-input text-primary focus:ring-primary h-5 w-5 sm:h-4 sm:w-4"
                  checked={filterOverdue}
                  onChange={e => { setFilterOverdue(e.target.checked); setCurrentPage(1); }}
                />
                Overdue Only
              </label>
            </div>
          </div>

          {filterLocation !== '' && slaMetrics && (
            <div className="bg-card shadow-sm border border-border p-4 rounded-xl flex items-center justify-between">
              {!slaMetrics.sla_enabled ? (
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between w-full">
                  <span className="text-sm text-muted-foreground">SLA Tracking is not enabled for this location.</span>
                  <button onClick={() => setShowSlaModal(true)} className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 transition-colors">Enable SLA Tracking</button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-6">
                  <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Avg Response</span>
                    <span className="text-sm font-semibold text-foreground">
                      {slaMetrics.avg_response_hours !== null ? `${slaMetrics.avg_response_hours}h — ${slaMetrics.avg_sla_tier}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Replied</span>
                    <span className="text-sm font-semibold text-foreground">{slaMetrics.total_replied}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Overdue</span>
                    <span className="text-sm font-semibold text-red-400">{slaMetrics.overdue_count}</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Pending</span>
                    <span className="text-sm font-semibold text-amber-400">{slaMetrics.pending_count}</span>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Reviews List */}
          {loading ? (
             <div className="flex h-48 w-full items-center justify-center rounded-xl border border-border bg-card shadow-sm">
               <RefreshCw className="h-6 w-6 animate-spin text-primary" />
             </div>
          ) : reviews.length === 0 ? (
             <div className="flex flex-col items-center justify-center p-12 text-center rounded-xl border border-border bg-card shadow-sm">
                <MessageCircle className="h-10 w-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm font-bold text-foreground">No reviews found</p>
                <p className="text-xs text-muted-foreground mt-1">Try adjusting your filters or sync reviews.</p>
             </div>
          ) : (
            <div className="grid gap-6">
              {reviews.map(review => (
                <div key={review.id} className="bg-card shadow-sm border border-border rounded-xl p-5 space-y-4">
                  
                  <div className="flex justify-between items-start gap-4">
                    <div className="flex items-center gap-3">
                      {review.reviewer_profile_photo ? (
                        <img src={review.reviewer_profile_photo} alt={review.reviewer_name} className="w-10 h-10 rounded-full border border-border" referrerPolicy="no-referrer" />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-muted/40 border border-border flex items-center justify-center">
                          <UserIcon className="h-5 w-5 text-muted-foreground" />
                        </div>
                      )}
                      <div className="min-w-0">
                        <h4 className="font-bold text-foreground">{review.reviewer_name}</h4>
                        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                          <span className="text-xs text-muted-foreground">{new Date(review.review_created_at).toLocaleDateString()}</span>
                          <span className="text-xs sm:text-[10px] bg-muted/40 px-2 py-0.5 rounded-full text-primary font-medium">
                            {locations.find(l => l.id === review.location_id)?.location_name || 'Unknown Location'}
                          </span>
                        </div>
                      </div>
                    </div>
                    
                        <div className="flex flex-col items-end gap-2">
                      <div className="flex items-center gap-1">
                        {Array.from({ length: 5 }).map((_, i) => (
                          <Star key={i} className={`h-4 w-4 ${i < (review.rating || 0) ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground/30'}`} />
                        ))}
                      </div>
                      {/* Sentiment badge + category tag + SLA badge */}
                      <div className="flex items-center gap-1.5 flex-wrap justify-end">
                        {renderSlaBadge(review)}
                        {review.sentiment && (
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs sm:text-[10px] font-semibold ${
                            review.sentiment === 'Positive' ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' :
                            review.sentiment === 'Neutral'  ? 'bg-slate-500/15 text-slate-400 border border-slate-500/30' :
                            review.sentiment === 'Negative' ? 'bg-red-500/15 text-red-400 border border-red-500/30' :
                            review.sentiment === 'Angry'    ? 'bg-rose-700/20 text-rose-300 border border-rose-700/40' :
                            'bg-muted/20 text-muted-foreground border border-border'
                          }`}>
                            {review.sentiment}
                          </span>
                        )}
                        {review.issue_category && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs sm:text-[10px] font-medium bg-slate-700/40 text-blue-300 border border-slate-600/50">
                            {review.issue_category}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {review.comment && (
                    <p className="text-sm text-foreground/90 leading-relaxed bg-muted/20 p-4 rounded-lg border border-border/50">
                      &ldquo;{review.comment}&rdquo;
                    </p>
                  )}

                  <div className="pt-2">
                    {review.is_replied ? (
                      <div className="pl-4 border-l-2 border-primary/50 space-y-1 mt-2">
                        <span className="text-xs sm:text-[10px] font-bold uppercase tracking-wider text-primary">Your Reply</span>
                        <p className="text-sm text-muted-foreground bg-primary/5 p-3 rounded-r-lg border border-primary/10">
                          {review.reply_text}
                        </p>
                      </div>
                    ) : generatedReplies[review.id] ? (
                      <div className="space-y-3 mt-4 bg-muted/20 p-4 rounded-xl border border-primary/20">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-semibold text-muted-foreground">AI Tone:</span>
                            {generatedReplies[review.id].tone === 'grateful' && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
                                Warm & Grateful
                              </span>
                            )}
                            {generatedReplies[review.id].tone === 'neutral' && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-500/15 text-blue-400 border border-blue-500/30">
                                Professional
                              </span>
                            )}
                            {generatedReplies[review.id].tone === 'empathetic' && (
                              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-500/15 text-amber-400 border border-amber-500/30">
                                Empathetic
                              </span>
                            )}
                          </div>
                          <span className={`text-xs ${generatedReplies[review.id].reply.trim().split(/\s+/).filter(Boolean).length > 100 ? 'text-amber-500 font-semibold' : 'text-muted-foreground'}`}>
                            {generatedReplies[review.id].reply.trim().split(/\s+/).filter(Boolean).length} words
                          </span>
                        </div>
                        <textarea
                          value={generatedReplies[review.id].reply}
                          onChange={(e) => {
                            setGeneratedReplies({
                              ...generatedReplies,
                              [review.id]: {
                                ...generatedReplies[review.id],
                                reply: e.target.value
                              }
                            });
                          }}
                          className="min-h-[100px] w-full rounded-lg border border-input bg-background text-foreground p-3 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
                        />
                        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:gap-3 sm:justify-end">
                          <button
                            onClick={() => {
                              const newReplies = { ...generatedReplies };
                              delete newReplies[review.id];
                              setGeneratedReplies(newReplies);
                              const newErrors = { ...generationError };
                              delete newErrors[review.id];
                              setGenerationError(newErrors);
                            }}
                            className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors border border-border sm:border-transparent hover:border-border rounded-lg"
                          >
                            Discard
                          </button>
                          <button
                            onClick={() => handlePostAiReply(review.id)}
                            disabled={replying || !generatedReplies[review.id].reply.trim()}
                            className="w-full sm:w-auto min-h-[44px] sm:min-h-0 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors"
                          >
                            <Send className="h-4 w-4" />
                            {replying ? 'Sending...' : 'Send Reply'}
                          </button>
                        </div>
                      </div>
                    ) : replyingTo === review.id ? (
                      <div className="space-y-3 mt-4">
                        {review.suggested_templates && review.suggested_templates.length > 0 && (
                          <div className="mb-3">
                            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">Quick Templates</p>
                            <div className="flex flex-wrap gap-2">
                              {review.suggested_templates.map(template => (
                                <button
                                  key={template.id}
                                  onClick={() => {
                                    const text = resolveTemplateVariables(template.body, review.reviewer_name, review.location_name)
                                    if (replyText.trim()) {
                                      setPendingTemplate({ id: template.id, text })
                                      return
                                    }
                                    setReplyText(text)
                                    setReplyingTemplateId(template.id)
                                  }}
                                  className={`inline-flex items-center px-2.5 py-1 rounded-full border text-xs font-medium transition-colors ${
                                    replyingTemplateId === template.id
                                      ? 'border-primary bg-primary text-primary-foreground ring-2 ring-primary/30'
                                      : 'border-primary/20 bg-primary/5 hover:bg-primary/10 text-primary'
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
                            if (replyingTemplateId) setReplyingTemplateId(null) // Unlink template if they edit it manually
                          }}
                          placeholder="Write your response..."
                          className="w-full bg-background border border-input rounded-lg p-3 text-sm text-foreground placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary min-h-[100px]"
                        />
                        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:gap-3 sm:justify-end">
                          <button
                            onClick={() => { setReplyingTo(null); setReplyText(''); setReplyingTemplateId(null); }}
                            className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors border border-border sm:border-0 rounded-lg"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handlePostReply(review.id)}
                            disabled={replying || !replyText.trim()}
                            className="w-full sm:w-auto min-h-[44px] sm:min-h-0 flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors"
                          >
                            <Send className="h-4 w-4" />
                            {replying ? 'Sending...' : 'Post Reply'}
                          </button>
                        </div>
                      </div>
                    ) : userRole !== 'Viewer' ? (
                      <div className="mt-4">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
                          <button
                            onClick={() => { setReplyingTo(review.id); setReplyText(''); }}
                            className="w-full sm:w-auto min-h-[44px] sm:min-h-0 flex items-center justify-center gap-2 px-4 py-2 sm:p-0 rounded-lg sm:rounded-none text-sm font-semibold text-primary-foreground sm:text-primary bg-primary sm:bg-transparent hover:bg-primary/90 sm:hover:bg-transparent sm:hover:text-primary/80 transition-colors"
                          >
                            Reply to Review
                            {review.suggested_templates && review.suggested_templates.length > 0 && (
                              <span className="inline-flex items-center px-1.5 py-0.5 rounded-full bg-primary/10 text-primary text-[10px] font-semibold leading-none">
                                {review.suggested_templates.length} template{review.suggested_templates.length > 1 ? 's' : ''}
                              </span>
                            )}
                          </button>
                          <button
                            onClick={() => handleGenerateReply(review.id)}
                            disabled={generatingFor === review.id}
                            className="w-full sm:w-auto min-h-[44px] sm:min-h-0 flex items-center justify-center gap-1.5 px-3 py-2 sm:py-1.5 rounded-lg text-sm sm:text-xs font-semibold text-purple-600 border border-purple-500/40 hover:bg-purple-500/10 disabled:opacity-50 transition-all"
                          >
                            {generatingFor === review.id ? (
                              <>
                                <RefreshCw className="h-3 w-3 animate-spin" />
                                <span>Generating...</span>
                              </>
                            ) : (
                              <span>Generate Reply</span>
                            )}
                          </button>
                        </div>
                        {generationError[review.id] && (
                          <p className="text-xs text-red-500 mt-2">
                            {generationError[review.id]}
                          </p>
                        )}
                      </div>
                    ) : null}
                  </div>
                  
                </div>
              ))}

              {totalPages > 1 && (
                <div className="flex justify-between items-center mt-6">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1 || loading}
                    className="px-4 py-2 min-h-[44px] sm:min-h-0 rounded-lg text-sm font-semibold border border-border text-foreground hover:bg-muted/50 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-muted-foreground">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages || loading}
                    className="px-4 py-2 min-h-[44px] sm:min-h-0 rounded-lg text-sm font-semibold border border-border text-foreground hover:bg-muted/50 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}

          {showSlaModal && (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 sm:backdrop-blur-sm">
              <div className="bg-card border border-border w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-xl p-6 shadow-2xl">
                <h3 className="text-xl font-bold text-foreground mb-2">Enable SLA Tracking</h3>
                <p className="text-sm text-muted-foreground mb-6">
                  Start tracking response times from today? Historical reviews will remain visible but will not affect SLA metrics or rankings.
                </p>
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
                  <button
                    onClick={() => setShowSlaModal(false)}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors border border-border sm:border-0"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleEnableSla}
                    disabled={enablingSla}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  >
                    {enablingSla ? 'Enabling...' : 'Enable from Today'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {pendingTemplate && (
            <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-black/50 sm:backdrop-blur-sm">
              <div className="bg-card border border-border w-full sm:max-w-md max-h-[90vh] overflow-y-auto rounded-t-2xl sm:rounded-xl p-6 shadow-2xl">
                <h3 className="text-xl font-bold text-foreground mb-2">Replace your reply?</h3>
                <p className="text-sm text-muted-foreground mb-6">
                  Applying this template will replace the reply you&apos;ve already written. This can&apos;t be undone.
                </p>
                <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end sm:gap-3">
                  <button
                    onClick={() => setPendingTemplate(null)}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold text-muted-foreground hover:text-foreground transition-colors border border-border sm:border-0"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => {
                      setReplyText(pendingTemplate.text)
                      setReplyingTemplateId(pendingTemplate.id)
                      setPendingTemplate(null)
                    }}
                    className="w-full sm:w-auto min-h-[44px] sm:min-h-0 px-4 py-2 rounded-lg text-sm font-semibold text-primary-foreground bg-primary hover:bg-primary/90 transition-colors"
                  >
                    Replace
                  </button>
                </div>
              </div>
            </div>
          )}

      </main>
    </div>
  )
}
