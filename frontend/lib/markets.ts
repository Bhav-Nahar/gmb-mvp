// The single source of truth for which markets we publish pSEO / lpSEO pages in.
//
// This used to be duplicated: an allow-list in middleware.ts and a COUNTRY_NAMES map
// in lib/pseo.ts and lib/lpseo.ts, with a comment saying they "MUST mirror" each
// other. They drifted. 1,034 pages were re-filed into nine new countries, the pages
// and sitemap were correct, and every one of them 404'd because the edge allow-list
// had not been updated — the request died in middleware before the route ever ran.
//
// Keep it a plain object with no imports: middleware runs on the edge runtime, so
// anything pulled in here ends up in the edge bundle.
export const MARKETS: Record<string, string> = {
  in: 'India',
  us: 'United States',
  gb: 'United Kingdom',
  ca: 'Canada',
  au: 'Australia',
  ae: 'UAE',
  sg: 'Singapore',
  za: 'South Africa',
  ie: 'Ireland',
  nz: 'New Zealand',
  th: 'Thailand',
  id: 'Indonesia',
  ph: 'Philippines',
  my: 'Malaysia',
  sa: 'Saudi Arabia',
  qa: 'Qatar',
  bh: 'Bahrain',
  kw: 'Kuwait',
  om: 'Oman',
}

/** ISO alpha-2 codes we serve. Derived, so it can never fall out of step. */
export const SUPPORTED_MARKETS: ReadonlySet<string> = new Set(Object.keys(MARKETS))

export const marketName = (code: string) => MARKETS[code] || code.toUpperCase()
