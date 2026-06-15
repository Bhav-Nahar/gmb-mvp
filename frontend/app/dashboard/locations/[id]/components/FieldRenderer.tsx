import { useState, useEffect } from "react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Loader2, AlertCircle, Globe } from "lucide-react"
import { api } from "@/lib/api"

interface FieldRendererProps {
  fieldConfig: {
    name: string
    label: string
    is_staff_editable: boolean
    is_admin_editable: boolean
    is_critical: boolean
    is_read_only: boolean
    warning_title?: string
    warning_body?: string
    field_type?: string
    transformer?: string
    ui_component?: string
    supports_bulk_edit?: boolean
  }
  value: any
  editState?: {
    status: string
    new_value: any
  }
  userRole: string
  onSave: (fieldName: string, newValue: any, acknowledged: boolean) => void
  onCriticalEdit: (fieldName: string, newValue: any, config: any) => void
  onEditingChange?: (isEditing: boolean) => void
}

interface DayHours {
  isOpen: boolean
  openTime: string
  closeTime: string
}

const DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
const DAY_LABELS: Record<string, string> = {
  MONDAY: "Monday",
  TUESDAY: "Tuesday",
  WEDNESDAY: "Wednesday",
  THURSDAY: "Thursday",
  FRIDAY: "Friday",
  SATURDAY: "Saturday",
  SUNDAY: "Sunday"
}

const formatTimeObj = (time: any): string => {
  if (!time) return "00:00"
  if (typeof time === "string") return time
  if (typeof time === "object") {
    if ('hours' in time || 'minutes' in time) {
      const hours = String(time.hours !== undefined ? time.hours : 0).padStart(2, "0")
      const minutes = String(time.minutes !== undefined ? time.minutes : 0).padStart(2, "0")
      return `${hours}:${minutes}`
    }
    return JSON.stringify(time)
  }
  return "00:00"
}

const parseHours = (periods: any[]): Record<string, DayHours> => {
  const initial: Record<string, DayHours> = {}
  DAYS.forEach(day => {
    initial[day] = { isOpen: false, openTime: "09:00", closeTime: "17:00" }
  })
  
  if (Array.isArray(periods)) {
    periods.forEach(p => {
      const day = p.openDay?.toUpperCase()
      if (DAYS.includes(day)) {
        initial[day] = {
          isOpen: true,
          openTime: formatTimeObj(p.openTime) || "09:00",
          closeTime: formatTimeObj(p.closeTime) || "17:00"
        }
      }
    })
  }
  return initial
}

const serializeHours = (hoursState: Record<string, DayHours>) => {
  const periods: any[] = []
  DAYS.forEach(day => {
    const config = hoursState[day]
    if (config.isOpen) {
      periods.push({
        openDay: day,
        openTime: config.openTime,
        closeDay: day,
        closeTime: config.closeTime
      })
    }
  })
  return periods
}

const formatAddress = (addressVal: any): string => {
  if (!addressVal) return '';
  if (typeof addressVal === 'object') {
    const lines = addressVal.addressLines || [];
    const locality = addressVal.locality || '';
    const region = addressVal.administrativeArea || '';
    const postalCode = addressVal.postalCode || '';
    const country = addressVal.regionCode || '';
    return [...lines, locality, region, postalCode, country].filter(Boolean).join(', ');
  }
  if (typeof addressVal === 'string') {
    if (addressVal.startsWith('{')) {
      try {
        const parsed = JSON.parse(addressVal);
        return formatAddress(parsed);
      } catch (e) {
        return addressVal;
      }
    }
    return addressVal;
  }
  return String(addressVal);
}

