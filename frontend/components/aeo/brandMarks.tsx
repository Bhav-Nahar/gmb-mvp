// Real brand marks for the AI engines — inline SVG (CSP-safe, no external images).
import React from 'react'

export function OpenAIMark({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M22.28 9.82a5.98 5.98 0 0 0-.52-4.91 6.05 6.05 0 0 0-6.51-2.9A6.07 6.07 0 0 0 4.98 4.18a5.98 5.98 0 0 0-3.99 2.9 6.05 6.05 0 0 0 .74 7.1 5.98 5.98 0 0 0 .51 4.91 6.05 6.05 0 0 0 6.52 2.9A5.98 5.98 0 0 0 13.26 24a6.06 6.06 0 0 0 5.77-4.21 5.99 5.99 0 0 0 4-2.9 6.06 6.06 0 0 0-.75-7.07zM13.26 22.43a4.48 4.48 0 0 1-2.88-1.04l.14-.08 4.78-2.76a.79.79 0 0 0 .39-.68v-6.74l2.02 1.17.01.06v5.58a4.5 4.5 0 0 1-4.48 4.49zM3.6 18.3a4.47 4.47 0 0 1-.54-3.01l.14.09 4.78 2.76a.77.77 0 0 0 .78 0l5.84-3.37v2.33l-.03.06L9.74 19.9a4.5 4.5 0 0 1-6.14-1.6zM2.34 7.9a4.49 4.49 0 0 1 2.34-1.97v5.67a.77.77 0 0 0 .39.68l5.8 3.35-2.02 1.17-.07-.01-4.83-2.79A4.5 4.5 0 0 1 2.34 7.9zm16.6 3.86-5.84-3.37 2.02-1.16.07.01 4.83 2.79a4.5 4.5 0 0 1-.68 8.12v-5.72a.79.79 0 0 0-.4-.67zm2.01-3.03-.14-.09-4.78-2.76a.78.78 0 0 0-.78 0L9.42 9.24V6.91l.03-.06 4.83-2.78a4.5 4.5 0 0 1 6.68 4.66zM8.31 12.86 6.29 11.7l-.03-.06V6.07a4.5 4.5 0 0 1 7.38-3.45l-.14.08L8.7 5.46a.79.79 0 0 0-.39.68zm1.1-2.37L12 8.99l2.6 1.5v3l-2.6 1.5-2.6-1.5z"/>
    </svg>
  )
}
export function GoogleMark({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path fill="#4285F4" d="M23.06 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h6.2a5.3 5.3 0 0 1-2.3 3.48v2.89h3.72c2.18-2 3.44-4.96 3.44-8.38z"/>
      <path fill="#34A853" d="M12 24c3.1 0 5.7-1.03 7.6-2.78l-3.72-2.89c-1.03.69-2.35 1.1-3.88 1.1-2.98 0-5.5-2.01-6.4-4.72H1.76v2.98A11.99 11.99 0 0 0 12 24z"/>
      <path fill="#FBBC05" d="M5.6 14.71a7.2 7.2 0 0 1 0-4.62V7.11H1.76a12 12 0 0 0 0 10.78l3.84-2.98z"/>
      <path fill="#EA4335" d="M12 4.75c1.68 0 3.2.58 4.39 1.72l3.29-3.29C17.7 1.24 15.1.2 12 .2A11.99 11.99 0 0 0 1.76 7.11l3.84 2.98C6.5 6.76 9.02 4.75 12 4.75z"/>
    </svg>
  )
}
export function GeminiMark({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <defs><linearGradient id="pinzoGemPanel" x1="2" y1="4" x2="22" y2="20" gradientUnits="userSpaceOnUse">
        <stop stopColor="#4285F4"/><stop offset=".5" stopColor="#9B72CB"/><stop offset="1" stopColor="#D96570"/>
      </linearGradient></defs>
      <path fill="url(#pinzoGemPanel)" d="M12 0c.4 6.4 5.2 11.2 11.6 11.6-6.4.4-11.2 5.2-11.6 11.6-.4-6.4-5.2-11.2-11.6-11.6C6.8 11.2 11.6 6.4 12 0z"/>
    </svg>
  )
}
export function PerplexityMark({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="none" stroke="#20808D" strokeWidth="1.6">
      <path d="M12 3v18M12 8 5 4v8l7-4 7 4V4l-7 4M4 9v6l8 4 8-4V9"/>
    </svg>
  )
}

export function SurfaceLogo({ surfaceKey, className = 'h-4 w-4' }: { surfaceKey: string; className?: string }) {
  if (surfaceKey === 'chatgpt') return <OpenAIMark className={`${className} text-foreground`} />
  if (surfaceKey === 'gemini') return <GeminiMark className={className} />
  if (surfaceKey === 'perplexity') return <PerplexityMark className={className} />
  return <GoogleMark className={className} /> // google_ai_overview + google_ai_mode
}
