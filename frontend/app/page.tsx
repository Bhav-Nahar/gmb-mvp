import type { Metadata } from 'next'
import HomeClient from './HomeClient'

export const metadata: Metadata = {
  title: 'Pinzo — Manage Google Business Profiles at Scale',
  description: 'Centralize Google Business Profile reviews, post schedules, analytics, and multi-location sync in one premium dashboard. Perfect for local SEO agencies and franchises.',
}

export default function RootPage() {
  return <HomeClient />
}

