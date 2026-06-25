'use client'

import { useEffect, useState } from 'react'
import { actAsOrg } from '@/lib/api'

// Shows a sticky bar whenever a super-admin is acting inside another org, so the
// borrowed workspace can never be mistaken for your own. Exit clears + reloads.
export default function ImpersonationBanner() {
  const [orgId, setOrgId] = useState<string | null>(null)

  useEffect(() => { setOrgId(sessionStorage.getItem('actingOrg')) }, [])

  if (!orgId) return null

  const exit = () => {
    actAsOrg(null)
    window.location.href = '/admin'
  }

  return (
    <div className="sticky top-0 z-50 flex items-center justify-center gap-3 bg-amber-500 px-4 py-1.5 text-xs font-semibold text-black">
      <span>Viewing workspace #{orgId} as super-admin</span>
      <button onClick={exit} className="rounded bg-black/15 px-2 py-0.5 hover:bg-black/25">Exit</button>
    </div>
  )
}
