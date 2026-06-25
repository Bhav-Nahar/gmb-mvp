'use client'

import React, { useMemo } from 'react'
import { MapPin, Phone, Globe, Clock } from 'lucide-react'

interface ContactSectionProps {
  address?: string
  phone?: string
  website?: string
  businessHours?: any
  latlng?: any
  mapsUrl?: string | null
}

// Only allow http(s) website links — blocks javascript:/data: XSS from backend data
const safeHttpUrl = (u?: string) => {
  if (!u) return undefined
  try {
    return ['http:', 'https:'].includes(new URL(u).protocol) ? u : undefined
  } catch {
    return undefined
  }
}

// Helper to format Google API time formats robustly
const formatTime = (t: any) => {
  if (!t) return ''
  if (typeof t === 'string' && t.length === 4) {
    const h = parseInt(t.slice(0, 2), 10)
    const mm = t.slice(2, 4)
    const suffix = h >= 12 ? 'PM' : 'AM'
    const h12 = h % 12 || 12
    return `${h12}:${mm} ${suffix}`
  }
  if (t.hours !== undefined) {
    const h = t.hours
    const m = t.minutes || 0
    const suffix = h >= 12 ? 'PM' : 'AM'
    const h12 = h % 12 || 12
    const mm = m < 10 ? `0${m}` : String(m)
    return `${h12}:${mm} ${suffix}`
  }
  return String(t)
}

// Google openDay enum/index -> JS day index (0=Sun). Google uses 1=Mon..7=Sun.
const normalizeDay = (openDay: any): number => {
  if (typeof openDay === 'string') {
    const map: Record<string, number> = { SUNDAY: 0, MONDAY: 1, TUESDAY: 2, WEDNESDAY: 3, THURSDAY: 4, FRIDAY: 5, SATURDAY: 6 }
    return map[openDay.toUpperCase()] ?? -1
  }
  if (typeof openDay === 'number') return openDay === 7 ? 0 : openDay
  return -1
}

// Helper to convert time format to minutes since midnight
const timeToMinutes = (t: any) => {
  if (!t) return 0
  if (typeof t === 'string' && t.length === 4) {
    const h = parseInt(t.slice(0, 2), 10)
    const m = parseInt(t.slice(2, 4), 10)
    return h * 60 + m
  }
  if (t.hours !== undefined) {
    return t.hours * 60 + (t.minutes || 0)
  }
  return 0
}

