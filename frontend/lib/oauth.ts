import { api } from "./api"
import { rememberCtaLocation, type CtaLocation } from "./analytics"

// Single entry point for starting Google OAuth. Remembers where the user came
// from (for sign_up, fired later on the success callback), fetches the
// authorize URL, and redirects. Throws on failure; caller owns loading/error UI.
export async function beginGoogleLogin(cta: CtaLocation): Promise<void> {
  rememberCtaLocation(cta)
  const res: any = await api.get("/auth/google/login")
  if (!res?.url) throw new Error("Failed to retrieve authorization URL")
  window.location.href = res.url
}
