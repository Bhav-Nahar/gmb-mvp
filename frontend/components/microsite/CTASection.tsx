import React from 'react'

interface CTASectionProps {
  phone?: string
  website?: string
  mapLink?: string | null
  whatsapp?: string | null
  reviewUrl?: string | null
}

export default function CTASection({ phone, website, mapLink, whatsapp, reviewUrl }: CTASectionProps) {
  if (!phone && !website && !whatsapp && !mapLink && !reviewUrl) return null

  return (
    <section className="py-24 px-6 sm:px-12 bg-slate-950 text-white relative overflow-hidden">
      {/* Decorative radial gradients */}
      <div className="absolute inset-0 opacity-60 bg-[radial-gradient(ellipse_at_top_right,_var(--tw-gradient-stops))] from-primary/30 via-transparent to-transparent"></div>
      <div className="absolute inset-0 opacity-40 bg-[radial-gradient(ellipse_at_bottom_left,_var(--tw-gradient-stops))] from-indigo-900/40 via-transparent to-transparent"></div>
      
      <div className="max-w-5xl mx-auto text-center relative z-10 animate-fade-up">
        <h2 className="text-4xl md:text-6xl font-black mb-12 tracking-tight drop-shadow-lg">Ready to visit us?</h2>
        
        <div className="flex flex-col sm:flex-row flex-wrap justify-center items-center gap-4 sm:gap-5">
          {phone && (
            <a href={`tel:${phone}`} className="w-full sm:w-auto bg-primary text-primary-foreground font-bold py-4 px-8 rounded-full shadow-[0_0_20px_rgba(79,70,229,0.3)] hover:shadow-[0_0_30px_rgba(79,70,229,0.5)] hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2.5">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
              </svg>
              Call Now
            </a>
          )}
          
          {whatsapp && (
            <a href={whatsapp} target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto bg-[#25D366] text-white font-bold py-4 px-8 rounded-full shadow-[0_0_20px_rgba(37,211,102,0.2)] hover:shadow-[0_0_30px_rgba(37,211,102,0.4)] hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2.5">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.77-.87-2.04-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.95 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.9-.8-1.5-1.78-1.67-2.08-.17-.3-.02-.46.13-.6.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.5-.17-.01-.37-.01-.57-.01-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.48 0 1.46 1.07 2.88 1.22 3.08.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35zM12 2a10 10 0 00-8.5 15.3L2 22l4.8-1.5A10 10 0 1012 2z"/></svg>
              WhatsApp
            </a>
          )}
          {mapLink && (
            <a href={mapLink} target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto bg-white/5 backdrop-blur-sm border border-white/10 text-white font-bold py-4 px-8 rounded-full hover:bg-white/10 hover:border-white/20 hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2.5">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Get Directions
            </a>
          )}
          
          {website && (
            <a href={website} target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto bg-white/5 backdrop-blur-sm border border-white/10 text-white font-bold py-4 px-8 rounded-full hover:bg-white/10 hover:border-white/20 hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2.5">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
              </svg>
              Visit Website
            </a>
          )}

          {reviewUrl && (
            <a href={reviewUrl} target="_blank" rel="noopener noreferrer" className="w-full sm:w-auto bg-amber-400 text-amber-950 font-bold py-4 px-8 rounded-full shadow-[0_0_20px_rgba(251,191,36,0.2)] hover:shadow-[0_0_30px_rgba(251,191,36,0.4)] hover:scale-105 transition-all duration-300 flex items-center justify-center gap-2.5">
              <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" /></svg>
              Write a Review
            </a>
          )}
        </div>
      </div>
    </section>
  )
}
