import React from 'react'

// Renders the business description sourced from Google Business Profile only.
// Hidden entirely when GBP has no description (no AI/templated fallback).
export default function AboutSection({ description, name }: { description?: string | null; name: string }) {
  const text = (description || '').trim()
  if (!text) return null

  return (
    <section id="about" className="scroll-mt-28">
      <div className="max-w-3xl">
        <h2 className="text-2xl sm:text-3xl font-bold text-foreground tracking-tight mb-4 text-balance leading-tight">About {name}</h2>
        <div className="w-16 h-1 bg-primary mb-6 rounded-full"></div>
        <p className="text-muted-foreground leading-relaxed whitespace-pre-line text-base sm:text-lg">{text}</p>
      </div>
    </section>
  )
}
