import React from 'react'

// Renders the business description sourced from Google Business Profile only.
// Hidden entirely when GBP has no description (no AI/templated fallback).
export default function AboutSection({ description, name }: { description?: string | null; name: string }) {
  const text = (description || '').trim()
  if (!text) return null

  return (
    <section id="about" className="py-12 px-6 sm:px-12 bg-white scroll-mt-20">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight mb-4">About {name}</h2>
        <div className="w-20 h-1 bg-indigo-600 mx-auto mb-6 rounded-full"></div>
        <p className="text-slate-600 leading-relaxed whitespace-pre-line text-base sm:text-lg">{text}</p>
      </div>
    </section>
  )
}
