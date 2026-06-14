import { useState } from "react"
import { useLocationWorkspace, LocationEdit } from "@/hooks/useLocationWorkspace"
import { SkeletonLoader } from "../components/SkeletonLoader"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Loader2, CheckCircle2, XCircle } from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"

interface TasksTabProps {
  locationId: number
}

export function TasksTab({ locationId }: TasksTabProps) {
  const { user, isAdmin } = useAuth()
  const { edits, isEditsLoading, approveMutation, rejectMutation, publishMutation, submitMutation } = useLocationWorkspace(locationId)
  
  const [rejectModalOpen, setRejectModalOpen] = useState(false)
  const [pendingRejectEdit, setPendingRejectEdit] = useState<LocationEdit | null>(null)
  const [rejectionNote, setRejectionNote] = useState("")

  if (isEditsLoading) return <SkeletonLoader />

  const pendingEdits = edits?.filter(e => e.status === 'Pending') || []
  const approvedEdits = edits?.filter(e => e.status === 'Approved') || []
  const draftEdits = edits?.filter(e => e.status === 'Draft' && e.actor_user_id === user?.id) || []
  const publishingEdits = edits?.filter(e => e.status === 'Publishing') || []
  const activeEdits = [...publishingEdits, ...approvedEdits, ...pendingEdits, ...draftEdits]

  const handleApprove = (edit: LocationEdit) => {
    approveMutation.mutate({ editId: edit.id, version: edit.version })
  }

  const handlePublish = (edit: LocationEdit) => {
    publishMutation.mutate({ editId: edit.id })
  }
  
  const handleSubmit = (edit: LocationEdit) => {
    submitMutation.mutate({ editId: edit.id, version: edit.version })
  }

  const handleRejectClick = (edit: LocationEdit) => {
    setPendingRejectEdit(edit)
    setRejectionNote("")
    setRejectModalOpen(true)
  }

  const confirmReject = () => {
    if (pendingRejectEdit) {
      rejectMutation.mutate({ 
        editId: pendingRejectEdit.id, 
        version: pendingRejectEdit.version, 
        rejection_note: rejectionNote 
      })
    }
    setRejectModalOpen(false)
    setPendingRejectEdit(null)
  }

  const renderValue = (val: any) => {
    if (val === null || val === undefined) return "Not set"
    if (typeof val === "object") return JSON.stringify(val)
    return String(val)
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      {activeEdits.length === 0 && (
        <div className="text-muted-foreground text-center py-8 border border-dashed border-border rounded-lg">
          No pending tasks or active edits.
        </div>
      )}

      {activeEdits.map(edit => (
        <div key={edit.id} className="p-4 border border-border/50 bg-card rounded-lg shadow-sm">
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-between sm:items-start mb-4">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2 mb-1">
                <span className="font-semibold break-words">{edit.field_name}</span>
                <Badge variant={
                  edit.status === 'Pending' ? 'destructive' :
                  edit.status === 'Approved' ? 'default' :
                  edit.status === 'Publishing' ? 'secondary' : 'outline'
                }>
                  {edit.status}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground">
                Last updated {edit.updated_at ? formatDistanceToNow(new Date(edit.updated_at), { addSuffix: true }) : ''}
              </div>
            </div>
            
            <div className="flex flex-wrap gap-2 shrink-0 w-full sm:w-auto">
              {edit.status === 'Draft' && (
                <Button
                  size="sm"
                  onClick={() => handleSubmit(edit)}
                  disabled={submitMutation.isPending}
                  className="w-full min-h-[44px] sm:w-auto sm:min-h-0"
                >
                  {submitMutation.isPending && submitMutation.variables?.editId === edit.id ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                  Submit for Approval
                </Button>
              )}
              {edit.status === 'Pending' && isAdmin && (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    className="flex-1 min-h-[44px] sm:flex-none sm:min-h-0 text-red-500 border-red-500/20 hover:bg-red-500/10"
                    onClick={() => handleRejectClick(edit)}
                  >
                    <XCircle className="w-4 h-4 mr-2" />
                    Reject
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => handleApprove(edit)}
                    disabled={approveMutation.isPending}
                    className="flex-1 min-h-[44px] sm:flex-none sm:min-h-0"
                  >
                    {approveMutation.isPending && approveMutation.variables?.editId === edit.id ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <CheckCircle2 className="w-4 h-4 mr-2" />}
                    Approve
                  </Button>
                </>
              )}
              {edit.status === 'Approved' && isAdmin && (
                <Button
                  size="sm"
                  onClick={() => handlePublish(edit)}
                  disabled={publishMutation.isPending}
                  className="w-full min-h-[44px] sm:w-auto sm:min-h-0"
                >
                  {publishMutation.isPending && publishMutation.variables?.editId === edit.id ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : null}
                  Publish to Google
                </Button>
              )}
              {edit.status === 'Publishing' && (
                <Button size="sm" variant="secondary" disabled className="w-full min-h-[44px] sm:w-auto sm:min-h-0">
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Publishing...
                </Button>
              )}
            </div>
          </div>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm bg-muted/50 p-3 rounded-md">
            <div>
              <span className="text-muted-foreground block text-xs mb-1 uppercase tracking-wider">Original Value</span>
              <span className="font-mono break-words">{renderValue(edit.original_value)}</span>
            </div>
            <div>
              <span className="text-muted-foreground block text-xs mb-1 uppercase tracking-wider">Proposed Value</span>
              <span className="font-mono text-green-500 break-words">{renderValue(edit.new_value)}</span>
            </div>
          </div>
        </div>
      ))}

      <Dialog open={rejectModalOpen} onOpenChange={setRejectModalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject Edit</DialogTitle>
            <DialogDescription>
              Please provide a reason for rejecting this edit. This will be visible in the activity log.
            </DialogDescription>
          </DialogHeader>
          <Textarea 
            placeholder="Rejection reason..." 
            value={rejectionNote}
            onChange={(e) => setRejectionNote(e.target.value)}
            className="mt-4"
          />
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setRejectModalOpen(false)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmReject}>Reject</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
