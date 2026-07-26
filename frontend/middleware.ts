import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { SUPPORTED_MARKETS } from '@/lib/markets'

// Derived from lib/markets.ts, the single source of truth. Bots enumerate /en-th,
// /en-de, /en-fr ... so unsupported locales are rejected at the edge: one cheap
// middleware invocation instead of a page render, a backend lookup and an ISR write.
// Deriving it means publishing a new market can never leave this list behind, which
// is exactly how 1,034 correctly-migrated pages once 404'd.
const SUPPORTED = SUPPORTED_MARKETS

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
