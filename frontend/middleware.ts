import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// Markets we actually publish pSEO/lpSEO pages for. MUST mirror COUNTRY_NAMES in
// lib/pseo.ts — bots enumerate /en-th, /en-my, /en-id, /en-sa ... which have no
// pages and 404. Without this, each junk URL still invokes the page render + a
// backend getPseoPage lookup and caches the notFound() (a Vercel function call +
// ISR write for nothing). Rejecting the unsupported locale here, at the edge,
// costs one cheap middleware invocation and zero ISR writes.
const SUPPORTED = new Set(['in', 'us', 'gb', 'ca', 'au', 'ae', 'sg', 'za', 'ie', 'nz'])

// /{en-xx}/gbp-management/... or /{en-xx}/local-seo-services/...
const SEO_LOCALE = /^\/en-([a-z]{2})\/(?:gbp-management|local-seo-services)(?:\/|$)/

// Pure + exported so it's unit-testable without the Next runtime.
export function isUnsupportedSeoLocale(pathname: string): boolean {
  const m = pathname.match(SEO_LOCALE)
  return !!m && !SUPPORTED.has(m[1])
}

export function middleware(req: NextRequest) {
  if (isUnsupportedSeoLocale(req.nextUrl.pathname)) {
    // Bare 404 — bots only need the status; avoids re-invoking the 404 page render.
    return new NextResponse(null, { status: 404 })
  }
  return NextResponse.next()
}

export const config = {
  // Only the two pSEO trees; everything else skips middleware entirely.
  matcher: ['/:locale/gbp-management/:path*', '/:locale/local-seo-services/:path*'],
}
