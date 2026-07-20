import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import FeatureLanding from '@/components/features/FeatureLanding'
import { FEATURES, getFeature } from '@/lib/features'

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'

// Static, hand-written pages — one per feature, prerendered from the content map.
// dynamicParams=false -> any slug not in the map returns 404 (no dynamic render).
export const dynamicParams = false
export function generateStaticParams() {
  return FEATURES.map((f) => ({ slug: f.slug }))
}

export function generateMetadata({ params }: { params: { slug: string } }): Metadata {
  const f = getFeature(params.slug)
  if (!f) return { title: 'Not Found', description: 'The requested page could not be found.' }
  const canonical = `${SITE_URL}/features/${f.slug}`
  const ogImage = `${SITE_URL}/logo-horizontal-3.png`
  return {
    title: f.metaTitle,
    description: f.metaDescription,
    robots: { index: true, follow: true },
    alternates: { canonical },
    openGraph: { title: f.metaTitle, description: f.metaDescription, url: canonical, siteName: 'Pinzo', type: 'website', images: [{ url: ogImage }] },
    twitter: { card: 'summary_large_image', title: f.metaTitle, description: f.metaDescription, images: [ogImage] },
  }
}

export default function FeaturePage({ params }: { params: { slug: string } }) {
  const f = getFeature(params.slug)
  if (!f) notFound()
  return <FeatureLanding feature={f} />
}
