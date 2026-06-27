'use client'

import React, { useMemo } from 'react'
import { 
  Scissors, Sparkles, Smile, Droplet, Heart, Paintbrush, 
  Wrench, ShoppingBag, FileText, Calendar, ConciergeBell, 
  Flame, Stethoscope
} from 'lucide-react'

interface ServicesSectionProps {
  serviceItems: any[]
}

const getServiceIcon = (title: string) => {
  const t = title.toLowerCase()
  if (t.includes('hair') || t.includes('cut') || t.includes('shave') || t.includes('trim') || t.includes('barber') || t.includes('styling')) return Scissors
  if (t.includes('nail') || t.includes('manicure') || t.includes('pedicure') || t.includes('polish') || t.includes('art')) return Paintbrush
  if (t.includes('massage') || t.includes('spa') || t.includes('relax') || t.includes('stone') || t.includes('therapy')) return Flame
  if (t.includes('skin') || t.includes('facial') || t.includes('peel') || t.includes('mask') || t.includes('scrub') || t.includes('beauty')) return Smile
  if (t.includes('wash') || t.includes('rinse') || t.includes('clean') || t.includes('shampoo') || t.includes('detail') || t.includes('laundry')) return Droplet
  if (t.includes('dent') || t.includes('teeth') || t.includes('tooth') || t.includes('oral')) return Stethoscope
  if (t.includes('health') || t.includes('medical') || t.includes('rehab') || t.includes('physical') || t.includes('care')) return Heart
  if (t.includes('consult') || t.includes('advice') || t.includes('plan') || t.includes('strategy') || t.includes('assess')) return FileText
  if (t.includes('book') || t.includes('reserve') || t.includes('schedule') || t.includes('meeting')) return Calendar
  if (t.includes('product') || t.includes('buy') || t.includes('shop') || t.includes('merchandise')) return ShoppingBag
  if (t.includes('repair') || t.includes('fix') || t.includes('install') || t.includes('maintenance') || t.includes('tech') || t.includes('support')) return Wrench
  if (t.includes('service') || t.includes('special') || t.includes('custom') || t.includes('vip')) return ConciergeBell
  return Sparkles
}

export default function ServicesSection({ serviceItems }: ServicesSectionProps) {
  const parsedServices = useMemo(() => {
    if (!serviceItems || serviceItems.length === 0) return []

    return serviceItems.map((it: any) => {
      const free = it?.freeFormServiceItem
      const struct = it?.structuredServiceItem
      
      let rawTitle = free?.label?.displayName || struct?.description || struct?.serviceTypeId || (typeof it === 'string' ? it : null)
      
      if (rawTitle && rawTitle.startsWith('gcid:')) {
        rawTitle = rawTitle.replace('gcid:', '').replace(/_/g, ' ')
        rawTitle = rawTitle.charAt(0).toUpperCase() + rawTitle.slice(1)
      }

      const title = rawTitle || 'Service'
      const description = free?.label?.description || null
      const price = it?.price?.units != null ? `${it.price.currencyCode || ''} ${it.price.units}`.trim() : null
      
      return { title, description, price }
    }).filter(s => s.title !== 'Service')
  }, [serviceItems])

  const filteredServices = parsedServices

  if (parsedServices.length === 0) return null

  return (
    <div id="services" className="scroll-mt-28 relative">
      <div>
        <div className="mb-10 animate-fade-up">
          <span className="text-xs font-bold tracking-[0.2em] text-primary uppercase">
            Our Offerings
          </span>
          <h2 className="text-3xl sm:text-4xl font-black text-foreground tracking-tight mt-3 mb-4 leading-tight text-balance">
            Services & Solutions
          </h2>
          <p className="text-muted-foreground max-w-2xl text-base leading-relaxed">
            Explore our curated range of professional services, tailored to deliver excellence and meet your exact needs.
          </p>
        </div>

        {filteredServices.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 auto-rows-fr animate-fade-up" style={{ animationDelay: '200ms', opacity: 0 }}>
            {filteredServices.map((s, i) => {
              const IconComponent = getServiceIcon(s.title)
              const isLarge = i === 0 && filteredServices.length % 2 !== 0 && filteredServices.length > 3

              return (
                <div 
                  key={i} 
                  className={`group interactive-card bg-card p-8 rounded-[2rem] flex flex-col h-full ${isLarge ? 'md:col-span-2 lg:col-span-2' : ''}`}
                >
                  <div className="flex justify-between items-start gap-4 mb-6">
                    <div className="w-14 h-14 rounded-2xl bg-primary/10 group-hover:bg-primary text-primary group-hover:text-primary-foreground flex items-center justify-center transition-all duration-500 shadow-sm">
                      <IconComponent className="w-6 h-6 transition-transform duration-500 group-hover:scale-110 group-hover:-rotate-12" />
                    </div>
                    {s.price && (
                      <span className="text-primary-foreground font-bold whitespace-nowrap bg-primary px-4 py-1.5 rounded-full text-sm shrink-0 shadow-md">
                        {s.price}
                      </span>
                    )}
                  </div>

                  <h3 className="font-extrabold text-card-foreground text-xl leading-tight mb-3 group-hover:text-primary transition-colors duration-300">
                    {s.title}
                  </h3>

                  {s.description ? (
                    <p className="text-muted-foreground text-sm leading-relaxed flex-grow">
                      {s.description}
                    </p>
                  ) : (
                    <p className="text-muted-foreground/60 text-sm italic leading-relaxed flex-grow">
                      Contact us for full details and customizations.
                    </p>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
