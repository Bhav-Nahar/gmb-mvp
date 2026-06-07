"use client"
import { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "sonner"
import { SkeletonLoader } from "./SkeletonLoader"

interface DynamicFormEngineProps {
  locationId: number
}

export function DynamicFormEngine({ locationId }: DynamicFormEngineProps) {
  const queryClient = useQueryClient()
  const [draftState, setDraftState] = useState<Record<string, any>>({})
  const [hasChanges, setHasChanges] = useState(false)
  const [isSeeded, setIsSeeded] = useState(false)
  const [isPublishing, setIsPublishing] = useState(false)
  const [publishTimedOut, setPublishTimedOut] = useState(false)
  const publishStartTimeRef = useRef<number | null>(null)
  const PUBLISH_TIMEOUT_MS = 60000

  useQuery({
    queryKey: ['location-publish-status', locationId],
    queryFn: async () => {
      // Check 60-second publish timeout
      if (publishStartTimeRef.current !== null && Date.now() - publishStartTimeRef.current > PUBLISH_TIMEOUT_MS) {
        setIsPublishing(false)
        setPublishTimedOut(true)
        publishStartTimeRef.current = null
        toast.error("Publishing timed out after 60 seconds. Please try again.")
        return null
      }

      const res = await api.get<{ status: string, attention_needed?: boolean, attention_reason?: string }>(`/locations/${locationId}/publish-status`)
      if (res.status === 'Synced' || res.status === 'Failed') {
        setIsPublishing(false)
        publishStartTimeRef.current = null
        if (res.status === 'Synced') {
          toast.success("Attributes published to Google")
          setDraftState({})
          setHasChanges(false)
          setIsSeeded(false)
        } else if (res.status === 'Failed') {
          toast.error(res.attention_reason || "Failed to publish attributes. Your drafts are still saved.")
        }
        queryClient.invalidateQueries({ queryKey: ['location-attributes', locationId] })
      }
      return res
    },
    refetchInterval: isPublishing ? 3000 : false,
    enabled: isPublishing
  })

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['location-attributes', locationId],
    queryFn: async () => {
      const res = await api.get<{ schema: any[] }>(`/locations/${locationId}/form-schema`)
      return res.schema
    }
  })

  // Seed draft state from existing drafts on first load
  useEffect(() => {
    if (!data || isSeeded) return
    const initialDrafts: Record<string, any> = {}
    data.forEach(field => {
      if (field.draft_value !== undefined && field.draft_value !== null) {
        initialDrafts[field.attribute_id] = field.draft_value
      } else if (field.is_rejected && field.rejected_value !== undefined && field.rejected_value !== null) {
        // Carry over the value that was rejected so it doesn't "vanish"
        initialDrafts[field.attribute_id] = field.rejected_value
      }
    })
    if (Object.keys(initialDrafts).length > 0) {
      setDraftState(initialDrafts)
    }
    setIsSeeded(true)
  }, [data, isSeeded])

  const suppressMutation = useMutation({
    mutationFn: (attributeId: string) => api.post(`/locations/${locationId}/suppress-rejection`, { attribute_id: attributeId }),
    onSuccess: () => {
      toast.success("Warning dismissed. You can now edit this attribute.")
      queryClient.invalidateQueries({ queryKey: ['location-attributes', locationId] })
    },
    onError: (err: any) => {
      toast.error(err?.message || "Failed to dismiss warning")
    }
  })

  const saveDraftMutation = useMutation({
    mutationFn: (payload: any) => api.post(`/locations/${locationId}/draft-attributes`, payload),
    onSuccess: async () => {
      toast.success("Draft attributes saved")
      setIsSeeded(false)
      await queryClient.invalidateQueries({ queryKey: ['location-attributes', locationId] })
      queryClient.invalidateQueries({ queryKey: ['location', locationId] })
    },
    onError: (err: any) => {
      toast.error(err?.message || "Failed to save drafts")
    }
  })

  const publishMutation = useMutation({
    mutationFn: () => api.post<{
      success?: boolean
      status?: string
      message?: string
    }>(`/locations/${locationId}/publish-attributes`, {}),
    onMutate: async () => {
      const previousDraftState = { ...draftState }
      return { previousDraftState }
    },
    onSuccess: (data) => {
      setIsPublishing(true)
      setPublishTimedOut(false)
      publishStartTimeRef.current = Date.now()
      toast.info("Publishing attributes to Google...")
    },
    onError: (err: any, variables, context) => {
      if (context?.previousDraftState) {
        setDraftState(context.previousDraftState)
        setHasChanges(true)
      }
      toast.error(err?.message || "Failed to enqueue publish task")
    }
  })

  if (isLoading) return <SkeletonLoader />
  if (isError) return (
    <div className="p-4 border border-destructive/30 rounded-lg text-destructive text-sm bg-destructive/5 flex items-center justify-between gap-4">
      <span>Failed to load dynamic attributes.</span>
      <Button variant="outline" size="sm" onClick={() => refetch()} className="text-xs shrink-0">
        Retry
      </Button>
    </div>
  )
  if (!data || data.length === 0) return (
    <div className="p-4 border border-dashed border-border/50 rounded-lg text-center text-muted-foreground text-sm">
      No dynamic attributes available for this location&apos;s category.
    </div>
  )

  const handleFieldChange = (attrId: string, val: any) => {
    setDraftState(prev => ({ ...prev, [attrId]: val }))
    setHasChanges(true)
  }

  const renderField = (field: any) => {
    const val = draftState[field.attribute_id] !== undefined
      ? draftState[field.attribute_id]
      : (field.is_rejected && field.rejected_value !== undefined && field.rejected_value !== null 
          ? field.rejected_value 
          : field.current_value)

    const rejectionBox = field.is_rejected ? (() => {
      const getFriendlyReason = (reason: string) => {
        if (reason === "INVALID_ATTRIBUTE_NAME") {
          return "Google has rejected this specific attribute for your business category. It may have been recently deprecated or is restricted for your location type."
        }
        if (reason === "ATTRIBUTE_PROVIDER_URL_NOT_ALLOWED") {
          return "Google does not allow this specific booking or calendar provider as an appointment link. Please try using a direct link from your own website or a Google-supported booking partner."
        }
        if (reason === "INVALID_SOCIAL_MEDIA_PROFILE_URL") {
          return "Google has rejected this social media link. Please ensure the URL is correct and follows the standard format for this platform (e.g., https://instagram.com/yourprofile)."
        }
        return reason || "This attribute is not currently supported for this specific Google Business Profile location."
      }

      return (
        <div className="mt-2 mb-3 text-[11px] text-destructive bg-destructive/5 border border-destructive/20 p-2.5 rounded-md flex flex-col gap-2 shadow-sm animate-in slide-in-from-top-1 duration-200">
          <div className="flex items-start gap-2">
            <svg className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div className="space-y-1">
              <span className="font-bold block uppercase tracking-tight text-[10px]">Google Rejection</span>
              <p className="text-muted-foreground leading-snug">
                {getFriendlyReason(field.rejection_reason)}
              </p>
            </div>
          </div>
          <Button 
            variant="ghost" 
            size="sm" 
            className="self-start text-[10px] h-5 px-1.5 text-destructive/70 hover:text-destructive hover:bg-destructive/5 font-medium -ml-1"
            onClick={() => suppressMutation.mutate(field.attribute_id)}
            disabled={suppressMutation.isPending}
          >
            Dismiss Warning
          </Button>
        </div>
      )
    })() : null

    let inputElement = null
    const baseClass = field.is_rejected ? "border-destructive/50 focus-visible:ring-destructive" : ""

    if (field.value_type === "BOOL") {
      // Render as styled toggle button pair
      inputElement = (
        <div className="flex gap-2 mt-2">
          <button
            type="button"
            onClick={() => handleFieldChange(field.attribute_id, val === true ? null : true)}
            className={`flex-1 py-1.5 px-3 rounded-md text-sm border transition-colors ${
              val === true
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-transparent text-muted-foreground border-border/50 hover:border-border"
            } ${field.is_rejected && val === true ? "bg-destructive border-destructive" : ""}`}
          >
            Yes
          </button>
          <button
            type="button"
            onClick={() => handleFieldChange(field.attribute_id, val === false ? null : false)}
            className={`flex-1 py-1.5 px-3 rounded-md text-sm border transition-colors ${
              val === false
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-transparent text-muted-foreground border-border/50 hover:border-border"
            } ${field.is_rejected && val === false ? "bg-destructive border-destructive" : ""}`}
          >
            No
          </button>
          {val === undefined || val === null ? (
            <span className="text-xs text-muted-foreground self-center ml-1">Not set</span>
          ) : (
            <button
              type="button"
              onClick={() => handleFieldChange(field.attribute_id, null)}
              className="text-xs text-muted-foreground hover:text-foreground underline ml-2 self-center transition-colors"
            >
              Clear
            </button>
          )}
        </div>
      )
    } else if (field.value_type === "REPEATED_ENUM" || (field.value_type === "ENUM" && field.is_repeatable)) {
      let parsedOptions = field.options
      if (typeof parsedOptions === 'string') {
        try { parsedOptions = JSON.parse(parsedOptions) } catch(e) {}
      }
      const options = Array.isArray(parsedOptions)
        ? parsedOptions
        : (parsedOptions?.repeatedEnumValue?.supportedOptions
            || parsedOptions?.enumValue?.supportedOptions
            || parsedOptions?.supportedOptions
            || [])
      const selectedList: string[] = Array.isArray(val) ? val : []
      inputElement = (
        <div className="mt-2 space-y-1.5 max-h-48 overflow-y-auto">
          {options.length === 0 && (
            <p className="text-xs text-muted-foreground">No options available</p>
          )}
          {options.map((opt: any) => {
            const isChecked = selectedList.includes(opt.value)
            return (
              <label
                key={opt.value}
                className="flex items-center gap-2.5 cursor-pointer group"
              >
                <div
                  onClick={() => {
                    if (isChecked) {
                      handleFieldChange(field.attribute_id, selectedList.filter(v => v !== opt.value))
                    } else {
                      handleFieldChange(field.attribute_id, [...selectedList, opt.value])
                    }
                  }}
                  className={`w-4 h-4 rounded border flex items-center justify-center transition-colors cursor-pointer flex-shrink-0 ${
                    isChecked
                      ? (field.is_rejected ? "bg-destructive border-destructive" : "bg-primary border-primary")
                      : "bg-transparent border-border/60 group-hover:border-border"
                  }`}
                >
                  {isChecked && (
                    <svg className="w-2.5 h-2.5 text-primary-foreground" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                </div>
                <span className="text-sm text-foreground">{opt.displayName}</span>
              </label>
            )
          })}
        </div>
      )
    } else if (field.value_type === "ENUM" && !field.is_repeatable) {
      let parsedOptions = field.options
      if (typeof parsedOptions === 'string') {
        try { parsedOptions = JSON.parse(parsedOptions) } catch(e) {}
      }
      const options = Array.isArray(parsedOptions)
        ? parsedOptions
        : (parsedOptions?.enumValue?.supportedOptions
            || parsedOptions?.repeatedEnumValue?.supportedOptions
            || parsedOptions?.supportedOptions
            || [])
      inputElement = (
        <div className="mt-2 space-y-1.5">
          {options.map((opt: any) => (
            <label key={opt.value} className="flex items-center gap-2.5 cursor-pointer group">
              <div
                onClick={() => handleFieldChange(field.attribute_id, val === opt.value ? null : opt.value)}
                className={`w-4 h-4 rounded-full border flex items-center justify-center transition-colors cursor-pointer flex-shrink-0 ${
                  val === opt.value
                    ? (field.is_rejected ? "border-destructive" : "border-primary")
                    : "border-border/60 group-hover:border-border"
                }`}
              >
                {val === opt.value && (
                  <div className={`w-2 h-2 rounded-full ${field.is_rejected ? "bg-destructive" : "bg-primary"}`} />
                )}
              </div>
              <span className="text-sm text-foreground">{opt.displayName}</span>
            </label>
          ))}
          {val !== undefined && val !== null && (
            <button
              type="button"
              onClick={() => handleFieldChange(field.attribute_id, null)}
              className="text-[11px] text-muted-foreground hover:text-foreground underline transition-colors block mt-1"
            >
              Clear selection
            </button>
          )}
        </div>
      )
    } else if (field.value_type === "URL") {
      inputElement = (
        <Input
          className={`mt-2 text-sm ${baseClass}`}
          type="url"
          value={val || ""}
          onChange={(e) => handleFieldChange(field.attribute_id, e.target.value)}
          placeholder="https://..."
        />
      )
    } else {
      // Fallback text input
      inputElement = (
        <Input
          className={`mt-2 text-sm ${baseClass}`}
          value={val || ""}
          onChange={(e) => handleFieldChange(field.attribute_id, e.target.value)}
        />
      )
    }

    return (
      <div className="flex flex-col">
        {rejectionBox}
        {inputElement}
      </div>
    )
  }

  // Group fields by group_display_name
  const groups: Record<string, any[]> = {}
  data.forEach(field => {
    const group = field.group_display_name || "General"
    if (!groups[group]) groups[group] = []
    groups[group].push(field)
  })

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between border-b pb-4 sticky top-0 bg-background/95 backdrop-blur-sm z-10 pt-2">
        <div>
          <h2 className="text-lg font-semibold tracking-tight">Location Attributes</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Manage your business profile features and amenities</p>
        </div>
        <div className="flex gap-3">
          <Button 
            variant="outline" 
            size="sm"
            onClick={() => saveDraftMutation.mutate(draftState)}
            disabled={!hasChanges || saveDraftMutation.isPending || isPublishing}
            className="text-xs h-8"
          >
            {saveDraftMutation.isPending ? "Saving..." : "Save Drafts"}
          </Button>
          <Button 
            size="sm"
            className="text-xs h-8"
            disabled={publishMutation.isPending || isPublishing}
            onClick={async () => {
              if (hasChanges) {
                try {
                  await saveDraftMutation.mutateAsync(draftState)
                } catch (e) {
                  return
                }
              }
              publishMutation.mutate()
            }}
          >
            {isPublishing ? "Publishing..." : "Publish to Google"}
          </Button>
        </div>
      </div>

      {Object.entries(groups).map(([groupName, fields]) => (
        <div key={groupName} className="space-y-5 animate-in slide-in-from-bottom-2 duration-300">
          <h3 className="text-[11px] font-bold text-muted-foreground uppercase tracking-[0.1em] border-l-2 border-primary/40 pl-3">
            {groupName}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-6">
            {fields.map((field) => (
              <div key={field.attribute_id} className="flex flex-col group min-h-[70px]">
                <div className="flex items-center gap-2 mb-0.5">
                  <Label className="text-sm font-medium text-foreground leading-tight">
                    {field.display_name}
                  </Label>
                  {field.is_rejected && (
                    <span className="text-[9px] font-bold bg-destructive/10 text-destructive border border-destructive/20 px-1.5 py-0.5 rounded uppercase tracking-wider">
                      Rejected
                    </span>
                  )}
                </div>
                {renderField(field)}
                {field.draft_value !== null && field.draft_value !== undefined && draftState[field.attribute_id] === undefined && !field.is_rejected && (
                  <p className="text-xs text-amber-500 mt-1.5">Unsaved draft</p>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
