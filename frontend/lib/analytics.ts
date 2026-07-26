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
  // GA4 promotion params (select_promotion / view_promotion)
  promotion_id?: string
  promotion_name?: string
  creative_slot?: string
  // GA4 select_content params
  content_type?: string
  item_id?: string
  // GA4 exception params
  description?: string
  fatal?: boolean
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

// ── Paid-landing audit funnel ────────────────────────────────────────────────
//
// Every step uses a name GA4 already knows, so the funnel and the Google Ads
// conversion are configurable without defining a single custom event:
//
//   select_promotion  audit CTA clicked
//   view_promotion    lead form opened
//   form_start        first field touched — GA4 Enhanced Measurement ("Form
//                     interactions") emits this itself; we deliberately do NOT
//                     push it, or it would double-count
//   form_submit       same, emitted by Enhanced Measurement on the submit event
//   generate_lead     backend CONFIRMED the lead  ← mark key event, import to Ads
//   exception         submission failed
//
// generate_lead nests identity under `user`, exactly like sign_up, so existing
// GTM user.* variables work on it unchanged.
const AUDIT_PROMO = { promotion_id: "free_gbp_audit", promotion_name: "Free GBP audit" }

export function trackAuditCtaClick(cta_location: CtaLocation) {
  track("select_promotion", {
    event_id: generateEventId(), ...AUDIT_PROMO, creative_slot: cta_location, cta_location,
  })
}

export function trackAuditFormOpen(cta_location: CtaLocation) {
  track("view_promotion", {
    event_id: generateEventId(), ...AUDIT_PROMO, creative_slot: cta_location, cta_location,
  })
}

// Fire ONCE, only after the API confirms the lead row exists — never on submit
// click. This is the event Google Ads should import as the conversion goal.
export function trackGenerateLead(o: {
  lead_id?: number | string
  cta_location?: CtaLocation
  locationsCount?: number
  email?: string
}) {
  track("generate_lead", {
    event_id: generateEventId(),
    lead_magnet: "custom_plan",
    ...(o.lead_id !== undefined ? { lead_id: String(o.lead_id) } : {}),
    ...(o.cta_location ? { cta_location: o.cta_location } : {}),
    locations_count: o.locationsCount ? bucketLocations(o.locationsCount) : undefined,
    email: o.email,
  }, "user")
}

// GA4's standard error event, so a failed submit is visible in the same funnel
// without inventing an event name. fatal:false — the visitor can retry.
export function trackFormError(description: string) {
  track("exception", { event_id: generateEventId(), description, fatal: false })
}

// WhatsApp is a separate contact path from the audit form, so it gets its own
// countable event — select_content is GA4's recommended name for "tapped a thing".
export function trackWhatsAppClick(cta_location: CtaLocation) {
  track("select_content", {
    event_id: generateEventId(), content_type: "whatsapp", item_id: cta_location, cta_location,
  })
}

// Fires at /login/success after OAuth completes — the account exists, so this is
// GA4's sign_up (completed), not merely "started". method = the OAuth provider.
//
// The audit lead form also calls this (method: "audit_form"), because the Ads
// conversion goal is currently built on sign_up — see trackLeadSignUp below.
// Passing cta_location explicitly skips the sessionStorage lookup, so a form
// submit can't consume a CTA that a pending OAuth round-trip still needs.
export function trackSignUp(o: {
  method?: string
  lead_magnet?: EventParams["lead_magnet"]
  cta_location?: CtaLocation
  email?: string
  lead_id?: number | string
} = {}) {
  let cta_location = o.cta_location
  if (!cta_location && typeof window !== "undefined") {
    cta_location = (sessionStorage.getItem(CTA_KEY) as CtaLocation | null) ?? undefined
    sessionStorage.removeItem(CTA_KEY) // consume so a back-nav can't re-fire it
  }
  track("sign_up", {
    event_id: generateEventId(),
    lead_magnet: o.lead_magnet ?? "7_day_trial",
    method: o.method ?? "google",
    ...(cta_location ? { cta_location } : {}),
    ...(o.lead_id !== undefined ? { lead_id: String(o.lead_id) } : {}),
    email: o.email,
  }, "user")
}

// A confirmed audit lead, pushed as sign_up as well as generate_lead.
//
// Why both: the Google Ads conversion goal is wired to sign_up today, so a lead
// that only pushed generate_lead would not be counted or bid on. method
// ("audit_form" vs "google") is what separates form leads from trial signups in
// GA4. NOTE: once generate_lead is imported into Ads as its own conversion,
// drop this call or the same lead counts twice.
export function trackLeadSignUp(o: {
  lead_id?: number | string
  cta_location?: CtaLocation
  email?: string
}) {
  trackSignUp({
    method: "audit_form",
    lead_magnet: "custom_plan",
    cta_location: o.cta_location,
    email: o.email,
    lead_id: o.lead_id,
  })
}
