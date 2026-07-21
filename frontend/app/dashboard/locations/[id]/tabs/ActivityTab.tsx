import { useState } from "react"
import { useLocationWorkspace } from "@/hooks/useLocationWorkspace"
import { SkeletonLoader } from "../components/SkeletonLoader"
import { Badge } from "@/components/ui/badge"
import { ChangeDiff, GoogleUpdateActions, formatDistanceToNow } from "@/components/changes/ChangeEntry"

interface ActivityTabProps {
  locationId: number
}

export function ActivityTab({ locationId }: ActivityTabProps) {
  // TODO: Add virtualization later for Activity feed (e.g. using @tanstack/react-virtual or react-window) if logs scale to thousands.
  const { activityLog, isActivityLoading } = useLocationWorkspace(locationId)
  const [filter, setFilter] = useState<string | null>(null)

  if (isActivityLoading) return <SkeletonLoader />

  const filteredLogs = filter 
    ? activityLog?.filter(log => log.entity_type === filter) 
    : activityLog

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-wrap gap-2">
        <Badge 
          variant={filter === null ? "default" : "outline"}
          className="cursor-pointer h-auto py-2 px-3 text-xs sm:h-5 sm:py-0.5 sm:px-2"
          onClick={() => setFilter(null)}
        >
          All
        </Badge>
        <Badge
          variant={filter === "ProfileChange" ? "default" : "outline"}
          className="cursor-pointer h-auto py-2 px-3 text-xs sm:h-5 sm:py-0.5 sm:px-2"
          onClick={() => setFilter("ProfileChange")}
        >
          Changes on Google
        </Badge>
        <Badge
          variant={filter === "ListingEdit" ? "default" : "outline"}
          className="cursor-pointer h-auto py-2 px-3 text-xs sm:h-5 sm:py-0.5 sm:px-2"
          onClick={() => setFilter("ListingEdit")}
        >
          Edits
        </Badge>
        <Badge 
          variant={filter === "SyncLog" ? "default" : "outline"}
          className="cursor-pointer h-auto py-2 px-3 text-xs sm:h-5 sm:py-0.5 sm:px-2"
          onClick={() => setFilter("SyncLog")}
        >
          Syncs
        </Badge>
        <Badge 
          variant={filter === "Review" || filter === "ReviewReply" ? "default" : "outline"}
          className="cursor-pointer h-auto py-2 px-3 text-xs sm:h-5 sm:py-0.5 sm:px-2"
          onClick={() => setFilter("Review")}
        >
          Reviews
        </Badge>
      </div>

      <div className="space-y-4">
        {(!filteredLogs || filteredLogs.length === 0) && (
          <div className="text-muted-foreground text-center py-8">No activity found.</div>
        )}
        
        {filteredLogs?.map(log => (
          <div key={log.id} className="flex gap-4 p-4 border border-border/50 bg-card rounded-lg shadow-sm hover:shadow-md transition-shadow">
            <div className="flex-1 space-y-2">
              <div className="flex justify-between items-start">
                <span className="font-medium text-sm text-foreground">{log.action}</span>
                <span className="text-xs text-muted-foreground">
                  {log.created_at ? formatDistanceToNow(new Date(log.created_at), { addSuffix: true }) : ''}
                </span>
              </div>
              <div className="text-xs text-muted-foreground font-mono bg-muted p-3 rounded-md max-h-48 overflow-y-auto">
                {log.entity_type === "ProfileChange"
                  ? <ChangeDiff payload={log.payload} />
                  : <pre>{JSON.stringify(log.payload, null, 2)}</pre>}
              </div>
              {log.entity_type === "ProfileChange" && log.payload?.source === "google" && (
                <GoogleUpdateActions locationId={locationId} activityId={log.id} payload={log.payload} />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
