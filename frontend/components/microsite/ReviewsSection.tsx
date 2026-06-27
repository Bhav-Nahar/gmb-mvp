'use client'

import React, { useState, useMemo, useRef, useEffect } from 'react'
import { 
  Star, ChevronLeft, ChevronRight, Grid, LayoutList, 
  Search, SlidersHorizontal, ArrowUpRight, MessageSquare,
  CheckCircle, ShieldAlert
} from 'lucide-react'

interface Review {
  reviewer_name: string
  reviewer_profile_photo?: string
  rating?: number
  comment?: string
  review_created_at: string
  reply_text?: string
  reply_created_at?: string
}

interface ReviewsSectionProps {
  reviews: Review[]
  averageRating?: number | null
  totalReviews?: number | null
  reviewUrl?: string | null
}

const getAvatarBgColor = (name: string) => {
  const colors = [
    'bg-red-100 text-red-700 border-red-200',
    'bg-orange-100 text-orange-700 border-orange-200',
    'bg-amber-100 text-amber-700 border-amber-200',
    'bg-emerald-100 text-emerald-700 border-emerald-200',
    'bg-teal-100 text-teal-700 border-teal-200',
    'bg-blue-100 text-blue-700 border-blue-200',
    'bg-indigo-100 text-indigo-700 border-indigo-200',
    'bg-purple-100 text-purple-700 border-purple-200',
    'bg-rose-100 text-rose-700 border-rose-200'
  ]
  const index = name ? name.charCodeAt(0) % colors.length : 0
  return colors[index]
}

