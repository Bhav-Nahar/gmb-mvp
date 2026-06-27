'use client'

import { useEffect } from 'react'
import { captureAttribution } from '@/lib/attribution'

// Captures first/last-touch attribution once per load. Renders nothing.
export default function Attribution() {
  useEffect(() => { captureAttribution() }, [])
  return null
}
