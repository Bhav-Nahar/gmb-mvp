import { Metadata } from 'next'
import { notFound } from 'next/navigation'
import Hero from '@/components/microsite/Hero'
import ServicesSection from '@/components/microsite/ServicesSection'
import Gallery from '@/components/microsite/Gallery'
import ReviewsSection from '@/components/microsite/ReviewsSection'
import ContactSection from '@/components/microsite/ContactSection'
import CTASection from '@/components/microsite/CTASection'
import StickyNav from '@/components/microsite/StickyNav'
import SocialLinks from '@/components/microsite/SocialLinks'
import Breadcrumbs from '@/components/microsite/Breadcrumbs'
import AboutSection from '@/components/microsite/AboutSection'
import LeadForm from '@/components/microsite/LeadForm'
import Footer from '@/components/microsite/Footer'
import { buildLocalBusinessJsonLd, buildBreadcrumbJsonLd } from '@/lib/microsite/jsonld'

// Enable ISR caching (revalidate every 3600 seconds / 1 hour)
export const revalidate = 3600

async function getMicrositeData(slug: string) {
  // Use internal routing for docker-compose SSR, fallback to public URL
  const apiBaseUrl = process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://backend:8000/api/v1'
  let url = `${apiBaseUrl}/public/microsites/${slug}`

  if (url.includes('localhost')) {
    url = url.replace('localhost', 'backend')
  }

  try {
    const res = await fetch(url, { next: { revalidate: 3600 } })
    if (res.status === 404) return null
    if (!res.ok) return null
    return res.json()
  } catch (error) {
    console.error("Failed to fetch microsite data:", error)
    return null
  }
}

export async function generateMetadata({ params }: { params: { slug: string } }): Promise<Metadata> {
  const data = await getMicrositeData(params.slug)

  if (!data) {
    return {
      title: 'Not Found',
      description: 'The requested page could not be found.'
    }
  }

  const { location_name, primary_category, city, photos, logo } = data
  const title = `${location_name} — ${primary_category || 'Business'} in ${city || 'your area'}`
  // Description comes from the Google Business Profile; only fall back to a
  // templated line if GBP has no description. Meta descriptions cap ~160 chars.
  const gbpDesc = (data.description || '').trim()
  const description = gbpDesc
    ? (gbpDesc.length > 300 ? gbpDesc.slice(0, 297) + '…' : gbpDesc)
    : `${location_name} is a ${primary_category || 'business'} located in ${city || 'your area'}. Contact, hours, reviews, and directions.`
  // Prefer the brand logo for OG/branding, fall back to the first gallery photo.
  const ogImage = logo || (photos && photos.length > 0 ? photos[0] : undefined)

  return {
    title,
    description,
    robots: {
      index: true,
      follow: true,
    },
    openGraph: {
      title,
      description,
      images: ogImage ? [
        {
          url: ogImage,
          width: 1200,
          height: 630,
          alt: `${location_name} Brand Logo / Cover`,
        }
      ] : [],
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: ogImage ? [ogImage] : [],
    },
    alternates: {
      canonical: `${process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io'}/${params.slug}`
    }
  }
}