export function FieldRenderer({
  fieldConfig,
  value,
  editState,
  userRole,
  onSave,
  onCriticalEdit,
  onEditingChange
}: FieldRendererProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [localValue, setLocalValue] = useState(typeof value === "object" && value !== null ? JSON.stringify(value, null, 2) : (value || ""))

  // BUG-007 fix: Sync localValue when value prop changes externally (async data load)
  // Only update when NOT actively editing to avoid overwriting the user's in-progress input.
  useEffect(() => {
    if (!isEditing) {
      setLocalValue(
        typeof value === "object" && value !== null
          ? JSON.stringify(value, null, 2)
          : (value || "")
      )
    }
  }, [value, isEditing])

  const isAdminOrOwner = userRole === "Admin" || userRole === "admin" || userRole === "Owner" || userRole === "owner"

  const canEdit = 
    !fieldConfig.is_read_only &&
    (isAdminOrOwner ? fieldConfig.is_admin_editable : fieldConfig.is_staff_editable)

  const isPending = editState?.status === "Draft" || editState?.status === "Pending"
  const isPublishing = editState?.status === "Approved" || editState?.status === "Publishing"
  
  const displayValue = editState ? editState.new_value : value

  const renderValue = (val: any) => {
    if (val === null || val === undefined || val === "") return <span className="text-muted-foreground italic">Not set</span>
    
    if (fieldConfig.name === "address") {
      const formatted = formatAddress(val);
      if (!formatted) return <span className="text-muted-foreground italic">Not set</span>;
      return <span className="text-foreground font-medium leading-relaxed">{formatted}</span>;
    }

    if (fieldConfig.name === "additional_categories") {
      const list = Array.isArray(val) ? val : []
      if (list.length === 0) return <span className="text-muted-foreground italic">None</span>
      return (
        <div className="flex flex-wrap gap-1.5">
          {list.map((c: any, i: number) => {
            const label = typeof c === "object" && c !== null ? c.displayName : c
            return (
              <span key={(typeof c === "object" && c?.name) || label || i} className="inline-flex items-center rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 px-2 py-0.5 text-xs font-semibold">
                {label}
              </span>
            )
          })}
        </div>
      )
    }

    if (fieldConfig.name === "additional_phones") {
      const list = Array.isArray(val) ? val.filter(Boolean) : []
      if (list.length === 0) return <span className="text-muted-foreground italic">None</span>
      return (
        <div className="flex flex-wrap gap-1.5">
          {list.map((p: any, i: number) => (
            <span key={i} className="inline-flex items-center rounded-md bg-muted/40 text-foreground/80 border border-border/50 px-2 py-0.5 text-xs font-medium">{String(p)}</span>
          ))}
        </div>
      )
    }

    if (fieldConfig.name === "special_hours") {
      const periods = (val && val.specialHourPeriods) || []
      if (periods.length === 0) return <span className="text-muted-foreground italic">None</span>
      return (
        <div className="space-y-1">
          {periods.map((p: any, i: number) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              <span className="font-mono text-foreground/80">{fmtGDate(p.startDate)}</span>
              {p.closed ? <span className="text-red-400 font-semibold">Closed</span>
                : <span className="text-indigo-300 font-mono">{fmtGTime(p.openTime)}–{fmtGTime(p.closeTime)}</span>}
            </div>
          ))}
        </div>
      )
    }

    if (fieldConfig.name === "service_items") {
      const items = Array.isArray(val) ? val : []
      if (items.length === 0) return <span className="text-muted-foreground italic">None</span>
      return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {items.map((it: any, i: number) => {
            const free = it.freeFormServiceItem
            const title = free?.label?.displayName || it.structuredServiceItem?.serviceTypeId || "Service"
            const desc = free?.label?.description
            const price = it.price?.units != null ? `${it.price.currencyCode || ''} ${it.price.units}`.trim() : null
            return (
              <div key={i} className="rounded-lg border border-border/50 bg-muted/10 p-2.5 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs font-semibold text-foreground">{title}</span>
                  {price && <span className="text-[11px] font-bold text-emerald-500 shrink-0">{price}</span>}
                </div>
                {desc && <p className="text-[11px] text-muted-foreground leading-snug line-clamp-2">{desc}</p>}
              </div>
            )
          })}
        </div>
      )
    }

    if (fieldConfig.name === "open_info") {
      const status = (val && val.status) || (typeof val === "string" ? val : null)
      if (!status) return <span className="text-muted-foreground italic">Not set</span>
      return (
        <span className="text-foreground font-medium">
          {String(status).replace(/_/g, " ")}
          {val?.openingDate && <span className="text-muted-foreground"> · opened {fmtGDate(val.openingDate)}</span>}
        </span>
      )
    }

    if (fieldConfig.ui_component === "business_hours_editor" || fieldConfig.name === "business_hours") {
      const hoursMap = parseHours(val)
      return (
        <div className="space-y-1.5 pt-1 text-xs max-w-md bg-muted/10 p-3 rounded-lg border border-border/40">
          {DAYS.map(day => {
            const config = hoursMap[day]
            return (
              <div key={day} className="flex justify-between items-center text-muted-foreground font-medium border-b border-border/10 pb-1 last:border-0 last:pb-0">
                <span className="text-foreground/80 font-semibold">{DAY_LABELS[day]}</span>
                {config.isOpen ? (
                  <span className="text-indigo-400 font-bold font-mono">{config.openTime} - {config.closeTime}</span>
                ) : (
                  <span className="text-muted-foreground/40 italic">Closed</span>
                )}
              </div>
            )
          })}
        </div>
      )
    }

    if (typeof val === "object") {
      return (
        <pre className="text-xs p-2 bg-muted/20 border border-border/30 rounded-md overflow-x-auto font-mono text-muted-foreground">
          {JSON.stringify(val, null, 2)}
        </pre>
      )
    }
    return <span className="text-foreground font-medium leading-relaxed">{String(val)}</span>
  }

  const handleSave = () => {
    if (fieldConfig.is_critical) {
      onCriticalEdit(fieldConfig.name, localValue, fieldConfig)
    } else {
      onSave(fieldConfig.name, localValue, false)
    }
    setIsEditing(false)
    if (onEditingChange) onEditingChange(false)
  }

  const renderEditor = () => {
    if (fieldConfig.name === "address") {
      return (
        <AddressEditor 
          initialValue={value} 
          onSave={(serialized) => {
            const stringified = JSON.stringify(serialized);
            if (fieldConfig.is_critical) {
              onCriticalEdit(fieldConfig.name, stringified, fieldConfig)
            } else {
              onSave(fieldConfig.name, stringified, false)
            }
            setIsEditing(false)
            if (onEditingChange) onEditingChange(false)
          }}
          onCancel={() => {
            setIsEditing(false)
            if (onEditingChange) onEditingChange(false)
          }}
        />
      )
    }

    const NAME_TO_UI: Record<string, string> = {
      business_hours: "business_hours_editor",
      primary_category: "category_autocomplete",
      additional_categories: "multi_category_autocomplete",
      additional_phones: "phones_editor",
      special_hours: "special_hours_editor",
      service_items: "service_items_editor",
      open_info: "open_status_editor",
    }
    const uiComponent = fieldConfig.ui_component || NAME_TO_UI[fieldConfig.name] || (typeof value === "object" || fieldConfig.name.includes("description") ? "textarea" : "input")

    const selfManaged = (serialized: any) => {
      onSave(fieldConfig.name, serialized, false)
      setIsEditing(false)
      if (onEditingChange) onEditingChange(false)
    }
    const cancelEdit = () => {
      setIsEditing(false)
      if (onEditingChange) onEditingChange(false)
    }

    switch (uiComponent) {
      case "phones_editor":
        return <PhonesEditor initialValue={value} onSave={selfManaged} onCancel={cancelEdit} />
      case "special_hours_editor":
        return <SpecialHoursEditor initialValue={value} onSave={selfManaged} onCancel={cancelEdit} />
      case "service_items_editor":
        return <ServiceItemsEditor initialValue={value} onSave={selfManaged} onCancel={cancelEdit} />
      case "open_status_editor":
        return <OpenStatusEditor initialValue={value} onSave={selfManaged} onCancel={cancelEdit} />
      case "multi_category_autocomplete":
        return (
          <MultiCategoryEditor
            initialValue={value}
            onSave={(serialized) => {
              if (fieldConfig.is_critical) {
                onCriticalEdit(fieldConfig.name, serialized, fieldConfig)
              } else {
                onSave(fieldConfig.name, serialized, false)
              }
              setIsEditing(false)
              if (onEditingChange) onEditingChange(false)
            }}
            onCancel={() => {
              setIsEditing(false)
              if (onEditingChange) onEditingChange(false)
            }}
          />
        )
      case "business_hours_editor":
        return (
          <BusinessHoursEditor 
            initialValue={value} 
            onSave={(serialized) => {
              onSave(fieldConfig.name, serialized, false)
              setIsEditing(false)
              if (onEditingChange) onEditingChange(false)
            }}
            onCancel={() => {
              setIsEditing(false)
              if (onEditingChange) onEditingChange(false)
            }}
          />
        )
      case "category_autocomplete":
        return (
          <CategoryAutocompleteEditor 
            value={localValue}
            onChange={setLocalValue}
          />
        )
      case "textarea":
        return (
          <Textarea 
            value={localValue} 
            onChange={(e) => setLocalValue(e.target.value)}
            className="font-mono text-xs min-h-[120px] bg-background/50 border-border focus:border-indigo-500 focus:ring-indigo-500"
          />
        )
      case "input":
      default:
        return (
          <Input 
            value={localValue} 
            onChange={(e) => setLocalValue(e.target.value)}
            className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500"
          />
        )
    }
  }

  return (
    <div className="border border-border/40 bg-muted/5 rounded-xl p-5 space-y-4 shadow-lg hover:shadow-indigo-500/5 hover:border-border/80 transition-all">
      <div className="flex justify-between items-start">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h4 className="text-sm font-bold text-foreground tracking-wide">{fieldConfig.label}</h4>
            {fieldConfig.is_critical && (
              <Badge variant="destructive" className="h-5 px-1.5 text-[9px] uppercase tracking-wider font-extrabold bg-red-500/10 text-red-400 border border-red-500/25">
                Critical
              </Badge>
            )}
            {fieldConfig.is_read_only && (
              <Badge variant="secondary" className="h-5 px-1.5 text-[9px] uppercase tracking-wider font-extrabold bg-muted text-muted-foreground border border-border/30">
                Read Only
              </Badge>
            )}
          </div>
          <div className="text-[10px] text-muted-foreground/60 font-mono">
            {fieldConfig.name}
          </div>
        </div>
        
        {!isEditing && canEdit && !isPending && !isPublishing && (
          <Button variant="ghost" size="sm" className="h-7 text-xs font-bold border border-border/40 hover:bg-indigo-500/10 hover:text-indigo-400 cursor-pointer" onClick={() => {
            setLocalValue(typeof value === "object" && value !== null ? JSON.stringify(value, null, 2) : (value || ""))
            setIsEditing(true)
            if (onEditingChange) onEditingChange(true)
          }}>
            Edit
          </Button>
        )}
      </div>

      <div className="mt-2">
        {isEditing ? (
          <div className="space-y-2">
            {renderEditor()}
            {fieldConfig.ui_component !== "business_hours_editor" && !["business_hours", "address", "additional_categories", "additional_phones", "special_hours", "service_items", "open_info"].includes(fieldConfig.name) && (
              <div className="flex justify-end gap-2 mt-2">
                <Button variant="ghost" size="sm" className="text-xs" onClick={() => {
                  setIsEditing(false)
                  if (onEditingChange) onEditingChange(false)
                }}>Cancel</Button>
                <Button size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={handleSave}>Save</Button>
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="text-sm">
              {renderValue(displayValue)}
            </div>

            {isPending && (
              <div className="flex items-center gap-2 text-[11px] font-bold text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-2 rounded-lg">
                <AlertCircle className="w-4 h-4 shrink-0 text-amber-500" />
                <span>Pending Approval (Needs Workspace Review)</span>
              </div>
            )}
            {isPublishing && (
              <div className="flex items-center gap-2 text-[11px] font-bold text-blue-400 bg-blue-500/10 border border-blue-500/20 px-3 py-2 rounded-lg">
                <Loader2 className="w-4 h-4 shrink-0 animate-spin text-blue-500" />
                <span>Publishing to Google Business Profile...</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function BusinessHoursEditor({
  initialValue,
  onSave,
  onCancel
}: {
  initialValue: any
  onSave: (val: any) => void
  onCancel: () => void
}) {
  const [hoursState, setHoursState] = useState<Record<string, DayHours>>(() => parseHours(initialValue))

  const handleToggle = (day: string) => {
    setHoursState(prev => ({
      ...prev,
      [day]: { ...prev[day], isOpen: !prev[day].isOpen }
    }))
  }

  const handleTimeChange = (day: string, field: "openTime" | "closeTime", val: string) => {
    setHoursState(prev => ({
      ...prev,
      [day]: { ...prev[day], [field]: val }
    }))
  }

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const serialized = serializeHours(hoursState)
    onSave(serialized)
  }

  return (
    <form onSubmit={handleFormSubmit} className="space-y-4 pt-1">
      <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1">
        {DAYS.map(day => {
          const config = hoursState[day]
          return (
            <div key={day} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-2 rounded-lg bg-background/50 border border-border/30 hover:border-border/60 transition-colors">
              <div className="flex items-center gap-3">
                {/* BUG-008 fix: Checkbox now represents "Open" state (checked = open, unchecked = closed).
                    Previously checked meant "Closed" — confusing inverse UX. */}
                <input 
                  type="checkbox"
                  id={`open-${day}`}
                  checked={config.isOpen}
                  onChange={() => handleToggle(day)}
                  className="h-4 w-4 rounded border-border/80 bg-background text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                />
                <label htmlFor={`open-${day}`} className="text-xs font-bold text-foreground/90 cursor-pointer select-none min-w-[70px]">
                  {DAY_LABELS[day]}
                </label>
                <span className={`text-[10px] font-extrabold uppercase px-1.5 py-0.5 rounded ${config.isOpen ? 'bg-indigo-500/10 text-indigo-400' : 'bg-muted text-muted-foreground'}`}>
                  {config.isOpen ? "Open" : "Closed"}
                </span>
              </div>
              
              {config.isOpen && (
                <div className="flex items-center gap-3 pl-7 sm:pl-0">
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted-foreground font-semibold">Opens:</span>
                    <input 
                      type="text"
                      placeholder="09:00"
                      value={config.openTime}
                      onChange={(e) => handleTimeChange(day, "openTime", e.target.value)}
                      className="w-14 rounded border border-border bg-background/50 px-2 py-0.5 text-center text-xs font-semibold font-mono text-foreground focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-[10px] text-muted-foreground font-semibold">Closes:</span>
                    <input 
                      type="text"
                      placeholder="17:00"
                      value={config.closeTime}
                      onChange={(e) => handleTimeChange(day, "closeTime", e.target.value)}
                      className="w-14 rounded border border-border bg-background/50 px-2 py-0.5 text-center text-xs font-semibold font-mono text-foreground focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
      <div className="flex justify-end gap-2 pt-3 border-t border-border/30">
        <Button type="button" variant="ghost" size="sm" className="text-xs" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-semibold">
          Save Hours
        </Button>
      </div>
    </form>
  )
}

function CategoryAutocompleteEditor({
  value,
  onChange
}: {
  value: any
  onChange: (val: any) => void
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState(
    typeof value === "object" && value !== null
      ? (value as any).displayName
      : (value || "")
  )
  const [categories, setCategories] = useState<{ name: string; displayName: string }[]>([])
  const [isLoading, setIsLoading] = useState(false)

  useEffect(() => {
    if (!search || search.length < 2) {
      setCategories([])
      return
    }
    const delayDebounceFn = setTimeout(async () => {
      setIsLoading(true)
      try {
        const res = await api.get<any[]>(`/locations/categories/search?query=${encodeURIComponent(search)}`)
        setCategories(res || [])
      } catch (e) {
        console.error("Failed to fetch GMB categories", e)
      } finally {
        setIsLoading(false)
      }
    }, 300)

    return () => clearTimeout(delayDebounceFn)
  }, [search])

  const handleSelect = (category: { name: string; displayName: string }) => {
    onChange(category)
    setSearch(category.displayName)
    setIsOpen(false)
  }

  // BUG-004 fix: Use POPULAR_CATEGORIES as a fallback when the user hasn't typed enough
  // to trigger a live search, so the dropdown is never empty on first open.
  const displayCategories = search.length >= 2
    ? categories
    : POPULAR_CATEGORIES.map(n => ({ name: n, displayName: n }))

  return (
    <div className="relative">
      <div className="relative">
        <Input 
          value={search} 
          onChange={(e) => {
            setSearch(e.target.value)
            setIsOpen(true)
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="Search live GMB categories..."
          className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500 pr-8"
        />
        {isLoading && (
          <div className="absolute right-2.5 top-2.5">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        )}
      </div>
      {isOpen && displayCategories.length > 0 && (
        <div className="absolute z-50 w-full mt-1 max-h-[200px] overflow-y-auto rounded-lg border border-border bg-card shadow-2xl p-1 space-y-0.5">
          {displayCategories.map(cat => (
            <div 
              key={cat.name} 
              // BUG-005 fix: Use onMouseDown + preventDefault so the item click
              // fires before the backdrop overlay's onClick closes the dropdown.
              onMouseDown={(e) => { e.preventDefault(); handleSelect(cat) }}
              className="px-3 py-2 text-xs text-foreground hover:bg-indigo-600 hover:text-white rounded-md cursor-pointer transition-colors"
            >
              {cat.displayName}
            </div>
          ))}
        </div>
      )}
      {isOpen && (
        <div 
          className="fixed inset-0 z-40" 
          onClick={() => setIsOpen(false)}
        />
      )}
    </div>
  )
}

function MultiCategoryEditor({
  initialValue,
  onSave,
  onCancel
}: {
  initialValue: any
  onSave: (val: { name: string; displayName: string }[]) => void
  onCancel: () => void
}) {
  const normalize = (val: any): { name: string; displayName: string }[] => {
    if (!Array.isArray(val)) return []
    return val
      .map((c) => (typeof c === "object" && c !== null
        ? { name: c.name, displayName: c.displayName }
        : { name: c, displayName: c }))
      .filter((c) => c.name)
  }

  const [selected, setSelected] = useState<{ name: string; displayName: string }[]>(() => normalize(initialValue))
  const [search, setSearch] = useState("")
  const [isOpen, setIsOpen] = useState(false)
  const [categories, setCategories] = useState<{ name: string; displayName: string }[]>([])
  const [isLoading, setIsLoading] = useState(false)

  // Google allows up to 9 additional categories per location.
  const MAX_ADDITIONAL = 9
  const atLimit = selected.length >= MAX_ADDITIONAL

  useEffect(() => {
    if (!search || search.length < 2) {
      setCategories([])
      return
    }
    const t = setTimeout(async () => {
      setIsLoading(true)
      try {
        const res = await api.get<any[]>(`/locations/categories/search?query=${encodeURIComponent(search)}`)
        setCategories(res || [])
      } catch (e) {
        console.error("Failed to fetch GMB categories", e)
      } finally {
        setIsLoading(false)
      }
    }, 300)
    return () => clearTimeout(t)
  }, [search])

  const addCategory = (cat: { name: string; displayName: string }) => {
    if (atLimit) return
    if (selected.some((c) => c.name === cat.name)) return
    setSelected((prev) => [...prev, cat])
    setSearch("")
    setIsOpen(false)
  }

  const removeCategory = (name: string) => {
    setSelected((prev) => prev.filter((c) => c.name !== name))
  }

  const displayCategories = (search.length >= 2
    ? categories
    : POPULAR_CATEGORIES.map((n) => ({ name: n, displayName: n }))
  ).filter((cat) => !selected.some((s) => s.name === cat.name))

  return (
    <div className="space-y-3">
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selected.map((c) => (
            <span key={c.name} className="inline-flex items-center gap-1 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 px-2 py-0.5 text-xs font-semibold">
              {c.displayName}
              <button type="button" onClick={() => removeCategory(c.name)} className="text-indigo-300/60 hover:text-indigo-200">
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      <div className="relative">
        <Input
          value={search}
          disabled={atLimit}
          onChange={(e) => { setSearch(e.target.value); setIsOpen(true) }}
          onFocus={() => setIsOpen(true)}
          placeholder={atLimit ? `Limit of ${MAX_ADDITIONAL} reached` : "Add a category..."}
          className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500 pr-8"
        />
        {isLoading && (
          <div className="absolute right-2.5 top-2.5">
            <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
          </div>
        )}
        {isOpen && !atLimit && displayCategories.length > 0 && (
          <div className="absolute z-50 w-full mt-1 max-h-[200px] overflow-y-auto rounded-lg border border-border bg-card shadow-2xl p-1 space-y-0.5">
            {displayCategories.map((cat) => (
              <div
                key={cat.name}
                onMouseDown={(e) => { e.preventDefault(); addCategory(cat) }}
                className="px-3 py-2 text-xs text-foreground hover:bg-indigo-600 hover:text-white rounded-md cursor-pointer transition-colors"
              >
                {cat.displayName}
              </div>
            ))}
          </div>
        )}
        {isOpen && (
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
        )}
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onCancel}>Cancel</Button>
        <Button size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={() => onSave(selected)}>Save</Button>
      </div>
    </div>
  )
}

const POPULAR_CATEGORIES = [
  "Jewellery Store",
  "Jeweler",
  "Home Help",
  "Coffee Shop",
  "Cafe",
  "Restaurant",
  "Bakery",
  "Clothing Store",
  "Hair Salon",
  "Beauty Salon",
  "Nail Salon",
  "Gym",
  "Dental Clinic",
  "Dentist",
  "Medical Clinic",
  "Doctor",
  "Pharmacy",
  "Real Estate Agency",
  "Real Estate Agent",
  "Legal Services",
  "Lawyer",
  "Marketing Agency",
  "Software Company",
  "Grocery Store",
  "Supermarket",
  "Convenience Store",
  "Hotel",
  "Auto Repair Shop",
  "Car Dealer",
  "Gas Station",
  "Florist",
  "Bookstore",
  "School",
  "University",
  "Veterinary Clinic",
  "Plumber",
  "Electrician",
  "Contractor",
  "Accounting Firm",
  "Accountant",
  "Cleaning Service",
  "Spa",
  "Photography Studio",
  "Photographer",
  "Travel Agency",
  "Art Gallery",
  "Museum",
  "Event Venue",
  "Consulting Firm",
  "Financial Planner",
  "Insurance Agency",
  "IT Support",
  "Bar",
  "Brewery",
  "Boutique",
  "Furniture Store",
  "Electronics Store",
  "Pet Groomer",
  "Dry Cleaner",
  "Locksmith",
  "Tattoo Shop",
  "Hardware Store",
  "Physiotherapist",
  "Massage Therapist",
  "Optician",
  "Architect",
  "Interior Designer",
  "Painter",
  "Roofing Contractor",
  "Landscaper",
  "Gardener"
]

interface AddressFields {
  regionCode: string
  addressLines: string[]
  locality: string
  postalCode: string
  administrativeArea: string
}

function AddressEditor({
  initialValue,
  onSave,
  onCancel
}: {
  initialValue: any
  onSave: (val: any) => void
  onCancel: () => void
}) {
  const parseInitial = (val: any): AddressFields => {
    const defaultVal: AddressFields = {
      regionCode: "IN",
      addressLines: [""],
      locality: "",
      postalCode: "",
      administrativeArea: ""
    }
    if (!val) return defaultVal;
    if (typeof val === "object") {
      return {
        regionCode: val.regionCode || "IN",
        addressLines: val.addressLines || [""],
        locality: val.locality || "",
        postalCode: val.postalCode || "",
        administrativeArea: val.administrativeArea || ""
      }
    }
    if (typeof val === "string") {
      if (val.startsWith("{")) {
        try {
          const parsed = JSON.parse(val);
          return parseInitial(parsed);
        } catch (e) {
          // Fall back to splitting
        }
      }
      // Fallback for flat strings: try to parse or put in addressLines
      return {
        ...defaultVal,
        addressLines: [val]
      }
    }
    return defaultVal;
  }

  const [form, setForm] = useState<AddressFields>(() => parseInitial(initialValue))
  const [streetText, setStreetText] = useState(() => (form.addressLines || []).join("\n"))

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // Split streetText by newline and filter out empty lines
    const lines = streetText.split("\n").map(l => l.trim()).filter(Boolean)
    const serialized = {
      ...form,
      addressLines: lines.length > 0 ? lines : [""]
    }
    onSave(serialized)
  }

  return (
    <form onSubmit={handleFormSubmit} className="space-y-4 pt-1 text-xs">
      <div className="space-y-3 bg-background/30 p-4 rounded-xl border border-border/40">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-muted-foreground/60 uppercase">Country/Region</label>
            <Input 
              value={form.regionCode} 
              onChange={(e) => setForm(prev => ({ ...prev, regionCode: e.target.value }))}
              placeholder="e.g. IN"
              className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-muted-foreground/60 uppercase">Pincode / Postal Code</label>
            <Input 
              value={form.postalCode} 
              onChange={(e) => setForm(prev => ({ ...prev, postalCode: e.target.value }))}
              placeholder="e.g. 411005"
              className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500"
              required
            />
          </div>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] font-bold text-muted-foreground/60 uppercase">Street Address</label>
          <Textarea 
            value={streetText} 
            onChange={(e) => setStreetText(e.target.value)}
            placeholder="Line 1&#10;Line 2 (Optional)"
            className="bg-background/50 border-border text-sm min-h-[80px] focus:border-indigo-500 focus:ring-indigo-500"
            required
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-muted-foreground/60 uppercase">Town/City</label>
            <Input 
              value={form.locality} 
              onChange={(e) => setForm(prev => ({ ...prev, locality: e.target.value }))}
              placeholder="e.g. Pune"
              className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500"
              required
            />
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-muted-foreground/60 uppercase">State</label>
            <Input 
              value={form.administrativeArea} 
              onChange={(e) => setForm(prev => ({ ...prev, administrativeArea: e.target.value }))}
              placeholder="e.g. Maharashtra"
              className="bg-background/50 border-border text-sm focus:border-indigo-500 focus:ring-indigo-500"
              required
            />
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2 pt-3 border-t border-border/30">
        <Button type="button" variant="ghost" size="sm" className="text-xs" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white font-semibold">
          Save Address
        </Button>
      </div>
    </form>
  )
}

// ── Helpers for GBP date/time shapes ────────────────────────────────────────
function fmtGTime(t: any): string {
  if (!t) return "00:00"
  if (typeof t === "string") return t
  return `${String(t.hours ?? 0).padStart(2, "0")}:${String(t.minutes ?? 0).padStart(2, "0")}`
}
function parseGTime(s: string): { hours: number; minutes: number } {
  const [h, m] = (s || "00:00").split(":")
  return { hours: Number(h) || 0, minutes: Number(m) || 0 }
}
function fmtGDate(d: any): string {
  if (!d) return ""
  return `${d.year}-${String(d.month).padStart(2, "0")}-${String(d.day).padStart(2, "0")}`
}
function parseGDate(s: string): { year: number; month: number; day: number } | null {
  if (!s) return null
  const [y, m, d] = s.split("-")
  if (!y || !m || !d) return null
  return { year: Number(y), month: Number(m), day: Number(d) }
}

// ── Additional phones editor ────────────────────────────────────────────────
function PhonesEditor({ initialValue, onSave, onCancel }: { initialValue: any; onSave: (v: string[]) => void; onCancel: () => void }) {
  const [phones, setPhones] = useState<string[]>(() => (Array.isArray(initialValue) ? initialValue.map(String) : []))
  const update = (i: number, v: string) => setPhones(prev => prev.map((p, idx) => (idx === i ? v : p)))
  const remove = (i: number) => setPhones(prev => prev.filter((_, idx) => idx !== i))
  return (
    <div className="space-y-2">
      {phones.map((p, i) => (
        <div key={i} className="flex items-center gap-2">
          <Input value={p} onChange={e => update(i, e.target.value)} placeholder="+91 …" className="bg-background/50 border-border text-sm" />
          <button type="button" onClick={() => remove(i)} className="text-muted-foreground hover:text-red-400 text-lg px-1">×</button>
        </div>
      ))}
      <Button variant="ghost" size="sm" className="text-xs" onClick={() => setPhones(prev => [...prev, ""])}>+ Add phone</Button>
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onCancel}>Cancel</Button>
        <Button size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={() => onSave(phones.map(p => p.trim()).filter(Boolean))}>Save</Button>
      </div>
    </div>
  )
}

// ── Special hours editor ────────────────────────────────────────────────────
interface SpecialRow { date: string; closed: boolean; open: string; close: string }
function SpecialHoursEditor({ initialValue, onSave, onCancel }: { initialValue: any; onSave: (v: any) => void; onCancel: () => void }) {
  const parse = (val: any): SpecialRow[] => {
    const periods = (val && val.specialHourPeriods) || []
    return periods.map((p: any) => ({
      date: fmtGDate(p.startDate),
      closed: !!p.closed,
      open: fmtGTime(p.openTime),
      close: fmtGTime(p.closeTime),
    }))
  }
  const [rows, setRows] = useState<SpecialRow[]>(() => parse(initialValue))
  const update = (i: number, patch: Partial<SpecialRow>) => setRows(prev => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  const remove = (i: number) => setRows(prev => prev.filter((_, idx) => idx !== i))
  const save = () => {
    const specialHourPeriods = rows.filter(r => r.date).map(r => {
      const startDate = parseGDate(r.date)
      if (r.closed) return { startDate, endDate: startDate, closed: true }
      return { startDate, endDate: startDate, openTime: parseGTime(r.open), closeTime: parseGTime(r.close) }
    })
    onSave({ specialHourPeriods })
  }
  return (
    <div className="space-y-2">
      {rows.map((r, i) => (
        <div key={i} className="flex flex-wrap items-center gap-2 p-2 rounded-lg bg-background/50 border border-border/30">
          <input type="date" value={r.date} onChange={e => update(i, { date: e.target.value })} className="rounded border border-border bg-background/50 px-2 py-1 text-xs text-foreground" />
          <label className="flex items-center gap-1.5 text-xs">
            <input type="checkbox" checked={r.closed} onChange={e => update(i, { closed: e.target.checked })} className="h-3.5 w-3.5" />
            Closed
          </label>
          {!r.closed && (
            <>
              <input type="text" value={r.open} onChange={e => update(i, { open: e.target.value })} placeholder="09:00" className="w-16 rounded border border-border bg-background/50 px-2 py-1 text-center text-xs font-mono" />
              <span className="text-xs text-muted-foreground">–</span>
              <input type="text" value={r.close} onChange={e => update(i, { close: e.target.value })} placeholder="17:00" className="w-16 rounded border border-border bg-background/50 px-2 py-1 text-center text-xs font-mono" />
            </>
          )}
          <button type="button" onClick={() => remove(i)} className="text-muted-foreground hover:text-red-400 text-lg px-1 ml-auto">×</button>
        </div>
      ))}
      <Button variant="ghost" size="sm" className="text-xs" onClick={() => setRows(prev => [...prev, { date: "", closed: true, open: "09:00", close: "17:00" }])}>+ Add date</Button>
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onCancel}>Cancel</Button>
        <Button size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={save}>Save</Button>
      </div>
    </div>
  )
}

// ── Services (free-form service items) editor ───────────────────────────────
interface SvcRow { displayName: string; description: string; price: string; _original?: any }
function ServiceItemsEditor({ initialValue, onSave, onCancel }: { initialValue: any; onSave: (v: any[]) => void; onCancel: () => void }) {
  const items: any[] = Array.isArray(initialValue) ? initialValue : []
  // Preserve non-free-form (structured) items untouched; only edit free-form ones.
  const preserved = items.filter(it => !it.freeFormServiceItem)
  const parse = (): SvcRow[] => items.filter(it => it.freeFormServiceItem).map(it => ({
    displayName: it.freeFormServiceItem?.label?.displayName || "",
    description: it.freeFormServiceItem?.label?.description || "",
    price: it.price?.units != null ? String(it.price.units) : "",
    _original: it,
  }))
  const [rows, setRows] = useState<SvcRow[]>(parse)
  const update = (i: number, patch: Partial<SvcRow>) => setRows(prev => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  const remove = (i: number) => setRows(prev => prev.filter((_, idx) => idx !== i))
  const save = () => {
    const edited = rows.filter(r => r.displayName.trim()).map(r => {
      const orig = r._original || {}
      const item: any = {
        ...orig,
        freeFormServiceItem: {
          ...(orig.freeFormServiceItem || {}),
          label: { displayName: r.displayName.trim(), ...(r.description.trim() ? { description: r.description.trim() } : {}) },
        },
      }
      if (r.price.trim()) {
        item.price = { currencyCode: orig.price?.currencyCode || "INR", units: r.price.trim() }
      } else {
        delete item.price
      }
      return item
    })
    onSave([...preserved, ...edited])
  }
  return (
    <div className="space-y-3">
      {rows.map((r, i) => (
        <div key={i} className="rounded-lg border border-border/50 bg-muted/10 p-3 space-y-2">
          <div className="flex items-center gap-2">
            <Input value={r.displayName} onChange={e => update(i, { displayName: e.target.value })} placeholder="Service name" className="bg-background/50 border-border text-sm font-semibold" />
            <Input value={r.price} onChange={e => update(i, { price: e.target.value })} placeholder="Price" className="bg-background/50 border-border text-sm w-24" />
            <button type="button" onClick={() => remove(i)} className="text-muted-foreground hover:text-red-400 text-lg px-1">×</button>
          </div>
          <Textarea value={r.description} onChange={e => update(i, { description: e.target.value })} placeholder="Description (optional)" className="bg-background/50 border-border text-xs min-h-[60px]" />
        </div>
      ))}
      <Button variant="ghost" size="sm" className="text-xs" onClick={() => setRows(prev => [...prev, { displayName: "", description: "", price: "" }])}>+ Add service</Button>
      {preserved.length > 0 && (
        <p className="text-[11px] text-muted-foreground">{preserved.length} structured service(s) from Google are preserved and not shown here.</p>
      )}
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onCancel}>Cancel</Button>
        <Button size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={save}>Save</Button>
      </div>
    </div>
  )
}

// ── Open status editor ──────────────────────────────────────────────────────
const OPEN_STATUSES = ["OPEN", "CLOSED_TEMPORARILY", "CLOSED_PERMANENTLY"]
function OpenStatusEditor({ initialValue, onSave, onCancel }: { initialValue: any; onSave: (v: any) => void; onCancel: () => void }) {
  const [status, setStatus] = useState<string>(() => (initialValue?.status || (typeof initialValue === "string" ? initialValue : "OPEN")))
  const [openingDate, setOpeningDate] = useState<string>(() => fmtGDate(initialValue?.openingDate))
  const save = () => {
    const out: any = { status }
    const d = parseGDate(openingDate)
    if (d) out.openingDate = d
    onSave(out)
  }
  return (
    <div className="space-y-2">
      <select value={status} onChange={e => setStatus(e.target.value)} className="w-full rounded-md border border-border bg-background/50 px-3 py-2 text-sm text-foreground">
        {OPEN_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, " ")}</option>)}
      </select>
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted-foreground">Opening date (optional):</span>
        <input type="date" value={openingDate} onChange={e => setOpeningDate(e.target.value)} className="rounded border border-border bg-background/50 px-2 py-1 text-foreground" />
      </div>
      <div className="flex justify-end gap-2 pt-1">
        <Button variant="ghost" size="sm" className="text-xs" onClick={onCancel}>Cancel</Button>
        <Button size="sm" className="text-xs bg-indigo-600 hover:bg-indigo-500 text-white" onClick={save}>Save</Button>
      </div>
    </div>
  )
}
