import React from "react"

/**
 * Read-only panel surfacing the rich GBP fields we now capture from Google so
 * nothing returned by the API is hidden from the user. Editing parity for these
 * is added incrementally; this guarantees visibility today.
 */

const Chips = ({ items }: { items: any[] }) => (
  <div className="flex flex-wrap gap-1.5">
    {items.map((v, i) => (
      <span key={i} className="inline-flex items-center rounded-md bg-muted/40 text-foreground/80 border border-border/50 px-2 py-0.5 text-xs font-medium">
        {typeof v === "object" && v !== null ? (v.displayName || JSON.stringify(v)) : String(v)}
      </span>
    ))}
  </div>
)

const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div className="flex flex-col gap-1.5 py-3 border-b border-border/30 last:border-0">
    <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70">{label}</span>
    <div className="text-sm">{children}</div>
  </div>
)

const Json = ({ value }: { value: any }) => (
  <pre className="text-xs p-2 bg-muted/20 border border-border/30 rounded-md overflow-x-auto font-mono text-muted-foreground max-h-48">
    {JSON.stringify(value, null, 2)}
  </pre>
)

const has = (v: any) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)

export function GoogleDataPanel({ location }: { location: any }) {
  if (!location) return null

  const phones: any[] = Array.isArray(location.additional_phones) ? location.additional_phones : []
  const labels: any[] = Array.isArray(location.labels) ? location.labels : []
  const open = location.open_info
  const latlng = location.latlng
  const serviceItems = location.service_items
  const serviceArea = location.service_area
  const specialHours = location.special_hours
  const moreHours = location.more_hours

  const anything = has(phones) || has(labels) || has(open) || has(latlng) ||
    has(serviceItems) || has(serviceArea) || has(specialHours) || has(moreHours) ||
    has(location.store_code)

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-medium text-foreground border-b border-border/50 pb-2">
        Google Profile Data <span className="text-xs font-normal text-muted-foreground">(read-only, synced from Google)</span>
      </h3>

      {!anything ? (
        <p className="text-sm text-muted-foreground italic">
          No additional Google data captured yet. Use “Force Sync” to refresh from Google.
        </p>
      ) : (
        <div className="rounded-xl border border-border/40 bg-muted/5 px-5 shadow-sm">
          {has(phones) && <Row label="Additional phones"><Chips items={phones} /></Row>}
          {has(labels) && <Row label="Labels"><Chips items={labels} /></Row>}
          {has(open) && (
            <Row label="Open status">
              <span className="font-medium text-foreground">{open?.status || "—"}</span>
              {open?.openingDate && (
                <span className="text-muted-foreground"> · opened {open.openingDate.year}-{open.openingDate.month}-{open.openingDate.day}</span>
              )}
            </Row>
          )}
          {has(latlng) && (
            <Row label="Coordinates">
              <span className="font-mono text-foreground/80">{latlng?.latitude}, {latlng?.longitude}</span>
            </Row>
          )}
          {has(location.store_code) && (
            <Row label="Store code"><span className="font-medium text-foreground">{location.store_code}</span></Row>
          )}
          {has(specialHours) && <Row label="Special hours"><Json value={specialHours} /></Row>}
          {has(moreHours) && <Row label="More hours"><Json value={moreHours} /></Row>}
          {has(serviceArea) && <Row label="Service area"><Json value={serviceArea} /></Row>}
          {has(serviceItems) && <Row label="Service items"><Json value={serviceItems} /></Row>}
        </div>
      )}
    </div>
  )
}
