'use client'

import React, { useState, useEffect } from 'react'
import BrandMark from './BrandMark'

interface NavSection { id: string; label: string }
interface StickyNavProps {
  name: string
  logo?: string | null
  phone?: string
  mapLink?: string | null
  whatsapp?: string | null
  sections: NavSection[]
}

export default function StickyNav({ name, logo, phone, mapLink, whatsapp, sections }: StickyNavProps) {
  const [activeSection, setActiveSection] = useState('')
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 50)
    }
    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  useEffect(() => {
    if (sections.length === 0) return

    const observerOptions = {
      root: null,
      rootMargin: '-30% 0px -60% 0px',
      threshold: 0
    }

    const observerCallback = (entries: IntersectionObserverEntry[]) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setActiveSection(entry.target.id)
        }
      })
    }

    const observer = new IntersectionObserver(observerCallback, observerOptions)

    sections.forEach((s) => {
      const el = document.getElementById(s.id)
      if (el) observer.observe(el)
    })

    const heroEl = document.getElementById('top')
    if (heroEl) observer.observe(heroEl)

    return () => {
      observer.disconnect()
    }
  }, [sections])

  return (
    <header className="relative lg:sticky top-4 z-50 px-1 sm:px-6 mb-4 mt-4 pointer-events-none">
      <div className={`max-w-5xl mx-auto rounded-full h-14 sm:h-16 flex items-center justify-between gap-1 sm:gap-4 px-2 sm:px-6 pointer-events-auto transition-all duration-500 ease-out ${scrolled ? 'glass-panel shadow-lg border border-border/50 bg-background/80 backdrop-blur-xl' : 'bg-background shadow-sm border border-border/30'}`}>
        {/* Brand */}
        <a href="#top" className="flex items-center gap-3 min-w-0 group">
          <BrandMark name={name} logo={logo} className={`w-9 h-9 rounded-full shrink-0 shadow-sm transition-all duration-300 ${scrolled ? 'ring-2 ring-primary/20' : 'ring-2 ring-border/50'}`} textClassName="text-sm" />
          <span className="font-black truncate text-sm sm:text-base transition-colors duration-300 text-foreground group-hover:text-primary">{name}</span>
        </a>

        {/* In-page nav (desktop) */}
        <nav className="hidden lg:flex items-center gap-1 h-full">
          {sections.map((s) => {
            const isActive = activeSection === s.id
            return (
              <a 
                key={s.id} 
                href={`#${s.id}`} 
                className={`text-xs font-bold px-4 py-2 rounded-full transition-all duration-300 ${
                  isActive 
                    ? 'bg-primary text-primary-foreground shadow-sm' 
                    : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                }`}
              >
                {s.label}
              </a>
            )
          })}
        </nav>

        {/* CTAs */}
        <div className="hidden sm:flex items-center gap-1 sm:gap-2 shrink-0">
          {whatsapp ? (
            <a href={whatsapp} target="_blank" rel="noopener noreferrer" aria-label="WhatsApp" className="inline-flex items-center justify-center w-8 h-8 sm:w-auto sm:px-4 sm:h-10 bg-[#25D366] text-white text-xs font-bold rounded-full hover:brightness-95 hover:scale-105 shadow-sm transition-all">
              <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 sm:mr-1.5" viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.77-.87-2.04-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.95 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.9-.8-1.5-1.78-1.67-2.08-.17-.3-.02-.46.13-.6.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.5-.17-.01-.37-.01-.57-.01-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.48 0 1.46 1.07 2.88 1.22 3.08.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35zM12 2a10 10 0 00-8.5 15.3L2 22l4.8-1.5A10 10 0 1012 2z"/></svg>
              <span className="hidden sm:inline">WhatsApp</span>
            </a>
          ) : (
            <a href="#enquiry" aria-label="Enquiry" className="inline-flex items-center justify-center w-8 h-8 sm:w-auto sm:px-4 sm:h-10 bg-indigo-600 text-white text-xs font-bold rounded-full hover:bg-indigo-700 hover:scale-105 shadow-sm transition-all">
              <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
              <span className="hidden sm:inline">Enquiry</span>
            </a>
          )}
          {phone && (
            <a href={`tel:${phone}`} className="inline-flex items-center justify-center w-8 h-8 sm:w-auto sm:px-4 sm:h-10 bg-primary text-primary-foreground text-xs font-bold rounded-full hover:bg-primary/90 hover:scale-105 shadow-sm transition-all">
              <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
              <span className="hidden sm:inline">Call</span>
            </a>
          )}
          {mapLink && (
            <a href={mapLink} target="_blank" rel="noopener noreferrer" className="inline-flex items-center justify-center w-8 h-8 sm:w-auto sm:px-4 sm:h-10 border text-xs font-bold rounded-full hover:scale-105 transition-all border-border text-foreground hover:bg-muted">
              <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4 sm:mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
              <span className="hidden sm:inline">Directions</span>
            </a>
          )}
        </div>
      </div>
    </header>
  )
}
