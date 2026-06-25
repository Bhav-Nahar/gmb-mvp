'use client'

import React, { useState } from 'react'

function initials(name: string): string {
  const words = (name || '').trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return '?'
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}

interface BrandMarkProps {
  name: string
  logo?: string | null
  className?: string
  textClassName?: string
}

// Brand logo when GBP has a real LOGO; otherwise a clean initials monogram so
// the header never shows a random owner avatar or an empty gap.
export default function BrandMark({ name, logo, className = '', textClassName = '' }: BrandMarkProps) {
  const [error, setError] = useState(false)

  if (logo && !error) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={logo} alt={`${name} logo`} onError={() => setError(true)} referrerPolicy="no-referrer" className={`object-cover bg-white ${className}`} />
  }
  return (
    <div className={`flex items-center justify-center bg-gradient-to-br from-indigo-500 to-indigo-700 text-white font-extrabold ${className}`}>
      <span className={textClassName}>{initials(name)}</span>
    </div>
  )
}
