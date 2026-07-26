import { redirect } from 'next/navigation'

// The city pillar is an lpseo_pages row, so it gets the full Local SEO admin
// (Search Console, editor, publish, robots toggle) rather than a second, thinner
// screen. Only the CSV import differs, and that switches on the tab's tier.
export default function AdminCityseoRedirect() {
  redirect('/admin/lpseo?type=city_pillar')
}
