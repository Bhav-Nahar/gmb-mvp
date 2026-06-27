// Single source of truth for the GTM dataLayer. Every push goes through track().
// Debug: `window.dataLayer` in console, or set NEXT_PUBLIC_ANALYTICS_DEBUG=1 to log each push.

export type CtaLocation =
  | "hero" | "pricing" | "navbar" | "header" | "footer" | "faq" | "mobile_menu" | "login_page"

// All params we may ever send (the agreed global schema). All optional — push only what's known.
type EventParams = {
  event_id?: string
  lead_id?: string
  user_id?: string
  lead_magnet?: "7_day_trial" | "custom_plan" | "direct_plan"
  user_type?: "agency" | "brand" | "local_business"
  business_category?: string
  locations_count?: "1" | "2-5" | "6-20" | "20+"
  plan_name?: string // actual tier name: "Trial" | "Basic" | "Pro" | ...
  billing_cycle?: "monthly" | "yearly"
  currency?: string
  value?: number
  locations_included?: number
  transaction_id?: string
  payment_status?: string
  cta_location?: CtaLocation
  page_path?: string
  utm_source?: string
  gclid?: string
  gbraid?: string
  wbraid?: string
  fbclid?: string
}

declare global {
  interface Window { dataLayer?: Record<string, any>[] }
}

export function generateEventId(): string {
  // crypto.randomUUID is native in all browsers we support
  return "evt_" + (globalThis.crypto?.randomUUID?.() ?? Date.now().toString(36) + Math.random().toString(36).slice(2))
}

// The only function that pushes to the dataLayer. Strips empty values, auto-adds page_path.
export function track(event: string, params: EventParams = {}): void {
  if (typeof window === "undefined") return
  const clean: Record<string, any> = { event }
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") clean[k] = v
  }
  if (clean.page_path === undefined) clean.page_path = window.location.pathname
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push(clean)
  if (process.env.NEXT_PUBLIC_ANALYTICS_DEBUG) console.debug("[dataLayer]", clean)
}

// ---- Event helpers. Add one per tracked event so call sites stay declarative. ----

// cta_location is known at click time but the event fires after OAuth returns.
// Stash it so the success callback can read it. sessionStorage = survives the
// Google redirect round-trip, auto-clears when the tab closes.
const CTA_KEY = "pinzo_signup_cta"

export function rememberCtaLocation(cta_location: CtaLocation) {
  if (typeof window !== "undefined") sessionStorage.setItem(CTA_KEY, cta_location)
}

// Fire once, only after OAuth gives us a successful result (call from login/success).
// Map a raw location count to the agreed schema bucket. <=0 -> undefined (omitted).
export function bucketLocations(n: number): EventParams["locations_count"] {
  if (n <= 0) return undefined
  if (n === 1) return "1"
  if (n <= 5) return "2-5"
  if (n <= 20) return "6-20"
  return "20+"
}

// Fire once, after the user's FIRST GBP sync completes successfully (we only then
// know their locations). business_category is blank if no location came back.
export function trackTrialStart(opts: {
  user_id: number | string
  locationsCount: number
  business_category?: string
}) {
  track("trial_start", {
    event_id: generateEventId(),
    lead_magnet: "7_day_trial",
    user_id: String(opts.user_id),
    business_category: opts.business_category,
    locations_count: bucketLocations(opts.locationsCount),
    plan_name: "Trial",
    value: 0,
    currency: "INR",
  })
}

// "annual" is the UI's word; the schema uses "yearly".
const toBillingCycle = (t: "monthly" | "annual") => (t === "annual" ? "yearly" : "monthly")

// The configurable plan payload, shared by select_plan and begin_checkout.
type PlanSelection = {
  plan_name: string
  paymentTerm: "monthly" | "annual"
  value: number // plan price in rupees (base, ex-GST)
  locations_included: number
  user_id?: number | string
}

function planParams(p: PlanSelection): EventParams {
  return {
    event_id: generateEventId(),
    lead_magnet: "direct_plan",
    ...(p.user_id ? { user_id: String(p.user_id) } : {}),
    plan_name: p.plan_name,
    billing_cycle: toBillingCycle(p.paymentTerm),
    value: p.value,
    currency: "INR",
    locations_included: p.locations_included,
  }
}

// User picked a plan tier in the upgrade modal.
export function trackSelectPlan(p: PlanSelection) {
  track("select_plan", planParams(p))
}

// User started the checkout flow (opened the upgrade modal). No plan is configured
// yet, so every field is optional — track() omits whatever is blank.
export function trackBeginCheckout(p: { user_id?: number | string } = {}) {
  track("begin_checkout", {
    event_id: generateEventId(),
    lead_magnet: "direct_plan",
    ...(p.user_id ? { user_id: String(p.user_id) } : {}),
  })
}

// Payment verified & subscription activated.
export function trackPurchase(p: {
  transaction_id: string
  plan_name: string
  paymentTerm: "monthly" | "annual"
  value: number // amount actually charged in rupees (incl. GST)
  user_id?: number | string
}) {
  track("purchase", {
    // Deterministic id from the txn so the backend Meta CAPI event can use the
    // SAME event_id and Meta dedupes browser + server. No id needs passing around.
    event_id: "evt_" + p.transaction_id,
    lead_magnet: "direct_plan",
    ...(p.user_id ? { user_id: String(p.user_id) } : {}),
    transaction_id: p.transaction_id,
    plan_name: p.plan_name,
    billing_cycle: toBillingCycle(p.paymentTerm),
    value: p.value,
    currency: "INR",
    payment_status: "success",
  })
}

export function trackSignUpStart() {
  const cta_location = (typeof window !== "undefined"
    ? sessionStorage.getItem(CTA_KEY)
    : null) as CtaLocation | null
  sessionStorage.removeItem(CTA_KEY) // consume so a back-nav can't re-fire it
  track("sign_up_start", {
    event_id: generateEventId(),
    lead_magnet: "7_day_trial",
    ...(cta_location ? { cta_location } : {}),
  })
}
