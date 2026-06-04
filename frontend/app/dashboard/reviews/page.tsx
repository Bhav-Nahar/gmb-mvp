'use client'

import { useEffect, useState } from 'react'
import AuthGuard from '@/components/AuthGuard'
import Navbar from '@/components/Navbar'
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
  const [showSlaModal, setShowSlaModal] = useState(false)
  const [enablingSla, setEnablingSla] = useState(false)

  // Reply state
  const [replyingTo, setReplyingTo] = useState<number | null>(null)
  const [replyText, setReplyText] = useState('')
  const [replying, setReplying] = useState(false)

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
      const updatedReview = await api.post<Review>(`/reviews/${reviewId}/reply`, {
        reply_text: replyText
      })
      
      setReviews(reviews.map(r => r.id === reviewId ? updatedReview : r))
      setSuccessAlert('Reply posted successfully!')
      setReplyingTo(null)
      setReplyText('')
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
    <AuthGuard>
      <div className={locationId ? "" : "min-h-screen bg-background"}>
        {!locationId && <Navbar />}
        
        <main className={locationId ? "space-y-6" : "mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8"}>
          
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            {!locationId && (<div>
              <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
                <MessageSquare className="h-8 w-8 text-indigo-400" />
                Customer Reviews
              </h1>
              <p className="text-muted-foreground mt-2">Manage and respond to Google Business Profile reviews.</p>
            </div>)}
            
            {userRole !== 'Viewer' && (
              <div className="flex items-center gap-2">
                <button
                  onClick={handleTriggerSync}
                  disabled={syncing}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
                  <span>{syncing ? 'Syncing...' : 'Sync Reviews'}</span>
                </button>
                {filterLocation !== '' && (
                  <button
                    onClick={handleRetag}
                    disabled={retagging || retagDisabled}
                    className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-teal-300 border border-teal-500/40 hover:bg-teal-500/10 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw className={`h-4 w-4 ${retagging ? 'animate-spin' : ''}`} />
                    <span>{retagging ? 'Retagging...' : 'Retag Sentiment'}</span>
                  </button>
                )}
              </div>
            )}
          </div>

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
          <div className="glass-panel border border-border p-4 rounded-xl flex flex-wrap items-center gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Rating</label>
              <select 
                className="bg-muted/30 border border-border rounded-lg text-sm px-3 py-1.5 text-white outline-none focus:ring-1 focus:ring-indigo-500"
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
            
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Status</label>
              <select 
                className="bg-muted/30 border border-border rounded-lg text-sm px-3 py-1.5 text-white outline-none focus:ring-1 focus:ring-indigo-500"
                value={filterReplied}
                onChange={e => setFilterReplied(e.target.value as any)}
              >
                <option value="all">All Reviews</option>
                <option value="unreplied">Needs Reply</option>
                <option value="replied">Replied</option>
              </select>
            </div>
            
            {!locationId && (<div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Location</label>
              <select 
                className="bg-muted/30 border border-border rounded-lg text-sm px-3 py-1.5 text-white outline-none focus:ring-1 focus:ring-indigo-500"
                value={filterLocation}
                onChange={e => setFilterLocation(e.target.value ? Number(e.target.value) : '')}
              >
                <option value="">All Locations</option>
                {locations.map(loc => (
                  <option key={loc.id} value={loc.id}>{loc.location_name}</option>
                ))}
              </select>
            </div>)}

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Sentiment</label>
              <select
                className="bg-muted/30 border border-border rounded-lg text-sm px-3 py-1.5 text-white outline-none focus:ring-1 focus:ring-indigo-500"
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

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Category</label>
              <select
                className="bg-muted/30 border border-border rounded-lg text-sm px-3 py-1.5 text-white outline-none focus:ring-1 focus:ring-indigo-500"
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

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">SLA Tier</label>
              <select
                className="bg-muted/30 border border-border rounded-lg text-sm px-3 py-1.5 text-white outline-none focus:ring-1 focus:ring-indigo-500"
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
            
            <div className="flex items-center gap-2 pt-5">
              <label className="text-sm font-bold text-white flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded bg-muted/30 border-border text-indigo-500 focus:ring-indigo-500"
                  checked={filterOverdue}
                  onChange={e => { setFilterOverdue(e.target.checked); setCurrentPage(1); }}
                />
                Overdue Only
              </label>
            </div>
          </div>

          {filterLocation !== '' && slaMetrics && (
            <div className="glass-panel border border-border p-4 rounded-xl flex items-center justify-between">
              {!slaMetrics.sla_enabled ? (
                <div className="flex items-center justify-between w-full">
                  <span className="text-sm text-muted-foreground">SLA Tracking is not enabled for this location.</span>
                  <button onClick={() => setShowSlaModal(true)} className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors">Enable SLA Tracking</button>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-6">
                  <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Avg Response</span>
                    <span className="text-sm font-semibold text-white">
                      {slaMetrics.avg_response_hours !== null ? `${slaMetrics.avg_response_hours}h — ${slaMetrics.avg_sla_tier}` : 'N/A'}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Replied</span>
                    <span className="text-sm font-semibold text-white">{slaMetrics.total_replied}</span>
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
             <div className="flex h-48 w-full items-center justify-center rounded-2xl border border-border glass-panel">
               <RefreshCw className="h-6 w-6 animate-spin text-indigo-500" />
             </div>
          ) : reviews.length === 0 ? (
             <div className="flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-border glass-panel">
                <MessageCircle className="h-10 w-10 text-muted-foreground/30 mb-3" />
                <p className="text-sm font-bold text-white">No reviews found</p>
                <p className="text-xs text-muted-foreground mt-1">Try adjusting your filters or sync reviews.</p>
             </div>
          ) : (
            <div className="grid gap-6">
              {reviews.map(review => (
                <div key={review.id} className="glass-panel border border-border rounded-xl p-5 space-y-4">
                  
                  <div className="flex justify-between items-start gap-4">
                    <div className="flex items-center gap-3">
                      {review.reviewer_profile_photo ? (
                        <img src={review.reviewer_profile_photo} alt={review.reviewer_name} className="w-10 h-10 rounded-full border border-border" referrerPolicy="no-referrer" />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-muted/40 border border-border flex items-center justify-center">
                          <UserIcon className="h-5 w-5 text-muted-foreground" />
                        </div>
                      )}
                      <div>
                        <h4 className="font-bold text-white">{review.reviewer_name}</h4>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className="text-xs text-muted-foreground">{new Date(review.review_created_at).toLocaleDateString()}</span>
                          <span className="text-[10px] bg-muted/40 px-2 py-0.5 rounded-full text-indigo-300 font-medium">
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
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
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
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-700/40 text-blue-300 border border-slate-600/50">
                            {review.issue_category}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {review.comment && (
                    <p className="text-sm text-white/90 leading-relaxed bg-muted/10 p-4 rounded-lg border border-border/50">
                      &ldquo;{review.comment}&rdquo;
                    </p>
                  )}

                  <div className="pt-2">
                    {review.is_replied ? (
                      <div className="pl-4 border-l-2 border-indigo-500/50 space-y-1 mt-2">
                        <span className="text-[10px] font-bold uppercase tracking-wider text-indigo-400">Your Reply</span>
                        <p className="text-sm text-muted-foreground bg-indigo-500/5 p-3 rounded-r-lg border border-indigo-500/10">
                          {review.reply_text}
                        </p>
                      </div>
                    ) : generatedReplies[review.id] ? (
                      <div className="space-y-3 mt-4 bg-gray-900/50 p-4 rounded-xl border border-violet-500/20">
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
                          <span className={`text-xs ${generatedReplies[review.id].reply.trim().split(/\s+/).filter(Boolean).length > 100 ? 'text-amber-400 font-semibold' : 'text-muted-foreground'}`}>
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
                          className="min-h-[100px] w-full rounded-lg border border-gray-600 bg-gray-800 text-white p-3 text-sm focus:outline-none focus:ring-1 focus:ring-violet-500"
                        />
                        <div className="flex gap-3 justify-end">
                          <button
                            onClick={() => {
                              const newReplies = { ...generatedReplies };
                              delete newReplies[review.id];
                              setGeneratedReplies(newReplies);
                              const newErrors = { ...generationError };
                              delete newErrors[review.id];
                              setGenerationError(newErrors);
                            }}
                            className="px-4 py-2 text-sm font-semibold text-muted-foreground hover:text-white transition-colors border border-transparent hover:border-gray-700 rounded-lg"
                          >
                            Discard
                          </button>
                          <button
                            onClick={() => handlePostAiReply(review.id)}
                            disabled={replying || !generatedReplies[review.id].reply.trim()}
                            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                          >
                            <Send className="h-4 w-4" />
                            {replying ? 'Sending...' : 'Send Reply'}
                          </button>
                        </div>
                      </div>
                    ) : replyingTo === review.id ? (
                      <div className="space-y-3 mt-4">
                        <textarea
                          value={replyText}
                          onChange={(e) => setReplyText(e.target.value)}
                          placeholder="Write your response..."
                          className="w-full bg-muted/20 border border-border rounded-lg p-3 text-sm text-white placeholder-muted-foreground focus:outline-none focus:ring-1 focus:ring-indigo-500 min-h-[100px]"
                        />
                        <div className="flex gap-3 justify-end">
                          <button
                            onClick={() => { setReplyingTo(null); setReplyText(''); }}
                            className="px-4 py-2 text-sm font-semibold text-muted-foreground hover:text-white transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            onClick={() => handlePostReply(review.id)}
                            disabled={replying || !replyText.trim()}
                            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                          >
                            <Send className="h-4 w-4" />
                            {replying ? 'Sending...' : 'Post Reply'}
                          </button>
                        </div>
                      </div>
                    ) : userRole !== 'Viewer' ? (
                      <div className="mt-4">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => { setReplyingTo(review.id); setReplyText(''); }}
                            className="text-sm font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
                          >
                            Reply to Review
                          </button>
                          <button
                            onClick={() => handleGenerateReply(review.id)}
                            disabled={generatingFor === review.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-violet-400 border border-violet-500/40 hover:bg-violet-500/10 disabled:opacity-50 transition-all"
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
                    className="px-4 py-2 rounded-lg text-sm font-semibold bg-muted/30 text-white disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <span className="text-sm text-muted-foreground">
                    Page {currentPage} of {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages || loading}
                    className="px-4 py-2 rounded-lg text-sm font-semibold bg-muted/30 text-white disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          )}

          {showSlaModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
              <div className="bg-background border border-border rounded-xl p-6 w-full max-w-md shadow-2xl">
                <h3 className="text-xl font-bold text-white mb-2">Enable SLA Tracking</h3>
                <p className="text-sm text-muted-foreground mb-6">
                  Start tracking response times from today? Historical reviews will remain visible but will not affect SLA metrics or rankings.
                </p>
                <div className="flex justify-end gap-3">
                  <button
                    onClick={() => setShowSlaModal(false)}
                    className="px-4 py-2 rounded-lg text-sm font-semibold text-muted-foreground hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleEnableSla}
                    disabled={enablingSla}
                    className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors"
                  >
                    {enablingSla ? 'Enabling...' : 'Enable from Today'}
                  </button>
                </div>
              </div>
            </div>
          )}

        </main>
      </div>
    </AuthGuard>
  )
}
