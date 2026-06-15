import React from "react"

/**
 * Read-only panel surfacing the rich GBP fields we now capture from Google so
 * nothing returned by the API is hidden from the user. Each field type gets a
 * human-readable renderer instead of a raw JSON dump.
 */

const has = (v: any) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)

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
  <div className="flex flex-col gap-2 py-3 border-b border-border/30 last:border-0">
    <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground/70">{label}</span>
    <div className="text-sm">{children}</div>
  </div>
)

const DAY_SHORT: Record<string, string> = {
  MONDAY: "Mon", TUESDAY: "Tue", WEDNESDAY: "Wed", THURSDAY: "Thu",
  FRIDAY: "Fri", SATURDAY: "Sat", SUNDAY: "Sun",
}

const fmtTime = (t: any): string => {
  if (!t) return "00:00"
  if (typeof t === "string") return t
  const h = String(t.hours ?? 0).padStart(2, "0")
  const m = String(t.minutes ?? 0).padStart(2, "0")
  return `${h}:${m}`
}

const fmtDate = (d: any): string => (d ? `${d.year}-${String(d.month).padStart(2, "0")}-${String(d.day).padStart(2, "0")}` : "")

const fmtMoney = (price: any): string | null => {
  if (!price) return null
  const cur = price.currencyCode || ""
  const units = price.units
  if (units === undefined || units === null) return cur || null
  const major = price.nanos ? Number(units) + price.nanos / 1e9 : Number(units)
  return `${cur} ${major}`.trim()
}

// ── Renderers ───────────────────────────────────────────────────────────────

function ServiceItems({ items }: { items: any[] }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {items.map((it, i) => {
        const free = it.freeFormServiceItem
        const structured = it.structuredServiceItem
        const title = free?.label?.displayName || structured?.serviceTypeId || "Service"
        const description = free?.label?.description || structured?.description
        const price = fmtMoney(it.price)
        const category = (free?.category || structured?.category || "").replace("categories/gcid:", "")
        return (
          <div key={i} className="rounded-lg border border-border/50 bg-muted/10 p-3 space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <span className="text-sm font-semibold text-foreground">{title}</span>
              {price && <span className="text-xs font-bold text-emerald-500 shrink-0">{price}</span>}
            </div>
            {description && <p className="text-xs text-muted-foreground leading-snug line-clamp-3">{description}</p>}
            {category && (
              <span className="inline-flex text-[10px] font-semibold uppercase tracking-wide text-indigo-300/80 bg-indigo-500/10 border border-indigo-500/20 rounded px-1.5 py-0.5">
                {category.replace(/_/g, " ")}
              </span>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ServiceArea({ area }: { area: any }) {
  const places = area?.places?.placeInfos || []
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
        {area?.businessType && (
          <span><span className="font-semibold text-foreground/70">Type:</span> {String(area.businessType).replace(/_/g, " ")}</span>
        )}
        {area?.regionCode && (
          <span><span className="font-semibold text-foreground/70">Region:</span> {area.regionCode}</span>
        )}
      </div>
      {places.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {places.map((p: any, i: number) => (
            <span key={p.placeId || i} className="inline-flex items-center rounded-md bg-muted/40 text-foreground/80 border border-border/50 px-2 py-0.5 text-xs font-medium">
              {p.placeName || p.placeId}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function MoreHours({ moreHours }: { moreHours: any[] }) {
  return (
    <div className="space-y-2">
      {moreHours.map((mh, i) => (
        <div key={i} className="text-xs">
          <span className="font-semibold text-foreground/80">{String(mh.hoursTypeId || "Hours").replace(/_/g, " ")}: </span>
          <span className="text-muted-foreground">
            {(mh.periods || []).map((p: any, j: number) =>
              `${DAY_SHORT[p.openDay] || p.openDay} ${fmtTime(p.openTime)}–${fmtTime(p.closeTime)}`
            ).join(", ") || "—"}
          </span>
        </div>
      ))}
    </div>
  )
}

function SpecialHours({ special }: { special: any }) {
  const periods = special?.specialHourPeriods || []
  return (
    <div className="space-y-1">
      {periods.map((p: any, i: number) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className="font-mono text-foreground/80">{fmtDate(p.startDate)}</span>
          {p.closed ? (
            <span className="text-red-400 font-semibold">Closed</span>
          ) : (
            <span className="text-indigo-300 font-mono">{fmtTime(p.openTime)}–{fmtTime(p.closeTime)}</span>
          )}
        </div>
      ))}
    </div>
  )
}

// ── Panel ───────────────────────────────────────────────────────────────────

export function GoogleDataPanel({ location }: { location: any }) {
  if (!location) return null

  const phones: any[] = Array.isArray(location.additional_phones) ? location.additional_phones : []
  const labels: any[] = Array.isArray(location.labels) ? location.labels : []
  const open = location.open_info
  const latlng = location.latlng
  const serviceItems: any[] = Array.isArray(location.service_items) ? location.service_items : []
  const serviceArea = location.service_area
  const specialHours = location.special_hours
  const moreHours: any[] = Array.isArray(location.more_hours) ? location.more_hours : []

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
              {open?.openingDate && <span className="text-muted-foreground"> · opened {fmtDate(open.openingDate)}</span>}
            </Row>
          )}
          {has(latlng) && (
            <Row label="Coordinates"><span className="font-mono text-foreground/80">{latlng?.latitude}, {latlng?.longitude}</span></Row>
          )}
          {has(location.store_code) && (
            <Row label="Store code"><span className="font-medium text-foreground">{location.store_code}</span></Row>
          )}
          {has(specialHours) && <Row label="Special hours"><SpecialHours special={specialHours} /></Row>}
          {has(moreHours) && <Row label="More hours"><MoreHours moreHours={moreHours} /></Row>}
          {has(serviceArea) && <Row label="Service area"><ServiceArea area={serviceArea} /></Row>}
          {has(serviceItems) && (
            <Row label={`Service items (${serviceItems.length})`}><ServiceItems items={serviceItems} /></Row>
          )}
        </div>
      )}
    </div>
  )
}
