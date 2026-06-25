'use client'

import React, { useState, useEffect, useCallback } from 'react'
import { ChevronLeft, ChevronRight, X, Image as ImageIcon } from 'lucide-react'

interface GalleryProps {
  photos: string[]
}

const INITIAL_COUNT = 9

export default function Gallery({ photos }: GalleryProps) {
  const [expanded, setExpanded] = useState(false)
  const [lightbox, setLightbox] = useState<number | null>(null)

  const close = useCallback(() => setLightbox(null), [])
  
  const show = useCallback((delta: number) => {
    setLightbox((cur) => {
      if (cur === null) return cur
      const n = photos.length
      return ((cur + delta) % n + n) % n
    })
  }, [photos.length])

  useEffect(() => {
    if (lightbox === null) return
    
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
      if (e.key === 'ArrowRight') show(1)
      if (e.key === 'ArrowLeft') show(-1)
    }
    
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [lightbox, close, show])

  if (!photos || photos.length === 0) return null

  const visible = expanded ? photos : photos.slice(0, INITIAL_COUNT)
  const hasMore = photos.length > INITIAL_COUNT

  return (
    <section id="photos" className="py-24 px-6 sm:px-12 bg-background scroll-mt-20">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16 animate-fade-up">
          <span className="text-sm font-bold tracking-[0.2em] text-primary uppercase">
            Our Gallery
          </span>
          <h2 className="text-4xl sm:text-5xl font-black text-foreground tracking-tight mt-4 mb-6">
            Captured Moments
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto text-lg leading-relaxed">
            Take a visual tour of our workspace, team, and recent projects.
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4 sm:gap-6 animate-fade-up" style={{ animationDelay: '100ms', opacity: 0 }}>
          {visible.map((url, i) => {
            // Create a slight masonry/bento effect by making every 4th item span taller
            const isTall = i % 4 === 0 || i % 5 === 0;
            return (
              <button
                key={i}
                onClick={() => setLightbox(i)}
                className={`relative overflow-hidden rounded-[2rem] bg-card group border border-border cursor-zoom-in shadow-sm hover:shadow-xl hover:border-primary/30 transition-all duration-500 ${isTall ? 'row-span-2 aspect-[3/4]' : 'aspect-square'}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={url}
                  alt={`Location photo ${i + 1}`}
                  referrerPolicy="no-referrer"
                  className="absolute inset-0 w-full h-full object-cover transition-transform duration-700 group-hover:scale-110"
                  loading="lazy"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/0 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 flex items-end justify-center pb-6">
                  <span className="flex items-center gap-2 text-white text-sm font-bold bg-white/20 backdrop-blur-md px-4 py-2 rounded-full border border-white/20 translate-y-4 group-hover:translate-y-0 transition-transform duration-500">
                    <ImageIcon className="w-4 h-4" />
                    View Photo
                  </span>
                </div>
              </button>
            )
          })}
        </div>

        {hasMore && (
          <div className="text-center mt-16 animate-fade-in" style={{ animationDelay: '200ms', opacity: 0 }}>
            <button
              onClick={() => setExpanded(!expanded)}
              className="inline-flex items-center gap-2 px-8 py-4 rounded-full border border-border text-foreground bg-card text-sm font-bold hover:border-primary hover:text-primary shadow-sm hover:shadow-md transition-all duration-300"
            >
              {expanded ? 'Show Less' : `Show All ${photos.length} Photos`}
            </button>
          </div>
        )}
      </div>

      {/* Lightbox Slider overlay */}
      {lightbox !== null && (
        <div 
          className="fixed inset-0 z-[100] bg-slate-950/95 flex items-center justify-center p-4 backdrop-blur-xl transition-all duration-300" 
          onClick={close}
        >
          {/* Close Button */}
          <button 
            onClick={close} 
            className="absolute top-6 right-6 text-slate-400 hover:text-white bg-white/10 hover:bg-white/20 p-3 rounded-full border border-white/10 transition-all active:scale-95 shadow-md" 
            aria-label="Close lightbox"
          >
            <X className="w-6 h-6" />
          </button>

          {/* Left Arrow Navigation */}
          {photos.length > 1 && (
            <button 
              onClick={(e) => { e.stopPropagation(); show(-1) }} 
              className="absolute left-4 sm:left-8 text-slate-400 hover:text-white bg-white/10 hover:bg-white/20 p-4 rounded-full border border-white/10 transition-all active:scale-95 shadow-md" 
              aria-label="Previous photo"
            >
              <ChevronLeft className="w-8 h-8" />
            </button>
          )}

          {/* Right Arrow Navigation */}
          {photos.length > 1 && (
            <button 
              onClick={(e) => { e.stopPropagation(); show(1) }} 
              className="absolute right-4 sm:right-8 text-slate-400 hover:text-white bg-white/10 hover:bg-white/20 p-4 rounded-full border border-white/10 transition-all active:scale-95 shadow-md" 
              aria-label="Next photo"
            >
              <ChevronRight className="w-8 h-8" />
            </button>
          )}

          {/* Active Image Container */}
          <div className="relative flex flex-col items-center justify-center max-w-[90vw] max-h-[85vh]" onClick={(e) => e.stopPropagation()}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photos[lightbox]}
              alt={`Location photo ${lightbox + 1}`}
              referrerPolicy="no-referrer"
              className="object-contain rounded-2xl max-w-full max-h-[85vh] shadow-2xl border border-white/10 animate-fade-in"
            />
            {/* Index Tracker Text */}
            <span className="absolute -bottom-10 text-slate-300 text-sm font-bold bg-white/5 backdrop-blur-md px-4 py-1.5 rounded-full border border-white/10">
              {lightbox + 1} of {photos.length}
            </span>
          </div>
        </div>
      )}
    </section>
  )
}