export default function ContactSection({ address, phone, website, businessHours, latlng, mapsUrl }: ContactSectionProps) {
  const safeWebsite = safeHttpUrl(website)
  const periods = businessHours?.periods || []
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

  // Map source priority: GBP canonical link (exact business pin) -> precise
  // coordinates -> address (so service-area businesses without a pin still show).
  const mapQuery = (latlng?.latitude && latlng?.longitude)
    ? `${latlng.latitude},${latlng.longitude}`
    : (address || null)
  const mapUrl = mapsUrl
    ? `${mapsUrl}${mapsUrl.includes('?') ? '&' : '?'}output=embed`
    : mapQuery
      ? `https://maps.google.com/maps?${new URLSearchParams({ q: mapQuery, output: 'embed', hl: 'en' }).toString()}`
      : null

  // Compute live open/closed status
  const currentStatus = useMemo(() => {
    const pList = businessHours?.periods || []
    if (pList.length === 0) {
      return { isOpen: false, text: 'Hours not specified' }
    }

    const now = new Date()
    const currentDay = now.getDay()
    const currentHours = now.getHours()
    const currentMinutes = now.getMinutes()
    const currentTimeVal = currentHours * 60 + currentMinutes

    // Find periods for today
    const todayPeriods = pList.filter((p: any) => normalizeDay(p.openDay) === currentDay)

    if (todayPeriods.length === 0) {
      return { isOpen: false, text: 'Closed today' }
    }

    for (const p of todayPeriods) {
      // 24 hours open case
      if (p.openTime === '0000' && p.closeTime === '0000') {
        return { isOpen: true, text: 'Open 24 Hours' }
      }

      const start = timeToMinutes(p.openTime)
      const end = timeToMinutes(p.closeTime)

      if (currentTimeVal >= start && currentTimeVal < end) {
        const closeStr = p.closeTime ? formatTime(p.closeTime) : ''
        return { isOpen: true, text: `Open Now • Closes at ${closeStr}` }
      }
    }

    // Check if opening later today
    const futurePeriods = todayPeriods.filter((p: any) => timeToMinutes(p.openTime) > currentTimeVal)
    if (futurePeriods.length > 0) {
      futurePeriods.sort((a: any, b: any) => timeToMinutes(a.openTime) - timeToMinutes(b.openTime))
      const nextOpen = formatTime(futurePeriods[0].openTime)
      return { isOpen: false, text: `Closed • Opens at ${nextOpen}` }
    }

    return { isOpen: false, text: 'Closed Now' }
  }, [businessHours])

  return (
    <section id="contact" className="py-24 px-6 sm:px-12 bg-background scroll-mt-20">
      <div className="max-w-6xl mx-auto animate-fade-up">
        <div className="bg-slate-900 rounded-[2rem] overflow-hidden shadow-2xl grid lg:grid-cols-2 border border-slate-800">
          
          {/* Left: contact details + hours */}
          <div className="p-8 md:p-12 text-white flex flex-col justify-between">
            <div>
              <h2 className="text-3xl sm:text-4xl font-black mb-8 text-white tracking-tight">
                Get in Touch
              </h2>

              <div className="space-y-6">
                {address && (
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-indigo-500/10 text-indigo-300 rounded-xl shrink-0 border border-indigo-500/15">
                      <MapPin className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-indigo-200 text-xs font-bold tracking-[0.1em] uppercase mb-1">Address</h4>
                      <p className="text-sm sm:text-base text-slate-100 leading-relaxed font-medium">{address}</p>
                    </div>
                  </div>
                )}

                {phone && (
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-indigo-500/10 text-indigo-300 rounded-xl shrink-0 border border-indigo-500/15">
                      <Phone className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-indigo-200 text-xs font-bold tracking-[0.1em] uppercase mb-1">Phone</h4>
                      <a href={`tel:${phone}`} className="text-sm sm:text-base text-slate-100 hover:text-white hover:underline transition-all font-medium">{phone}</a>
                    </div>
                  </div>
                )}

                {safeWebsite && (
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-indigo-500/10 text-indigo-300 rounded-xl shrink-0 border border-indigo-500/15">
                      <Globe className="w-5 h-5" />
                    </div>
                    <div>
                      <h4 className="text-indigo-200 text-xs font-bold tracking-[0.1em] uppercase mb-1">Website</h4>
                      <a href={safeWebsite} target="_blank" rel="noopener noreferrer" className="text-sm sm:text-base text-slate-100 hover:text-white hover:underline transition-all break-all font-medium">{website}</a>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Hours */}
            <div className="pt-8 mt-8 border-t border-slate-800">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-5">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-indigo-500/10 text-indigo-300 rounded-xl border border-indigo-500/15 shrink-0">
                    <Clock className="w-4 h-4" />
                  </div>
                  <h4 className="text-indigo-200 text-xs font-bold tracking-[0.1em] uppercase">Business Hours</h4>
                </div>
                
                {periods.length > 0 && (
                  <span className={`inline-flex items-center gap-2 text-[10px] font-black px-4 py-1.5 rounded-full uppercase border tracking-widest self-start sm:self-auto ${
                    currentStatus.isOpen 
                      ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25 shadow-[0_0_15px_rgba(16,185,129,0.1)]' 
                      : 'bg-rose-500/10 text-rose-400 border-rose-500/25'
                  }`}>
                    <span className={`w-2 h-2 rounded-full ${currentStatus.isOpen ? 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] animate-pulse' : 'bg-rose-400'}`} />
                    {currentStatus.text}
                  </span>
                )}
              </div>
              
              <div className="space-y-3 bg-slate-950/40 border border-slate-800 p-6 rounded-2xl">
                {days.map((day, i) => {
                  const dayPeriods = periods.filter((p: any) => normalizeDay(p.openDay) === i)
                  const isToday = new Date().getDay() === i
                  return (
                    <div key={day} className={`flex justify-between items-start text-xs sm:text-sm ${isToday ? 'text-indigo-300 font-bold' : 'text-slate-300 font-medium'}`}>
                      <div className="flex items-center gap-2.5">
                        {isToday && <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 shadow-[0_0_5px_rgba(129,140,248,0.5)]"></span>}
                        <span>{day}</span>
                      </div>
                      <div className="text-right flex flex-col items-end">
                        {dayPeriods.length === 0 ? (
                          <span className="text-slate-500 italic text-xs">Closed</span>
                        ) : (
                          dayPeriods.map((p: any, idx: number) => (
                            <span key={idx}>{formatTime(p.openTime)} - {formatTime(p.closeTime)}</span>
                          ))
                        )}
                      </div>
                    </div>
                  )
                })}
                {periods.length === 0 && <p className="text-slate-500 italic text-xs text-center py-2">Hours not specified</p>}
              </div>
            </div>
          </div>

          {/* Right: map */}
          {mapUrl && (
            <div className="min-h-[400px] lg:min-h-full relative overflow-hidden group">
              <iframe
                title="Google Maps Location"
                src={mapUrl}
                className="w-full h-full min-h-[400px] border-0 grayscale hover:grayscale-0 transition-all duration-1000 scale-105 group-hover:scale-100"
                loading="lazy"
                referrerPolicy="no-referrer-when-downgrade"
              />
              <div className="absolute inset-0 pointer-events-none shadow-[inset_0_0_20px_rgba(0,0,0,0.1)]"></div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