export default function ReviewsSection({ 
  reviews, 
  averageRating, 
  totalReviews, 
  reviewUrl 
}: ReviewsSectionProps) {
  const [viewMode, setViewMode] = useState<'carousel' | 'grid'>('carousel')
  const [ratingFilter, setRatingFilter] = useState<'all' | number>('all')
  const [sortBy, setSortBy] = useState<'newest' | 'highest' | 'lowest'>('newest')
  const [searchTerm, setSearchTerm] = useState('')

  const scrollRef = useRef<HTMLDivElement>(null)
  const [canScrollLeft, setCanScrollLeft] = useState(false)
  const [canScrollRight, setCanScrollRight] = useState(true)
  const [activeDot, setActiveDot] = useState(0)

  const stats = useMemo(() => {
    const list = reviews || []
    const total = list.length
    const distribution = { 5: 0, 4: 0, 3: 0, 2: 0, 1: 0 }
    let sum = 0

    list.forEach(r => {
      const rating = Math.min(5, Math.max(1, Math.round(r.rating || 5))) as 5 | 4 | 3 | 2 | 1
      distribution[rating]++
      sum += r.rating || 5
    })

    const calculatedAvg = total > 0 ? (sum / total) : 5.0
    const rawAverage = averageRating != null ? Number(averageRating) : calculatedAvg
    const formattedAverage = parseFloat(rawAverage.toFixed(1))
    const displayAverage = rawAverage.toFixed(1)

    return {
      total: totalReviews || total,
      average: formattedAverage,
      displayAverage,
      distribution: Object.entries(distribution).map(([stars, count]) => ({
        stars: parseInt(stars),
        count,
        percentage: total > 0 ? Math.round((count / total) * 100) : 0
      })).reverse()
    }
  }, [reviews, averageRating, totalReviews])

  const filteredAndSortedReviews = useMemo(() => {
    let list = [...(reviews || [])]

    if (searchTerm.trim()) {
      const query = searchTerm.toLowerCase()
      list = list.filter(r => 
        r.reviewer_name.toLowerCase().includes(query) || 
        (r.comment && r.comment.toLowerCase().includes(query))
      )
    }

    if (ratingFilter !== 'all') {
      list = list.filter(r => Math.round(r.rating || 5) === ratingFilter)
    }

    list.sort((a, b) => {
      if (sortBy === 'newest') {
        return new Date(b.review_created_at).getTime() - new Date(a.review_created_at).getTime()
      }
      if (sortBy === 'highest') {
        return (b.rating || 5) - (a.rating || 5)
      }
      if (sortBy === 'lowest') {
        return (a.rating || 5) - (b.rating || 5)
      }
      return 0
    })

    return list
  }, [reviews, searchTerm, ratingFilter, sortBy])

  const checkScrollState = () => {
    if (scrollRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current
      setCanScrollLeft(scrollLeft > 10)
      setCanScrollRight(scrollLeft + clientWidth < scrollWidth - 10)

      if (clientWidth > 0) {
        const itemWidth = 320 + 20
        const currentDot = Math.round(scrollLeft / itemWidth)
        setActiveDot(currentDot)
      }
    }
  }

  useEffect(() => {
    const el = scrollRef.current
    if (el) {
      el.addEventListener('scroll', checkScrollState)
      checkScrollState()
      window.addEventListener('resize', checkScrollState)
    }
    return () => {
      if (el) el.removeEventListener('scroll', checkScrollState)
      window.removeEventListener('resize', checkScrollState)
    }
  }, [reviews, filteredAndSortedReviews, viewMode])

  const handleScroll = (direction: 'left' | 'right') => {
    if (scrollRef.current) {
      const { clientWidth } = scrollRef.current
      const amount = direction === 'left' ? -clientWidth * 0.75 : clientWidth * 0.75
      scrollRef.current.scrollBy({ left: amount, behavior: 'smooth' })
    }
  }

  if (!reviews || reviews.length === 0) return null

  const totalDots = Math.max(1, filteredAndSortedReviews.length)

  return (
    <section id="reviews" className="scroll-mt-28 relative">
      <div>
        
        {/* Header */}
        <div className="mb-10 animate-fade-up">
          <span className="text-xs font-bold tracking-[0.2em] text-primary uppercase">
            Testimonials
          </span>
          <h2 className="text-3xl sm:text-4xl font-black text-foreground tracking-tight mt-3 mb-4">
            What Customers Say
          </h2>
          <p className="text-muted-foreground max-w-2xl text-base leading-relaxed">
            Verified ratings and customer reviews pulled directly from Google Business Profile.
          </p>
        </div>

        {/* Aggregated Reviews Dashboard - High Contrast */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 bg-slate-900 text-white rounded-[2rem] p-8 sm:p-10 shadow-2xl mb-16 animate-fade-up" style={{ animationDelay: '100ms', opacity: 0 }}>
          {/* Main Scorecard */}
          <div className="flex flex-col items-center justify-center text-center lg:border-r lg:border-slate-700 lg:pr-8 py-4">
            <h3 className="text-6xl sm:text-7xl font-black tracking-tighter">
              {stats.displayAverage}
            </h3>
            <div className="flex items-center gap-1 mt-4">
              {[...Array(5)].map((_, i) => (
                <Star 
                  key={i} 
                  className={`w-6 h-6 ${i < Math.round(stats.average) ? 'fill-amber-400 text-amber-400 drop-shadow-[0_2px_4px_rgba(251,191,36,0.3)]' : 'text-slate-700 fill-slate-700'}`} 
                />
              ))}
            </div>
            <p className="text-sm font-medium text-slate-400 mt-4">
              Based on {stats.total} Google reviews
            </p>
            <div className="flex items-center gap-1.5 mt-5 text-[11px] font-bold text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 rounded-full px-4 py-1.5">
              <CheckCircle className="w-3.5 h-3.5" />
              100% Google Verified
            </div>
          </div>

          {/* Progress Bars */}
          <div className="flex flex-col gap-3 justify-center py-2 lg:px-4">
            {stats.distribution.map((d) => (
              <div key={d.stars} className="flex items-center gap-3 text-sm font-medium">
                <span className="text-slate-300 w-3 text-right">{d.stars}</span>
                <Star className="w-4 h-4 fill-amber-400 text-amber-400 shrink-0 drop-shadow-sm" />
                <div className="flex-grow h-2.5 bg-slate-800 rounded-full overflow-hidden">
                  <div 
                    className="h-full bg-amber-400 rounded-full transition-all duration-700 ease-out" 
                    style={{ width: `${d.percentage}%` }}
                  />
                </div>
                <span className="text-slate-400 w-9 text-right">{d.percentage}%</span>
              </div>
            ))}
          </div>

          {/* CTA Box */}
          <div className="flex flex-col items-center justify-center p-8 bg-slate-800/50 rounded-2xl border border-slate-700/50 text-center">
            <h4 className="font-bold text-white text-lg mb-2">Have you visited us?</h4>
            <p className="text-sm text-slate-400 mb-6 max-w-[240px] leading-relaxed">
              Your feedback helps us grow. Share your experience with the community today!
            </p>
            {reviewUrl ? (
              <a
                href={reviewUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="w-full inline-flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-bold py-4 px-6 rounded-xl shadow-lg hover:shadow-xl hover:-translate-y-0.5 transition-all group"
              >
                Write a Review
                <ArrowUpRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
              </a>
            ) : (
              <button
                disabled
                className="w-full inline-flex items-center justify-center gap-2 bg-slate-700 text-slate-500 text-sm font-bold py-4 px-6 rounded-xl cursor-not-allowed"
              >
                Reviews Read-Only
              </button>
            )}
          </div>
        </div>

        {/* Filter Controls Toolbar */}
        <div className="flex flex-col md:flex-row gap-4 justify-between items-center mb-10 glass-panel p-4 rounded-2xl animate-fade-up" style={{ animationDelay: '200ms', opacity: 0 }}>
          <div className="flex flex-col sm:flex-row items-center gap-4 w-full md:w-auto">
            <div className="flex bg-muted border border-border p-1 rounded-xl self-start sm:self-auto">
              <button
                onClick={() => setViewMode('carousel')}
                className={`p-2 rounded-lg transition-all ${
                  viewMode === 'carousel'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <LayoutList className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('grid')}
                className={`p-2 rounded-lg transition-all ${
                  viewMode === 'grid'
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <Grid className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-4 w-full md:w-auto">
            <div className="flex items-center gap-1.5 w-full sm:w-auto overflow-x-auto pb-1 sm:pb-0 scrollbar-none">
              <span className="text-[11px] font-bold text-muted-foreground uppercase tracking-wider shrink-0 mr-2 hidden sm:inline">Filter:</span>
              <button
                onClick={() => setRatingFilter('all')}
                className={`px-4 py-2 rounded-lg text-xs font-bold border transition-all ${
                  ratingFilter === 'all'
                    ? 'bg-foreground text-background border-foreground shadow-sm'
                    : 'bg-background border-border text-foreground hover:border-primary/40'
                }`}
              >
                All
              </button>
              {[5, 4, 3, 2, 1].map((stars) => (
                <button
                  key={stars}
                  onClick={() => setRatingFilter(stars)}
                  className={`px-3 py-2 rounded-lg text-xs font-bold border transition-all flex items-center gap-1 whitespace-nowrap ${
                    ratingFilter === stars
                      ? 'bg-foreground text-background border-foreground shadow-sm'
                      : 'bg-background border-border text-foreground hover:border-primary/40'
                  }`}
                >
                  {stars}★
                </button>
              ))}
            </div>

            <div className="relative w-full sm:w-auto self-start sm:self-auto">
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as any)}
                className="w-full sm:w-auto bg-background border border-border text-sm font-bold text-foreground px-4 py-2.5 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/30 transition-all appearance-none pr-10 cursor-pointer shadow-sm"
              >
                <option value="newest">Newest First</option>
                <option value="highest">Highest Rating</option>
                <option value="lowest">Lowest Rating</option>
              </select>
              <div className="absolute inset-y-0 right-4 flex items-center pointer-events-none text-muted-foreground">
                <SlidersHorizontal className="w-4 h-4" />
              </div>
            </div>
          </div>
        </div>

        {/* Content Renderers */}
        {filteredAndSortedReviews.length > 0 ? (
          viewMode === 'carousel' ? (
            <div className="relative group/carousel animate-fade-up" style={{ animationDelay: '300ms', opacity: 0 }}>
              {canScrollLeft && (
                <button
                  onClick={() => handleScroll('left')}
                  className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-5 z-10 w-12 h-12 rounded-full bg-background border border-border shadow-xl flex items-center justify-center hover:bg-muted hover:scale-105 transition-all text-foreground"
                >
                  <ChevronLeft className="w-6 h-6" />
                </button>
              )}

              <div 
                ref={scrollRef}
                className="flex gap-6 overflow-x-auto snap-x snap-mandatory pb-8 -mx-6 px-6 sm:mx-0 sm:px-0 [scrollbar-width:none] scroll-smooth"
              >
                {filteredAndSortedReviews.map((r, i) => (
                  <div 
                    key={i} 
                    className="snap-start shrink-0 w-[85vw] sm:w-[400px] interactive-card bg-card p-8 rounded-[2rem] border border-border flex flex-col justify-between"
                  >
                    <ReviewCardContent r={r} />
                  </div>
                ))}
              </div>

              {canScrollRight && (
                <button
                  onClick={() => handleScroll('right')}
                  className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-5 z-10 w-12 h-12 rounded-full bg-background border border-border shadow-xl flex items-center justify-center hover:bg-muted hover:scale-105 transition-all text-foreground"
                >
                  <ChevronRight className="w-6 h-6" />
                </button>
              )}

              {totalDots > 1 && (
                <div className="flex justify-center items-center gap-2 mt-4">
                  {[...Array(Math.min(10, totalDots))].map((_, idx) => {
                    const step = totalDots > 10 ? Math.floor((totalDots - 1) / 9) : 1
                    const isActive = Math.round(activeDot / step) === idx
                    return (
                      <div 
                        key={idx} 
                        className={`h-2 rounded-full transition-all duration-500 ${
                          isActive ? 'w-8 bg-primary' : 'w-2 bg-muted-foreground/30'
                        }`}
                      />
                    )
                  })}
                </div>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 animate-fade-up" style={{ animationDelay: '300ms', opacity: 0 }}>
              {filteredAndSortedReviews.map((r, i) => (
                <div 
                  key={i} 
                  className="interactive-card bg-card p-8 rounded-[2rem] border border-border flex flex-col justify-between h-full"
                >
                  <ReviewCardContent r={r} />
                </div>
              ))}
            </div>
          )
        ) : (
          <div className="text-center py-20 glass-panel rounded-[2rem] max-w-md mx-auto animate-fade-in">
            <ShieldAlert className="w-12 h-12 text-muted-foreground/50 mx-auto mb-4" />
            <h3 className="font-extrabold text-foreground text-xl mb-2">No reviews match filters</h3>
            <p className="text-muted-foreground text-sm px-8 mb-6">
              We couldn&apos;t find any reviews matching &ldquo;{searchTerm}&rdquo; or your star selection.
            </p>
            <button 
              onClick={() => { setSearchTerm(''); setRatingFilter('all') }}
              className="text-sm font-bold text-primary hover:text-primary/80 underline underline-offset-4"
            >
              Clear all filters
            </button>
          </div>
        )}
      </div>
    </section>
  )
}

function ReviewCardContent({ r }: { r: Review }) {
  const avatarStyle = getAvatarBgColor(r.reviewer_name)
  
  return (
    <div className="flex flex-col h-full justify-between">
      <div>
        <div className="flex items-center gap-4 mb-6">
          {r.reviewer_profile_photo ? (
            <img
              src={r.reviewer_profile_photo}
              alt={r.reviewer_name}
              referrerPolicy="no-referrer"
              className="w-14 h-14 rounded-full object-cover ring-4 ring-muted shadow-sm"
              loading="lazy"
            />
          ) : (
            <div className={`w-14 h-14 rounded-full flex items-center justify-center font-bold text-xl border-2 ${avatarStyle} shadow-sm`}>
              {r.reviewer_name ? r.reviewer_name.charAt(0).toUpperCase() : '?'}
            </div>
          )}
          
          <div className="min-w-0 flex-grow">
            <div className="flex items-center gap-2">
              <h4 className="font-extrabold text-base text-foreground truncate leading-tight">
                {r.reviewer_name}
              </h4>
              <svg className="w-4 h-4 text-muted-foreground shrink-0" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                <path d="M12.24 10.285V13.4h6.887c-.275 1.565-1.88 4.604-6.887 4.604-4.33 0-7.86-3.577-7.86-8s3.53-8 7.86-8c2.46 0 4.105 1.025 5.047 1.926l2.427-2.334C17.955 2.192 15.34 1 12.24 1 5.48 1 0 6.48 0 13s5.48 12 12.24 12c7.05 0 11.75-4.91 11.75-11.89 0-.802-.087-1.413-.188-1.825H12.24z"/>
              </svg>
            </div>
            
            <div className="flex items-center gap-3 mt-1.5">
              <div className="flex text-amber-400 shrink-0">
                {[...Array(5)].map((_, idx) => (
                  <Star 
                    key={idx} 
                    className={`w-4 h-4 ${idx < (r.rating || 0) ? 'fill-current' : 'text-slate-200 fill-slate-200'}`} 
                  />
                ))}
              </div>
              <span className="text-xs text-muted-foreground font-medium">
                {new Date(r.review_created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
              </span>
            </div>
          </div>
        </div>

        {r.comment ? (
          <p className="text-muted-foreground text-sm sm:text-base leading-relaxed line-clamp-6 mb-4">
            &ldquo;{r.comment}&rdquo;
          </p>
        ) : (
          <p className="text-muted-foreground/60 text-sm italic leading-relaxed mb-4">
            Left a rating without a comment.
          </p>
        )}
      </div>

      {r.reply_text && (
        <div className="mt-4 bg-muted/50 p-5 rounded-2xl border border-border/50 relative">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-4 h-4 text-primary shrink-0" />
            <span className="font-extrabold text-[11px] text-primary uppercase tracking-widest">
              Owner Reply
            </span>
            {r.reply_created_at && (
              <span className="text-[10px] text-muted-foreground ml-auto font-medium">
                {new Date(r.reply_created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}
              </span>
            )}
          </div>
          <p className="text-muted-foreground text-sm leading-relaxed">
            {r.reply_text}
          </p>
        </div>
      )}
    </div>
  )
}
