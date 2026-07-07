import { redirect } from 'next/navigation'
import { getPseoPage, pseoPath, PSEO_SEGMENT } from '@/lib/pseo'

// Legacy bare URL (/gbp-management/{slug}, no locale prefix). Real pages live at
// /{locale}/gbp-management/{slug} (see app/[slug]/gbp-management). This stub only
// preserves the old behavior for stray direct hits: leaf slugs redirect to their
// canonical locale URL, anything else falls back to the global market index.
// Near-zero traffic (these URLs were never emitted anywhere), so dynamic is fine.
export const dynamic = 'force-dynamic'

export default async function BareGbpManagementRedirect({ params }: { params: { slug: string } }) {
  const page = await getPseoPage(params.slug)
  if (page) redirect(pseoPath(page.locale, page.slug))
  redirect(`/${PSEO_SEGMENT}`)
}
