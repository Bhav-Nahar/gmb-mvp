'use client'

import { Printer } from 'lucide-react'
import { useBranding } from '@/hooks/useBranding'

/** Print-only masthead: the agency's logo and site, or Pinzo's. */
export function ReportPrintHeader({ title, subtitle }: { title: string; subtitle?: string }) {
  const state = useBranding()
  if (!state) return null
  const { name, logo_url, website_url } = state.branding
  return (
    <div className="print-only mb-5 border-b pb-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-lg font-bold">{title}</div>
          {subtitle && <div className="text-sm">{subtitle}</div>}
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={logo_url} alt={name} style={{ height: 32 }} />
      </div>
      <div className="mt-2 text-xs">
        Prepared by {name} · {website_url.replace(/^https?:\/\//, '')}
      </div>
    </div>
  )
}

export function ExportPdfButton({ className = '' }: { className?: string }) {
  return (
    <button
      onClick={() => window.print()}
      className={`no-print inline-flex h-9 items-center gap-1.5 rounded-md border border-border px-3 text-sm font-semibold hover:bg-muted/40 ${className}`}
    >
      <Printer className="h-4 w-4" /> Export PDF
    </button>
  )
}
