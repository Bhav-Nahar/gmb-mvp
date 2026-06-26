'use client'

import React, { useState } from 'react'
import BrandMark from './BrandMark'

interface HeroProps {
  name: string
  category?: string
  rating?: number
  totalReviews?: number
  logo?: string | null
  cover?: string | null
  phone?: string
  whatsapp?: string | null
  mapLink?: string | null
}

export default function Hero({ name, category, rating, totalReviews, logo, cover, phone, whatsapp, mapLink }: HeroProps) {
  const [coverError, setCoverError] = useState(false)

  return (
    <section className="relative overflow-hidden bg-slate-900 text-white min-h-[85vh] flex items-center justify-center">
      {/* Background: cover photo if available, else sophisticated gradient */}
      {cover && !coverError ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={cover} alt="" aria-hidden onError={() => setCoverError(true)} referrerPolicy="no-referrer" className="absolute inset-0 w-full h-full object-cover" />
      ) : (
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900 via-slate-900 to-black" />
      )}
      
      {/* Readability overlay: pure gradient, no blur so the image is crisp */}
      <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/60 to-slate-950/20" />

      <div className="relative z-10 w-full max-w-5xl mx-auto px-6 sm:px-12 py-20 flex flex-col items-center text-center">
        <div className="animate-fade-up" style={{ animationDelay: '100ms', opacity: 0 }}>
          <BrandMark
            name={name}
            logo={logo}
            className="w-24 h-24 sm:w-32 sm:h-32 rounded-3xl mb-8 shadow-2xl ring-1 ring-white/20 glass-panel"
            textClassName="text-4xl sm:text-5xl text-slate-800"
          />
        </div>

        <h1 className="animate-fade-up text-4xl sm:text-6xl md:text-7xl font-extrabold tracking-tight drop-shadow-2xl max-w-4xl text-balance leading-tight" style={{ animationDelay: '200ms', opacity: 0 }}>
          {name}
        </h1>

        {category && (
          <p className="animate-fade-up mt-6 text-xl sm:text-2xl font-medium text-indigo-200/90 tracking-wide" style={{ animationDelay: '300ms', opacity: 0 }}>
            {category}
          </p>
        )}

        {rating !== undefined && rating > 0 && (
          <div className="animate-fade-up mt-8 inline-flex items-center gap-3 bg-white/5 px-6 py-3 rounded-full backdrop-blur-xl border border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.12)]" style={{ animationDelay: '400ms', opacity: 0 }}>
            <span className="text-amber-400 text-2xl font-black tracking-tighter">{rating.toFixed(1)}</span>
            <div className="flex text-amber-400 gap-0.5">
              {[...Array(5)].map((_, i) => (
                <svg key={i} className={`w-5 h-5 ${i < Math.round(rating) ? 'fill-current drop-shadow-[0_2px_4px_rgba(251,191,36,0.3)]' : 'fill-current opacity-20'}`} viewBox="0 0 20 20">
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
              ))}
            </div>
            {totalReviews !== undefined && totalReviews > 0 && (
              <span className="text-slate-300 text-sm font-medium ml-1">({totalReviews} reviews)</span>
            )}
          </div>
        )}

        {/* Primary CTAs */}
        <div className="animate-fade-up mt-12 flex flex-col sm:flex-row flex-wrap justify-center gap-3 sm:gap-4 w-full sm:w-auto" style={{ animationDelay: '500ms', opacity: 0 }}>
          {whatsapp ? (
            <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto inline-flex justify-center items-center gap-2 bg-[#25D366] text-white font-bold px-4 sm:px-8 py-3.5 sm:py-4 rounded-full shadow-[0_8px_30px_rgba(37,211,102,0.3)] hover:scale-105 transition-transform duration-300">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.77-.87-2.04-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.95 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.9-.8-1.5-1.78-1.67-2.08-.17-.3-.02-.46.13-.6.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.5-.17-.01-.37-.01-.57-.01-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.48 0 1.46 1.07 2.88 1.22 3.08.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35zM12 2a10 10 0 00-8.5 15.3L2 22l4.8-1.5A10 10 0 1012 2z"/></svg>
              WhatsApp
            </a>
          ) : (
            <a href="#enquiry" className="w-full sm:w-auto inline-flex justify-center items-center gap-2 bg-indigo-600 text-white font-bold px-4 sm:px-8 py-3.5 sm:py-4 rounded-full shadow-[0_8px_30px_rgba(79,70,229,0.3)] hover:scale-105 hover:bg-indigo-700 transition-all duration-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
              Enquiry
            </a>
          )}
          {phone && (
            <a href={`tel:${phone}`} className="w-full sm:w-auto inline-flex justify-center items-center gap-2 bg-white text-slate-900 font-bold px-4 sm:px-8 py-3.5 sm:py-4 rounded-full shadow-[0_8px_30px_rgb(255,255,255,0.12)] hover:scale-105 transition-transform duration-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
              Call Now
            </a>
          )}
          {mapLink && (
            <a href={mapLink} target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto inline-flex justify-center items-center gap-2 bg-white/10 backdrop-blur-md border border-white/20 text-white font-bold px-4 sm:px-8 py-3.5 sm:py-4 rounded-full hover:bg-white/20 hover:scale-105 transition-all duration-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              Directions
            </a>
          )}
        </div>
      </div>
    </section>
  )
}
