import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { FieldRenderer } from "../components/FieldRenderer"
import { CriticalFieldWarningModal } from "../components/CriticalFieldWarningModal"
import { useLocationWorkspace } from "@/hooks/useLocationWorkspace"
import { useAuth } from "@/hooks/useAuth"
import { SkeletonLoader } from "../components/SkeletonLoader"
import { DynamicFormEngine } from "../components/DynamicFormEngine"

interface ProfileTabProps {
  locationId: number
  setHasUnsavedChanges?: (hasUnsaved: boolean) => void
}

export function ProfileTab({ locationId, setHasUnsavedChanges }: ProfileTabProps) {
  const { user, isAdmin } = useAuth()
  const { location, isLocationLoading, edits, isEditsLoading, createEditMutation } = useLocationWorkspace(locationId)
  
  const { data: fieldConfigs, isLoading: isConfigsLoading, isError: isConfigsError, refetch: refetchConfigs } = useQuery({
    queryKey: ['field-configs'],
    queryFn: () => api.get<any[]>('/fields'),
  })

  const [warningModalOpen, setWarningModalOpen] = useState(false)
  const [pendingCriticalEdit, setPendingCriticalEdit] = useState<any>(null)
  const [editingFields, setEditingFields] = useState<Record<string, boolean>>({})

  const handleEditingChange = (fieldName: string, isEditing: boolean) => {
    setEditingFields(prev => {
      const updated = { ...prev, [fieldName]: isEditing }
      if (setHasUnsavedChanges) {
        setHasUnsavedChanges(Object.values(updated).some(Boolean))
      }
      return updated
    })
  }

  if (isLocationLoading || isConfigsLoading || isEditsLoading) {
    return <SkeletonLoader />
  }

  if (isConfigsError) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 p-8 text-center rounded-xl border border-destructive/30 bg-destructive/5">
        <p className="text-sm font-medium text-destructive">Failed to load profile configuration.</p>
        <button
          onClick={() => refetchConfigs()}
          className="px-4 py-2 rounded-lg text-sm font-semibold bg-muted/30 hover:bg-muted/50 border border-border transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  const handleSave = (fieldName: string, newValue: any, acknowledged: boolean) => {
    let finalValue = newValue
    try {
      if (typeof newValue === 'string' && (newValue.startsWith('{') || newValue.startsWith('['))) {
        finalValue = JSON.parse(newValue)
      }
    } catch (e) {
      // Keep as string if parsing fails
    }

    createEditMutation.mutate({
      field_name: fieldName,
      new_value: finalValue,
      warning_acknowledged: acknowledged
    })
  }

  const handleCriticalEdit = (fieldName: string, newValue: any, config: any) => {
    setPendingCriticalEdit({ fieldName, newValue, config })
    setWarningModalOpen(true)
  }

  const confirmCriticalEdit = () => {
    if (pendingCriticalEdit) {
      handleSave(pendingCriticalEdit.fieldName, pendingCriticalEdit.newValue, true)
    }
    setWarningModalOpen(false)
    setPendingCriticalEdit(null)
  }

  const criticalFields = fieldConfigs?.filter(f => f.is_critical && !f.is_read_only) || []
  const standardFields = fieldConfigs?.filter(f => !f.is_critical && !f.is_read_only) || []
  const readOnlyFields = fieldConfigs?.filter(f => f.is_read_only) || []

  const renderSection = (title: string, fields: any[]) => (
    fields.length > 0 && (
      <div className="space-y-4">
        <h3 className="text-lg font-medium text-foreground border-b border-border/50 pb-2">{title}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {fields.map(config => {
            const activeEdit = edits?.find(e => 
              e.field_name === config.name && 
              ['Draft', 'Pending', 'Approved', 'Publishing'].includes(e.status)
            )
            return (
              <FieldRenderer
                key={config.name}
                fieldConfig={config}
                value={location?.[config.name]}
                editState={activeEdit}
                userRole={user?.role || "Staff"}
                onSave={handleSave}
                onCriticalEdit={handleCriticalEdit}
                onEditingChange={(isEditing) => handleEditingChange(config.name, isEditing)}
              />
            )
          })}
        </div>
      </div>
    )
  )

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {renderSection("Critical Fields", criticalFields)}
      {renderSection("Standard Fields", standardFields)}

      <div className="space-y-4 pt-6 border-t border-border/50">
        <DynamicFormEngine locationId={locationId} />
      </div>

      {isAdmin && renderSection("System Fields (Admin Only)", readOnlyFields)}

      <CriticalFieldWarningModal
        isOpen={warningModalOpen}
        onClose={() => setWarningModalOpen(false)}
        onConfirm={confirmCriticalEdit}
        title={pendingCriticalEdit?.config?.warning_title}
        body={pendingCriticalEdit?.config?.warning_body}
      />
    </div>
  )
}
