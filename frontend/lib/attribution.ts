// First-touch / last-touch attribution. Captured once on landing, persisted in
// localStorage (cookies don't survive the Vercel<->Railway cross-domain hop, so
// we attach getAttribution() to API payloads instead). Also reads Meta's _fbp/_fbc
// cookies, which the Meta Pixel sets.
import { track } from "./analytics"

const KEY = "pinzo_attribution"

export type Attribution = {
  // first-touch (written once, never overwritten)
  utm_source?: string
  utm_medium?: string
  utm_campaign?: string
  utm_content?: string
  utm_term?: string
  gclid?: string
  gbraid?: string
  wbraid?: string
  fbclid?: string
  landing_page?: string
  first_page_path?: string
  referrer?: string
  device_type?: "mobile" | "tablet" | "desktop"
  first_touch?: string
  // last-touch (refreshed every visit that carries new params)
  last_touch?: string
  last_utm_source?: string
  last_utm_campaign?: string
}

function read(): Attribution {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}") } catch { return {} }
}
function write(a: Attribution) {
  try { localStorage.setItem(KEY, JSON.stringify(a)) } catch { /* private mode / full */ }
}

function getCookie(name: string): string | undefined {
  const m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)")
  return m?.pop()
}

function deviceType(ua: string): Attribution["device_type"] {
  if (/iPad|Tablet|PlayBook|Silk|(Android(?!.*Mobile))/i.test(ua)) return "tablet"
  if (/Mobi|Android|iPhone|iPod/i.test(ua)) return "mobile"
  return "desktop"
}

// Read the stored attribution + current Meta cookies, to attach to signup / checkout
// / payment API payloads. _fbp/_fbc come from the Pixel's cookies (not localStorage);
// _fbc is synthesized from fbclid if the Pixel hasn't set it yet.
export function getAttribution(): Attribution & { _fbp?: string; _fbc?: string } {
  if (typeof window === "undefined") return {}
  const a = read()
  const fbp = getCookie("_fbp")
  let fbc = getCookie("_fbc")
  if (!fbc && a.fbclid) fbc = `fb.1.${Date.now()}.${a.fbclid}`
  return { ...a, ...(fbp ? { _fbp: fbp } : {}), ...(fbc ? { _fbc: fbc } : {}) }
}

// Run once per page load (mounted in the root layout). Idempotent.
export function captureAttribution() {
  if (typeof window === "undefined") return
  const p = new URLSearchParams(window.location.search)
  const get = (k: string) => p.get(k) || undefined
  const now = new Date().toISOString()
  const a = read()

  // First touch: only fill fields that aren't set yet.
  if (!a.first_touch) {
    a.utm_source = get("utm_source")
    a.utm_medium = get("utm_medium")
    a.utm_campaign = get("utm_campaign")
    a.utm_content = get("utm_content")
    a.utm_term = get("utm_term")
    a.gclid = get("gclid")
    a.gbraid = get("gbraid")
    a.wbraid = get("wbraid")
    a.fbclid = get("fbclid")
    a.landing_page = window.location.pathname + window.location.search
    a.first_page_path = window.location.pathname
    a.referrer = document.referrer || undefined
    a.device_type = deviceType(navigator.userAgent)
    a.first_touch = now
  }

  // Last touch: always refresh the timestamp; update source/campaign if this visit has them.
  a.last_touch = now
  if (get("utm_source")) a.last_utm_source = get("utm_source")
  if (get("utm_campaign")) a.last_utm_campaign = get("utm_campaign")

  write(a)

  // Meta cookies set by the Pixel. Synthesize _fbc from fbclid if the pixel hasn't yet.
  const fbp = getCookie("_fbp")
  let fbc = getCookie("_fbc")
  if (!fbc && a.fbclid) fbc = `fb.1.${Date.now()}.${a.fbclid}`

  track("attribution_captured", {
    utm_source: a.utm_source,
    utm_campaign: a.utm_campaign,
    gclid: a.gclid,
    fbclid: a.fbclid,
    landing_page: a.landing_page,
    ...(fbp ? { _fbp: fbp } : {}),
    ...(fbc ? { _fbc: fbc } : {}),
    // full set available via getAttribution() for GTM variables / backend payloads.
  } as any)
}
