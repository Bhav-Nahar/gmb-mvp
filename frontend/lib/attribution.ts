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
  first_touch?: string
  // _fbp / _fbc snapshotted from the Pixel's cookies (and _fbc synthesized from fbclid
  // once if the Pixel hasn't set it yet), persisted so they survive to the post-OAuth
  // page even if the cookie isn't readable at that instant.
  fbp?: string
  fbc?: string
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

// Read the stored attribution + current Meta cookies, to attach to signup / checkout
// / payment API payloads. _fbp/_fbc come from the Pixel's cookies (not localStorage);
// _fbc falls back to the value synthesized & persisted in captureAttribution.
export function getAttribution(): Attribution & { _fbp?: string; _fbc?: string } {
  if (typeof window === "undefined") return {}
  const a = read()
  const fbp = getCookie("_fbp") || a.fbp
  const fbc = getCookie("_fbc") || a.fbc
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
    a.first_touch = now
  }

  // Meta cookies set by the Pixel. Snapshot _fbp whenever present, and synthesize _fbc
  // from fbclid ONCE if the pixel hasn't set it yet — persist both so getAttribution()
  // still has them on the post-OAuth page even if the cookie read is flaky there.
  const fbpCookie = getCookie("_fbp")
  if (fbpCookie) a.fbp = fbpCookie
  if (!getCookie("_fbc") && a.fbclid && !a.fbc) a.fbc = `fb.1.${Date.now()}.${a.fbclid}`
  const fbp = fbpCookie || a.fbp
  const fbc = getCookie("_fbc") || a.fbc

  write(a)

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
