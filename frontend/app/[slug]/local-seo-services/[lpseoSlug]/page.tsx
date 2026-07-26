import type { Metadata } from 'next'
import { notFound } from 'next/navigation'
import LpseoLanding from '@/components/lpseo/LpseoLanding'
import CityPillar from '@/components/cityseo/CityPillar'
import PseoHub from '@/components/pseo/PseoHub'
import {
  getLpseoPage, listLpseoPages, lpseoPath, industryHubPath, rootHubPath, localeToCountry,
  isLpseoPillar, noSlash, getLiveFamilyPaths,
} from '@/lib/lpseo'
import { isCityPillar, asCityPage } from '@/lib/cityseo'

// Served at /{locale}/local-seo-services/{lpseoSlug}. [slug] is the locale (Next.js
// forbids two dynamic names at one level, so it reuses the microsite segment name).
// lpseoSlug is a leaf ({industry}-in-{city}) or an industry hub ({industry}).
// True ISR: 1-year fallback; admin publish/flush busts earlier via the 'lpseo' tags.
export const revalidate = 31536000

export function generateStaticParams(): Params[] {
  return []
}

const SITE_URL = process.env.NEXT_PUBLIC_APP_URL || 'https://www.pinzo.io'
const LOCALE_RE = /^en-[a-z]{2}$/

type Params = { slug: string; lpseoSlug: string }

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) return { title: 'Not Found' }
  const page = await getLpseoPage(params.lpseoSlug)

  if (page && page.locale === locale) {
    const canonical = noSlash(page.canonical_url || `${SITE_URL}${lpseoPath(page.locale, page.slug)}`)
    const noindex = page.index_status === 'noindex'
    const ogImage = page.content?.og_image || `${SITE_URL}/logo-horizontal-3.png`
    return {
      title: page.meta_title,
      description: page.meta_description,
      robots: { index: !noindex, follow: true },
      alternates: {
        canonical,
        // x-default is the GLOBAL pillar, not this page. Pointing it at itself made
        // every industry pillar, city pillar and leaf its own default variant.
        languages: { [page.locale]: canonical, 'x-default': `${SITE_URL}/local-seo-services` },
      },
      openGraph: { title: page.meta_title, description: page.meta_description, url: canonical, siteName: 'Pinzo', type: 'website', images: [{ url: ogImage }] },
      twitter: { card: 'summary_large_image', title: page.meta_title, description: page.meta_description, images: [ogImage] },
    }
  }

  if (!page) {
    const cities = await listLpseoPages({ industry: params.lpseoSlug, country: localeToCountry(locale) })
    if (cities.length > 0) {
      const label = cities[0].industry_label
      const canonical = `${SITE_URL}${industryHubPath(locale, params.lpseoSlug)}`
      return {
        title: `Local SEO Services for ${label} | Pinzo`,
        description: `Managed local SEO for ${label.toLowerCase()} across Google Maps, local search and AI recommendations. Pick your city.`,
        robots: { index: true, follow: true },
        alternates: { canonical },
      }
    }
  }
  return { title: 'Not Found', description: 'The requested page could not be found.' }
}

export default async function LocalSeoSlugPage({ params }: { params: Params }) {
  const locale = params.slug
  if (!LOCALE_RE.test(locale)) notFound()
  const page = await getLpseoPage(params.lpseoSlug)

  if (page) {
    // Wrong-locale prefix -> 404 so the two markets never serve duplicate content.
    if (locale !== page.locale) notFound()

    // City pillar ({city} slug): its own template and content schema.
    if (isCityPillar(page)) {
      return <CityPillar page={asCityPage(page)}
        livePaths={await getLiveFamilyPaths(page.country, page.locale)} />
    }

    // Sibling city pages (same industry + market) for contextual internal links.
    // The industry pillar is never a "sibling city" of its own children, so it is
    // filtered out before the rotation rather than eating one of the six slots.
    const all = (await listLpseoPages({ industry: page.industry_slug, country: page.country }))
      .filter((p) => !isLpseoPillar(p))
    const idx = all.findIndex((p) => p.slug === page.slug)
    // The pillar links every child (that is its routing job); a leaf shows a sample.
    const siblings = isLpseoPillar(page)
      ? all
      : idx === -1 ? [] : [...all.slice(idx + 1), ...all.slice(0, idx)].slice(0, 6)
    // Only pages that are actually published and indexable may be linked; the
    // authored CSVs list the full planned set long before those pages exist.
    const livePaths = await getLiveFamilyPaths(page.country, page.locale)
    return <LpseoLanding page={page} siblings={siblings} livePaths={livePaths} />
  }

  // Industry hub — scoped to this locale's market.
  const country = localeToCountry(locale)
  const cities = await listLpseoPages({ industry: params.lpseoSlug, country })
  if (cities.length > 0) {
    const label = cities[0].industry_label
    return (
      <PseoHub
        crumbs={[{ label: 'Home', href: '/' }, { label: 'Local SEO Services', href: rootHubPath(locale) }, { label }]}
        title={`Local SEO services for ${label.toLowerCase()}`}
        subtitle={`Choose your city to see how Pinzo grows ${label.toLowerCase()} visibility across Google Maps, local organic search and AI recommendations.`}
        cards={cities.map((c) => ({
          href: lpseoPath(locale, c.slug),
          title: `${label} in ${c.city_label}`,
          subtitle: c.city_label,
        }))}
      />
    )
  }

  notFound()
}
