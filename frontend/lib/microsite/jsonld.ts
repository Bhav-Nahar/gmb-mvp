import type { PublicMicrositeData } from '@/types/microsite'

const typeMapping: Record<string, string> = {
  'hair salon': 'HairSalon',
  'beauty salon': 'BeautySalon',
  'nail salon': 'BeautySalon',
  'barber shop': 'BarberShop',
  'dentist': 'Dentist',
  'dental clinic': 'Dentist',
  'restaurant': 'Restaurant',
  'cafe': 'Cafe',
  'bakery': 'Bakery',
  'spa': 'DaySpa',
  'massage therapist': 'DaySpa',
  'doctor': 'MedicalBusiness',
  'medical clinic': 'MedicalBusiness',
  'auto repair': 'AutoRepair',
  'car wash': 'AutoWash',
  'hotel': 'Hotel',
  'gym': 'ExerciseGym',
  'fitness center': 'ExerciseGym',
  'store': 'Store',
  'shopping': 'Store',
  'plumber': 'Plumber',
  'electrician': 'Electrician',
  'home repair': 'HomeAndConstructionBusiness',
  'construction': 'HomeAndConstructionBusiness',
  'attorney': 'LegalBusiness',
  'law firm': 'LegalBusiness'
}

function getSubtype(category?: string | null): string {
  if (!category) return 'LocalBusiness'
  const catLower = category.toLowerCase()
  for (const [key, type] of Object.entries(typeMapping)) {
    if (catLower.includes(key)) return type
  }
  return 'LocalBusiness'
}

// BreadcrumbList structured data: Home > State > City > Business.
export function buildBreadcrumbJsonLd(microsite: PublicMicrositeData, slug: string): object {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io';
  const items: any[] = [{ name: 'Home', url: baseUrl }]
  if (microsite.state) items.push({ name: microsite.state })
  if (microsite.city) items.push({ name: microsite.city })
  items.push({ name: microsite.location_name, url: `${baseUrl}/${slug}` })

  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      ...(it.url ? { item: it.url } : {}),
    })),
  };
}

export function buildLocalBusinessJsonLd(microsite: PublicMicrositeData, slug: string): object {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || 'https://pinzo.io';

  const hasPhotos = microsite.photos && microsite.photos.length > 0;
  const hasReviews = microsite.reviews && microsite.reviews.length > 0;
  const hasGeo = microsite.latlng && microsite.latlng.latitude && microsite.latlng.longitude;

  const periods = microsite.business_hours?.periods;
  let openingHoursSpecification = undefined;

  if (Array.isArray(periods) && periods.length > 0) {
    openingHoursSpecification = periods.map((p: any) => ({
      "@type": "OpeningHoursSpecification",
      dayOfWeek: mapGoogleDayToSchema(p.openDay),
      opens: mapGoogleTimeToSchema(p.openTime),
      closes: mapGoogleTimeToSchema(p.closeTime),
    }));
  }

  const schemaType = getSubtype(microsite.primary_category)
  const sameAs = Array.isArray(microsite.social_links)
    ? microsite.social_links.map(l => l.url)
    : undefined

  return {
    "@context": "https://schema.org",
    "@type": schemaType,
    name: microsite.location_name ?? undefined,
    description: microsite.description ?? undefined,
    logo: microsite.logo ?? undefined,
    image: hasPhotos ? microsite.photos.slice(0, 5) : (microsite.logo ? [microsite.logo] : undefined),
    telephone: microsite.phone ?? undefined,
    url: `${baseUrl}/${slug}`,
    sameAs,
    address: microsite.address ? {
      "@type": "PostalAddress",
      streetAddress: microsite.address ?? undefined,
    } : undefined,
    geo: hasGeo ? {
      "@type": "GeoCoordinates",
      latitude: microsite.latlng?.latitude,
      longitude: microsite.latlng?.longitude,
    } : undefined,
    aggregateRating: microsite.total_reviews && microsite.total_reviews > 0 ? {
      "@type": "AggregateRating",
      ratingValue: microsite.average_rating,
      reviewCount: microsite.total_reviews,
    } : undefined,
    review: hasReviews ? microsite.reviews.slice(0, 5).map((r: any) => ({
      "@type": "Review",
      author: { "@type": "Person", name: r.reviewer_name },
      reviewRating: { "@type": "Rating", ratingValue: r.rating },
      reviewBody: r.comment ?? undefined,
    })) : undefined,
    openingHoursSpecification,
  };
}

function mapGoogleDayToSchema(day: any): string {
  if (typeof day === 'string') {
    const upper = day.toUpperCase();
    const mapping: Record<string, string> = {
      SUNDAY: 'Sunday', MONDAY: 'Monday', TUESDAY: 'Tuesday', 
      WEDNESDAY: 'Wednesday', THURSDAY: 'Thursday', FRIDAY: 'Friday', SATURDAY: 'Saturday'
    };
    return mapping[upper] || 'Monday';
  }
  const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  if (typeof day === 'number') {
    return days[day === 7 ? 0 : day];
  }
  return 'Monday';
}

function mapGoogleTimeToSchema(t: any): string {
  if (!t) return '00:00';
  if (typeof t === 'string' && t.length === 4) {
    return `${t.slice(0, 2)}:${t.slice(2, 4)}`;
  }
  if (t.hours !== undefined) {
    const h = t.hours.toString().padStart(2, '0');
    const m = (t.minutes || 0).toString().padStart(2, '0');
    return `${h}:${m}`;
  }
  return '00:00';
}
