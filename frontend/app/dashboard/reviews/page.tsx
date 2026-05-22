'use client'

import { useEffect, useState } from 'react'
import AuthGuard from '@/components/AuthGuard'
import Navbar from '@/components/Navbar'
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
  review_created_at: string
}

interface ReviewListResponse {
  reviews: Review[]
  total: int
  page: int
  pages: int
}

export default function ReviewsPage() {
  const [reviews, setReviews] = useState<Review[]>([])
  const [locations, setLocations] = useState<Location[]>([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  
  // Filters
  const [filterRating, setFilterRating] = useState<number | ''>('')
  const [filterReplied, setFilterReplied] = useState<'all' | 'replied' | 'unreplied'>('all')
  const [filterLocation, setFilterLocation] = useState<number | ''>('')

  // Reply state
  const [replyingTo, setReplyingTo] = useState<number | null>(null)
  const [replyText, setReplyText] = useState('')
  const [replying, setReplying] = useState(false)

  // Alerts
  const [errorAlert, setErrorAlert] = useState('')
  const [successAlert, setSuccessAlert] = useState('')

  useEffect(() => {
    loadLocations()
  }, [])

  useEffect(() => {
    loadReviews()
  }, [filterRating, filterReplied, filterLocation])

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
      if (filterRating !== '') params.append('rating', filterRating.toString())
      if (filterReplied === 'replied') params.append('is_replied', 'true')
      if (filterReplied === 'unreplied') params.append('is_replied', 'false')
      if (filterLocation !== '') params.append('location_id', filterLocation.toString())

      const data = await api.get<ReviewListResponse>(`/reviews/?${params.toString()}`)
      setReviews(data.reviews || [])
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

  return (
    <AuthGuard>
      <div className="min-h-screen bg-background">
        <Navbar />
        
        <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-8">
          
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div>
              <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-2">
                <MessageSquare className="h-8 w-8 text-indigo-400" />
                Customer Reviews
              </h1>
              <p className="text-muted-foreground mt-2">Manage and respond to Google Business Profile reviews.</p>
            </div>
            
            <button
              onClick={handleTriggerSync}
              disabled={syncing}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`h-4 w-4 ${syncing ? 'animate-spin' : ''}`} />
              <span>{syncing ? 'Syncing...' : 'Sync Reviews'}</span>
            </button>
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
            
            <div className="flex flex-col gap-1.5">
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
            </div>
          </div>

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
                    
                    <div className="flex items-center gap-1">
                      {Array.from({ length: 5 }).map((_, i) => (
                        <Star key={i} className={`h-4 w-4 ${i < (review.rating || 0) ? 'text-yellow-500 fill-yellow-500' : 'text-muted-foreground/30'}`} />
                      ))}
                    </div>
                  </div>

                  {review.comment && (
                    <p className="text-sm text-white/90 leading-relaxed bg-muted/10 p-4 rounded-lg border border-border/50">
                      "{review.comment}"
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
                    ) : (
                      replyingTo === review.id ? (
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
                      ) : (
                        <button
                          onClick={() => { setReplyingTo(review.id); setReplyText(''); }}
                          className="text-sm font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
                        >
                          Reply to Review
                        </button>
                      )
                    )}
                  </div>
                  
                </div>
              ))}
            </div>
          )}

        </main>
      </div>
    </AuthGuard>
  )
}
