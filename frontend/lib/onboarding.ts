// Card-required onboarding: the frontend mirror of the backend CARD_REQUIRED_ONBOARDING
// flag. When off, the legacy frictionless trial runs and none of the audit-gate UI shows.
export const CARD_REQUIRED_ONBOARDING =
  process.env.NEXT_PUBLIC_CARD_REQUIRED_ONBOARDING === 'true'
