// Single source of truth for the GTM dataLayer. Every push goes through track().
// Debug: `window.dataLayer` in console, or set NEXT_PUBLIC_ANALYTICS_DEBUG=1 to log each push.

export type CtaLocation =
  | "hero" | "pricing" | "navbar" | "header" | "footer" | "faq" | "mobile_menu" | "login_page" | "sticky_mobile" | "sync_failed"

// All params we may ever send (the agreed global schema). All optional — push only what's known.
type EventParams = {
  event_id?: string
  lead_id?: string
  user_id?: string
  email?: string // raw; hashed in GTM before any send (never to GA4 unhashed)
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
  method?: string // GA4 sign_up: how the account was created (e.g. "google")
}

declare global {
  interface Window { dataLayer?: Record<string, any>[] }
}

export function generateEventId(): string {
  // crypto.randomUUID is native in all browsers we support
  return "evt_" + crypto.randomUUID()
}

// Drop empty values so we never push "" / null / undefined.
function strip(params: EventParams): Record<string, any> {
  const clean: Record<string, any> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") clean[k] = v
  }
  return clean
}

// The only function that pushes to the dataLayer. Strips empty values, auto-adds page_path.
// `group` nests the params under that key, e.g. { event, user: {...} }. Omit for a flat push.
export function track(event: string, params: EventParams = {}, group?: string): void {
  if (typeof window === "undefined") return
  const clean = strip(params)
  if (clean.page_path === undefined) clean.page_path = window.location.pathname
  let payload: Record<string, any>
  if (group) {
    // event_id stays top-level (alongside event); everything else nests under `group`.
    const { event_id, ...rest } = clean
    payload = { event, ...(event_id ? { event_id } : {}), [group]: rest }
  } else {
    payload = { event, ...clean }
  }
  window.dataLayer = window.dataLayer || []
  // GTM merges objects across pushes, so a field set in a prior event leaks into this
  // one. Clear the wrapper first so each event only carries what it explicitly sets.
  if (group) window.dataLayer.push({ [group]: null })
  window.dataLayer.push(payload)
  if (process.env.NEXT_PUBLIC_ANALYTICS_DEBUG) console.debug("[dataLayer]", payload)
}

// Ecommerce events (add_payment_info, begin_checkout, purchase). GA4's built-in ecommerce
// reports only read the reserved `ecommerce` object + its `items` array, so money lives
// there and identity under `user`. We push { ecommerce: null } first to clear the prior
// object — otherwise its values leak into the next event. event_id stays top-level.
function trackEcom(
  event: string,
  ecommerce: Record<string, any>,
  user: EventParams,
  event_id: string,
): void {
  if (typeof window === "undefined") return
  const u = strip(user)
  u.page_path = window.location.pathname
  const payload = { event, event_id, ecommerce, user: u }
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({ ecommerce: null, user: null }) // clear both so neither leaks
  window.dataLayer.push(payload)
  if (process.env.NEXT_PUBLIC_ANALYTICS_DEBUG) console.debug("[dataLayer]", payload)
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
  email?: string
}) {
  track("trial_start", {
    event_id: generateEventId(),
    lead_magnet: "7_day_trial",
    user_id: String(opts.user_id),
    email: opts.email,
    business_category: opts.business_category,
    locations_count: bucketLocations(opts.locationsCount),
    plan_name: "Trial",
    value: 0,
    currency: "INR",
  }, "user")
}

// "annual" is the UI's word; the schema uses "yearly".
const toBillingCycle = (t: "monthly" | "annual") => (t === "annual" ? "yearly" : "monthly")

// The configurable plan payload, shared by add_payment_info and purchase.
type PlanSelection = {
  plan_name: string
  paymentTerm: "monthly" | "annual"
  value: number // plan price in rupees (base, ex-GST)
  locations_included: number
  user_id?: number | string
  email?: string
}

// One GA4 items entry for a plan. billing cycle -> item_variant, locations -> quantity.
const planItem = (p: PlanSelection) => ({
  item_name: p.plan_name,
  item_variant: toBillingCycle(p.paymentTerm),
  price: p.value,
  quantity: 1,
  locations_included: p.locations_included,
})

// User picked a plan tier in the upgrade modal. Mapped to GA4's add_payment_info.
export function trackAddPaymentInfo(p: PlanSelection) {
  trackEcom(
    "add_payment_info",
    { currency: "INR", value: p.value, items: [planItem(p)] },
    { lead_magnet: "direct_plan", email: p.email, ...(p.user_id ? { user_id: String(p.user_id) } : {}) },
    generateEventId(),
  )
}

// User started the checkout flow (opened the upgrade modal). No plan is configured
// yet, so there's nothing for the ecommerce object — items is empty.
export function trackBeginCheckout(p: { user_id?: number | string; email?: string } = {}) {
  trackEcom(
    "begin_checkout",
    { currency: "INR", items: [] },
    { lead_magnet: "direct_plan", email: p.email, ...(p.user_id ? { user_id: String(p.user_id) } : {}) },
    generateEventId(),
  )
}

// Payment verified & subscription activated.
export function trackPurchase(p: {
  transaction_id: string
  plan_name: string
  paymentTerm: "monthly" | "annual"
  value: number // amount actually charged in rupees (incl. GST)
  locations_included: number
  user_id?: number | string
  email?: string
}) {
  trackEcom(
    "purchase",
    {
      transaction_id: p.transaction_id,
      currency: "INR",
      value: p.value,
      items: [planItem(p)],
    },
    { lead_magnet: "direct_plan", payment_status: "success", email: p.email, ...(p.user_id ? { user_id: String(p.user_id) } : {}) },
    // Deterministic id from the txn so the backend Meta CAPI event can use the SAME
    // event_id and Meta dedupes browser + server. No id needs passing around.
    "evt_" + p.transaction_id,
  )
}

// Raw PII pushed for GTM to hash before any send (never leaves GTM unhashed).
// device_type auto-detected; pass to override. gtm.uniqueEventId is normally
// GTM-managed — omit it unless a tag specifically reads a value you set.
export function trackCustomerData(c: {
  name: string
  mobile: string
  email: string
  device_type?: "desktop" | "mobile" | "tablet"
}) {
  if (typeof window === "undefined") return
  const device_type =
    c.device_type ?? (window.matchMedia("(max-width: 767px)").matches ? "mobile" : "desktop")
  window.dataLayer = window.dataLayer || []
  window.dataLayer.push({ customer: null }) // clear so prior fields don't leak
  window.dataLayer.push({
    event: "customerData",
    customer: { name: c.name, mobile: c.mobile, email: c.email, device_type },
  })
  if (process.env.NEXT_PUBLIC_ANALYTICS_DEBUG) console.debug("[dataLayer] customerData")
}

// Fires at /login/success after OAuth completes — the account exists, so this is
// GA4's sign_up (completed), not merely "started". method = the OAuth provider.
export function trackSignUp() {
  const cta_location = (typeof window !== "undefined"
    ? sessionStorage.getItem(CTA_KEY)
    : null) as CtaLocation | null
  sessionStorage.removeItem(CTA_KEY) // consume so a back-nav can't re-fire it
  track("sign_up", {
    event_id: generateEventId(),
    lead_magnet: "7_day_trial",
    method: "google",
    ...(cta_location ? { cta_location } : {}),
  }, "user")
}
