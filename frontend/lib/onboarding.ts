// Card-required onboarding: the frontend mirror of the backend CARD_REQUIRED_ONBOARDING
// flag. When off, the legacy frictionless trial runs and none of the audit-gate UI shows.
export const CARD_REQUIRED_ONBOARDING =
  process.env.NEXT_PUBLIC_CARD_REQUIRED_ONBOARDING === 'true'

type BillingLike = { subscription_status?: string | null; trial_ends_at?: string | null } | null | undefined

/**
 * Pre-payment onboarding: on a trial whose clock hasn't started (trial_ends_at null).
 * Only meaningful in the card-required flow — the legacy flow starts the clock on sync,
 * so this is always false there.
 */
export function isOnboardingState(billing: BillingLike): boolean {
  return (
    CARD_REQUIRED_ONBOARDING &&
    billing?.subscription_status === 'trial' &&
    !billing?.trial_ends_at
  )
}
