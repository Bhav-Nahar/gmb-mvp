import { NextRequest, NextResponse } from 'next/server'

// pinzo.io/r/<token> — the destination of the "Leave a review" button in the
// WhatsApp template.
//
// This path is baked into the approved Meta template and CANNOT change without
// a new template and a new approval, so treat the URL shape as frozen.
//
// The redirect is 302, never 301: a permanent redirect gets cached by the
// browser and by intermediaries, after which the token stops reaching us — no
// click recorded, and no way to repoint or expire a link that is already out
// in the wild.

const BACKEND = process.env.BACKEND_API_URL ?? 'http://backend:8000'

export const dynamic = 'force-dynamic'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ token: string }> },
) {
  const { token } = await params

  try {
    const res = await fetch(
      `${BACKEND}/api/v1/public/r/${encodeURIComponent(token)}`,
      { cache: 'no-store' },
    )

    if (res.ok) {
      const { url } = (await res.json()) as { url: string }
      if (url) return NextResponse.redirect(url, 302)
    }
  } catch (err) {
    // A backend blip must not show the customer a stack trace. They came here
    // from a message asking them for a favour — the worst outcome is a scary
    // error page, so fall through to the homepage instead.
    console.error('[review-redirect] resolve failed', err)
  }

  return NextResponse.redirect(new URL('/', process.env.FRONTEND_URL ?? 'https://pinzo.io'), 302)
}
