import { NextRequest, NextResponse } from 'next/server'

// pSEO pages are served at /{locale}/gbp-management/... (e.g. /en-us/gbp-management/
// doctors-in-new-york-ny). A real [locale] route folder can't exist because it would
// collide with the microsite root route ([slug]) — two dynamic segments at the same
// level. So this middleware rewrites the locale-prefixed URL to the internal
// /gbp-management/... route and passes the locale along in a header. The matcher below
// scopes it to ONLY these paths, so every other request skips middleware entirely.

const LOCALE_GBP = /^\/(en-[a-z]{2})\/gbp-management(\/.*)?$/

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl
  const m = pathname.match(LOCALE_GBP)
  if (!m) return NextResponse.next()

  const locale = m[1]
  const rest = m[2] || '' // e.g. "/doctors-in-new-york-ny" or "" for the hub
  const url = req.nextUrl.clone()
  url.pathname = `/gbp-management${rest}`

  const headers = new Headers(req.headers)
  headers.set('x-pseo-locale', locale)
  return NextResponse.rewrite(url, { request: { headers } })
}

export const config = {
  matcher: ['/:locale(en-[a-z]{2})/gbp-management/:path*'],
}
