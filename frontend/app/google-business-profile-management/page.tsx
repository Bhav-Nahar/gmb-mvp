import type { Metadata } from 'next'
import HomeClient from '../HomeClient'

export const metadata: Metadata = {
  title: 'Google Business Profile Management Tool for Multi-Location Brands | Pinzo',
  description: 'Audit, manage and improve Google Business Profiles across locations. Track reviews, profile gaps, local visibility and GBP health from one AI dashboard. Free audit, no card required.',
}

// Paid-campaign landing page. Same login/trial funnel as the homepage, audit-framed
// copy + CTAs. Distinguished in the dataLayer by its page_path.
export default function PaidLandingPage() {
  return <HomeClient variant="paid" />
}
