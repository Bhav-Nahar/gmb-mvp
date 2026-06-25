import React from 'react'

interface SocialLink { type: string; label: string; url: string }

export default function SocialLinks({ links }: { links: SocialLink[] }) {
  if (!links || links.length === 0) return null

  return (
    <section className="py-12 px-6 bg-slate-950 border-t border-white/5">
      <div className="max-w-5xl mx-auto text-center">
        <h3 className="text-xs font-bold tracking-[0.2em] uppercase text-slate-500 mb-6">Explore More</h3>
        <div className="flex flex-wrap justify-center gap-4">
          {links.map((s) => (
            <a
              key={s.type + s.url}
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-full border border-white/10 bg-white/5 text-slate-300 font-semibold text-sm hover:bg-white/10 hover:text-white hover:border-white/20 hover:scale-105 transition-all duration-300 shadow-sm"
            >
              {s.label}
            </a>
          ))}
        </div>
      </div>
    </section>
  )
}
