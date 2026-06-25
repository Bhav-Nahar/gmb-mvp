/**
 * Matches PublicMicrositeSchema and PublicReviewSchema in
 * backend/app/schemas/public_microsite.py
 */
export interface PublicReview {
  reviewer_name: string
  reviewer_profile_photo?: string | null
  rating?: number | null
  comment?: string | null
  review_created_at: string
  reply_text?: string | null
  reply_created_at?: string | null
}

export interface PublicMicrositeData {
  location_name: string
  primary_category?: string | null
  average_rating?: number | null
  total_reviews?: number | null
  description?: string | null
  logo?: string | null
  cover?: string | null

  // Contact / location
  address?: string | null
  city?: string | null
  state?: string | null
  phone?: string | null
  social_links?: { type: string; label: string; url: string }[]
  website?: string | null
  business_hours?: Record<string, any> | null
  latlng?: { latitude: number; longitude: number } | null
  maps_url?: string | null
  review_url?: string | null

  // Rich content
  service_items: any[]
  photos: string[]
  reviews: PublicReview[]

  // Routing / state
  status: 'draft' | 'published' | 'unpublished'
}
