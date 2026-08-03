'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export interface Branding {
  name: string
  logo_url: string
  website_url: string
}

export interface BrandingState {
  is_agency: boolean
  branding: Branding
  saved: {
    brand_name: string | null
    brand_logo_url: string | null
    brand_website_url: string | null
  }
}

// Module-level cache: the export header renders on every analytics page and the
// answer changes about once a year. One fetch per session is plenty.
let cached: BrandingState | null = null
let inflight: Promise<BrandingState> | null = null

async function fetchBranding(): Promise<BrandingState> {
  if (cached) return cached
  if (!inflight) {
    inflight = api.get<BrandingState>('/branding')
      .then((d) => { cached = d; return d })
      .finally(() => { inflight = null })
  }
  return inflight
}

export function invalidateBranding() {
  cached = null
}

/** Returns null until loaded — callers render nothing rather than flashing Pinzo. */
export function useBranding() {
  const [state, setState] = useState<BrandingState | null>(cached)

  useEffect(() => {
    let alive = true
    fetchBranding()
      .then((d) => { if (alive) setState(d) })
      .catch(() => { /* export header just stays hidden */ })
    return () => { alive = false }
  }, [])

  return state
}
