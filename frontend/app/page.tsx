import type { Metadata } from 'next'
import HomeClient from './HomeClient'

export const metadata: Metadata = {
  title: 'Pinzo | AI Visibility (AEO) & Google Business Profile Management Platform',
  description:
    'Be the business AI recommends. Pinzo combines Google Business Profile management, local SEO, review management and AI visibility (AEO) so customers find you on Google Search, Maps, ChatGPT, Gemini and Perplexity — from one dashboard.',
  keywords: [
    'AI visibility platform',
    'AEO',
    'answer engine optimization',
    'Google Business Profile management',
    'local SEO software',
    'AI review replies',
    'multi-location management',
    'local rank tracking',
  ],
  alternates: { canonical: 'https://pinzo.io' },
  openGraph: {
    title: 'Pinzo | Be the Business AI Recommends',
    description:
      'Manage Google Business Profiles, reviews, posts and local SEO — and get recommended by ChatGPT, Gemini, Perplexity and Google AI. One platform for local visibility in the AI era.',
    url: 'https://pinzo.io',
    siteName: 'Pinzo',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Pinzo | Be the Business AI Recommends',
    description:
      'AI Visibility (AEO), Google Business Profile management, local SEO and reputation — one dashboard for every location.',
  },
}

const JSON_LD = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'Pinzo',
  url: 'https://pinzo.io',
  applicationCategory: 'BusinessApplication',
  operatingSystem: 'Web',
  description:
    'AI Visibility (AEO) and Google Business Profile management platform. Pinzo helps multi-location businesses get found on Google Search, Google Maps, ChatGPT, Gemini and Perplexity with local SEO, review management, Google Posts and AI recommendations.',
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'USD', description: 'Free audit, no card required. 7-day free trial — no charge today.' },
  featureList: [
    'AI Visibility Score (AEO)',
    'Google Business Profile management',
    'Local SEO health score',
    'AI review replies',
    'Local rank heatmaps',
    'Google Posts scheduler',
    'Multi-location analytics',
  ],
}

export default function RootPage() {
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(JSON_LD) }} />
      <HomeClient />
    </>
  )
}
