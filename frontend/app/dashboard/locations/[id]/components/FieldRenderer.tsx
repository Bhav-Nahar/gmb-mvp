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

    const uiComponent = fieldConfig.ui_component || (fieldConfig.name === "business_hours" ? "business_hours_editor" : fieldConfig.name === "primary_category" ? "category_autocomplete" : (typeof value === "object" || fieldConfig.name.includes("description") ? "textarea" : "input"))
    switch (uiComponent) {
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
            {fieldConfig.ui_component !== "business_hours_editor" && fieldConfig.name !== "business_hours" && fieldConfig.name !== "address" && (
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