export default async function MicrositePage({ params }: { params: { slug: string } }) {
  const data = await getMicrositeData(params.slug)

  if (!data) {
    // 404 for missing/draft/unpublished. We intentionally do NOT run middleware to
    // return a distinct 410 — that would require an uncached per-request fetch on
    // every visit. Keeping this fully static ISR; 404 and 410 both deindex in search.
    notFound()
  }

  const jsonLd = buildLocalBusinessJsonLd(data, params.slug)
  const breadcrumbJsonLd = buildBreadcrumbJsonLd(data, params.slug)
  const homeUrl = process.env.NEXT_PUBLIC_APP_URL || '/'

  // In-page nav links — only for sections that actually have content.
  const sections = [
    !!(data.description && data.description.trim()) && { id: 'about', label: 'About' },
    Array.isArray(data.service_items) && data.service_items.length > 0 && { id: 'services', label: 'Services' },
    Array.isArray(data.photos) && data.photos.length > 0 && { id: 'photos', label: 'Photos' },
    Array.isArray(data.reviews) && data.reviews.length > 0 && { id: 'reviews', label: 'Reviews' },
    { id: 'enquiry', label: 'Enquiry' },
    { id: 'contact', label: 'Contact' },
  ].filter(Boolean) as { id: string; label: string }[]

  // Directions link: coordinates if available, else the address (service-area
  // businesses have no latlng pin from GBP).
  const mapQuery = (data.latlng?.latitude && data.latlng?.longitude)
    ? `${data.latlng.latitude},${data.latlng.longitude}`
    : (data.address || null)
  const mapLink = mapQuery
    ? `https://www.google.com/maps/search/?${new URLSearchParams({ api: '1', query: mapQuery }).toString()}`
    : null

  // Social/contact links come straight from GBP (only what the business actually set).
  const socialLinks = (data.social_links || []) as { type: string; label: string; url: string }[]
  const whatsapp = socialLinks.find((s) => s.type === 'whatsapp')?.url || null
  const otherSocials = socialLinks.filter((s) => s.type !== 'whatsapp')

  return (
    <main id="top" className="min-h-screen bg-background font-sans selection:bg-primary/30 selection:text-primary">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(breadcrumbJsonLd) }}
      />

      <StickyNav
        name={data.location_name}
        logo={data.logo}
        phone={data.phone}
        mapLink={mapLink}
        whatsapp={whatsapp}
        sections={sections}
      />

      <Breadcrumbs
        name={data.location_name}
        city={data.city}
        state={data.state}
        homeUrl={homeUrl}
      />

      <Hero
        name={data.location_name}
        category={data.primary_category}
        rating={data.average_rating}
        totalReviews={data.total_reviews}
        logo={data.logo}
        cover={data.cover}
        phone={data.phone}
        whatsapp={whatsapp}
        mapLink={mapLink}
      />

      <AboutSection description={data.description} name={data.location_name} />

      <ServicesSection serviceItems={data.service_items} />

      <Gallery photos={data.photos} />

      <ReviewsSection
        reviews={data.reviews}
        averageRating={data.average_rating}
        totalReviews={data.total_reviews}
        reviewUrl={data.review_url}
      />

      <LeadForm
        slug={params.slug}
        businessName={data.location_name}
        whatsapp={whatsapp}
      />

      <ContactSection
        address={data.address}
        phone={data.phone}
        website={data.website}
        businessHours={data.business_hours}
        latlng={data.latlng}
        mapsUrl={data.maps_url}
      />

      <CTASection
        phone={data.phone}
        website={data.website}
        mapLink={mapLink}
        whatsapp={whatsapp}
        reviewUrl={data.review_url}
      />

      <SocialLinks links={otherSocials} />

      <Footer businessName={data.location_name} />

      {/* Floating Mobile CTA Action Bar */}
      <div className="fixed bottom-0 left-0 right-0 z-40 lg:hidden glass-panel border-t border-border/50 shadow-[0_-8px_30px_rgb(0,0,0,0.1)] px-3 py-4 pb-safe-bottom flex items-center justify-between gap-2 rounded-t-[2rem]">
        {whatsapp ? (
          <a 
            href={whatsapp} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="flex-none inline-flex items-center justify-center w-12 h-12 bg-[#25D366] text-white rounded-full hover:brightness-95 transition-all shadow-md active:scale-95"
            aria-label="WhatsApp"
          >
            <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor"><path d="M17.5 14.4c-.3-.15-1.77-.87-2.04-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.95 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.9-.8-1.5-1.78-1.67-2.08-.17-.3-.02-.46.13-.6.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.5-.17-.01-.37-.01-.57-.01-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.48 0 1.46 1.07 2.88 1.22 3.08.15.2 2.1 3.2 5.08 4.49.71.3 1.26.49 1.7.63.71.22 1.36.19 1.87.12.57-.09 1.77-.72 2.02-1.42.25-.7.25-1.3.17-1.42-.07-.13-.27-.2-.57-.35zM12 2a10 10 0 00-8.5 15.3L2 22l4.8-1.5A10 10 0 1012 2z"/></svg>
          </a>
        ) : (
          <a 
            href="#enquiry" 
            className="flex-none inline-flex items-center justify-center w-12 h-12 bg-indigo-600 text-white rounded-full hover:bg-indigo-700 transition-all shadow-md active:scale-95"
            aria-label="Enquiry"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" /></svg>
          </a>
        )}
        {data.phone && (
          <a 
            href={`tel:${data.phone}`} 
            className="flex-1 min-w-0 inline-flex items-center justify-center gap-1.5 bg-primary text-primary-foreground text-xs font-bold py-3.5 px-2 rounded-xl hover:bg-primary/90 transition-all shadow-sm active:scale-95"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
            <span className="truncate">Call</span>
          </a>
        )}
        {mapLink && (
          <a 
            href={mapLink} 
            target="_blank" 
            rel="noopener noreferrer" 
            className="flex-1 min-w-0 inline-flex items-center justify-center gap-1.5 bg-slate-900 text-white text-xs font-bold py-3.5 px-2 rounded-xl hover:bg-slate-800 transition-all shadow-sm active:scale-95"
          >
            <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
            <span className="truncate">Directions</span>
          </a>
        )}
      </div>
    </main>
  )
}
