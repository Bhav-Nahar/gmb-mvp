import React, { useState } from "react"
import { useLocationWorkspace } from "@/hooks/useLocationWorkspace"
import { useAuth } from "@/hooks/useAuth"
import { SkeletonLoader } from "../components/SkeletonLoader"
import { LeadsPanel } from "./LeadsPanel"
import { Button } from "@/components/ui/button"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogClose } from "@/components/ui/dialog"
import { Globe, Eye, CheckCircle2, AlertTriangle, ExternalLink, ArrowUpRight, Lock, Copy } from "lucide-react"
import { toast } from "sonner"

interface MicrositeTabProps {
  locationId: number
}

function formatDistanceToNow(dateStr: string): string {
  if (!dateStr) return ""
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    
    if (diffMins < 1) return 'just now'
    if (diffMins < 60) return `${diffMins}m ago`
    
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    
    const diffDays = Math.floor(diffHours / 24)
    if (diffDays < 30) return `${diffDays}d ago`
    
    return date.toLocaleDateString()
  } catch (e) {
    return dateStr
  }
}

export function MicrositeTab({ locationId }: MicrositeTabProps) {
  const { isAdmin } = useAuth()
  const {
    microsite,
    isMicrositeLoading,
    isMicrositeError,
    micrositeError,
    generateMicrositeMutation,
    publishMicrositeMutation,
    unpublishMicrositeMutation,
    createEditMutation,
  } = useLocationWorkspace(locationId)

  const [isUnpublishConfirmOpen, setIsUnpublishConfirmOpen] = useState(false)
  const [isPublishGoogleConfirmOpen, setIsPublishGoogleConfirmOpen] = useState(false)

  // Copy public URL helper
  const handleCopyLink = (url: string) => {
    navigator.clipboard.writeText(url)
    toast.success("Link copied to clipboard!")
  }

  // Handle unpublish request
  const handleUnpublish = () => {
    setIsUnpublishConfirmOpen(false)
    unpublishMicrositeMutation.mutate()
  }

  // Push the microsite URL onto the GBP listing's website field. Goes through the
  // normal listing-edit approval flow (creates a Pending "website" edit).
  const handlePublishToGoogle = () => {
    setIsPublishGoogleConfirmOpen(false)
    createEditMutation.mutate(
      { field_name: "website", new_value: microsite?.public_url, warning_acknowledged: false },
      {
        onSuccess: () =>
          toast.success("Submitted for approval — approve it in the Edits tab to push the link live on Google."),
      }
    )
  }

  if (isMicrositeLoading) {
    return <SkeletonLoader />
  }

  // Handle 404 case: backend returns 404 when no microsite exists yet.
  // We check both the error flag AND the absence of data — avoids a crash on
  // line 105 if the error message text ever changes, since microsite would be
  // undefined and destructuring it would throw a runtime error.
  const noMicrositeExists = isMicrositeError || !microsite

  if (noMicrositeExists) {
    return (
      <div className="animate-in fade-in duration-500 max-w-2xl mx-auto py-8">
        <div className="bg-card border border-border rounded-2xl p-6 sm:p-8 text-center space-y-6 shadow-sm">
          <div className="w-16 h-16 bg-primary/10 text-primary rounded-full flex items-center justify-center mx-auto">
            <Globe className="w-8 h-8" />
          </div>
          <div className="space-y-2">
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-foreground">Launch Your Location&apos;s Microsite</h2>
            <p className="text-muted-foreground text-sm max-w-md mx-auto">
              Create a fully-responsive, fast-loading, public page for this location. It showcases location details, reviews, and media to improve local search engine presence.
            </p>
          </div>

          <div className="pt-2">
            {isAdmin ? (
              <Button
                size="lg"
                onClick={() => generateMicrositeMutation.mutate()}
                disabled={generateMicrositeMutation.isPending}
                className="w-full sm:w-auto font-medium shadow-md shadow-primary/10 transition-transform active:scale-95"
              >
                {generateMicrositeMutation.isPending ? "Generating Draft..." : "Generate Microsite"}
              </Button>
            ) : (
              <div className="inline-flex items-center gap-2 text-xs bg-muted text-muted-foreground px-3 py-1.5 rounded-full border border-border">
                <Lock className="w-3.5 h-3.5" /> Only administrators can generate microsites.
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  const { status, public_url, view_count, published_at, unpublished_at } = microsite

  return (
    <div className="animate-in fade-in duration-500 max-w-4xl mx-auto space-y-6">
      
      {/* Overview Status Card */}
      <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-border/50 pb-6">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-bold text-foreground">Microsite Status</h3>
              {status === "published" && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
                  Live / Published
                </span>
              )}
              {status === "draft" && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                  Draft
                </span>
              )}
              {status === "unpublished" && (
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-red-500/10 text-red-500 border border-red-500/20">
                  Offline / Unpublished
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {status === "published" && published_at && `Published ${formatDistanceToNow(published_at)}`}
              {status === "unpublished" && unpublished_at && `Taken offline ${formatDistanceToNow(unpublished_at)}`}
              {status === "draft" && "Ready to be published"}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            {/* View Live (Only when published) */}
            {status === "published" && (
              <a
                href={public_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center justify-center rounded-lg text-sm font-medium border border-border bg-background hover:bg-muted text-foreground transition-colors px-4 py-2 gap-2 h-10 shadow-xs"
              >
                <Eye className="w-4 h-4" /> View Live <ArrowUpRight className="w-3.5 h-3.5 text-muted-foreground" />
              </a>
            )}

            {/* Admin Actions */}
            {isAdmin ? (
              <>
                {status === "draft" && (
                  <Button
                    onClick={() => publishMicrositeMutation.mutate()}
                    disabled={publishMicrositeMutation.isPending}
                    className="shadow-sm font-medium"
                  >
                    {publishMicrositeMutation.isPending ? "Publishing..." : "Publish Microsite"}
                  </Button>
                )}
                {status === "published" && (
                  <Button
                    onClick={() => setIsPublishGoogleConfirmOpen(true)}
                    disabled={createEditMutation.isPending}
                    className="shadow-sm font-medium gap-2"
                  >
                    <Globe className="w-4 h-4" />
                    {createEditMutation.isPending ? "Submitting..." : "Publish to Google"}
                  </Button>
                )}
                {status === "published" && (
                  <Button
                    variant="outline"
                    onClick={() => setIsUnpublishConfirmOpen(true)}
                    disabled={unpublishMicrositeMutation.isPending}
                    className="border-red-500/20 hover:bg-red-500/5 text-red-500 hover:text-red-600 transition-colors"
                  >
                    Unpublish
                  </Button>
                )}
                {status === "unpublished" && (
                  <Button
                    onClick={() => publishMicrositeMutation.mutate()}
                    disabled={publishMicrositeMutation.isPending}
                    className="shadow-sm font-medium"
                  >
                    {publishMicrositeMutation.isPending ? "Re-publishing..." : "Re-publish"}
                  </Button>
                )}
              </>
            ) : (
              <div className="inline-flex items-center gap-2 text-[11px] text-muted-foreground bg-muted/50 px-2.5 py-1.5 rounded-lg border border-border">
                <Lock className="w-3 h-3" /> Actions restricted to Admins
              </div>
            )}
          </div>
        </div>

        {/* Link / Analytics details */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="md:col-span-2 space-y-2">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Public URL</h4>
            {status === "published" ? (
              <div className="flex items-center gap-2 bg-muted/40 border border-border/80 rounded-lg p-2.5 max-w-full">
                <span className="text-sm font-mono text-foreground truncate select-all flex-1">
                  {public_url}
                </span>
                <button
                  onClick={() => handleCopyLink(public_url)}
                  className="p-1 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors shrink-0"
                  title="Copy link"
                >
                  <Copy className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="bg-muted/10 border border-dashed border-border rounded-lg p-3 text-muted-foreground text-sm flex items-center gap-2 italic">
                <Globe className="w-4 h-4 text-muted-foreground/50 shrink-0" />
                {status === "draft"
                  ? "A public link will be assigned once published (currently in Draft)."
                  : "Microsite is currently taken offline."}
              </div>
            )}
          </div>

          <div className="bg-muted/20 border border-border/50 rounded-xl p-4 flex flex-col justify-between">
            <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">Total Views</h4>
            <div className="mt-2 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold tracking-tight text-foreground">
                {view_count || 0}
              </span>
              <span className="text-xs text-muted-foreground">views</span>
            </div>
          </div>
        </div>
      </div>

      {/* Leads captured from the public microsite form */}
      <LeadsPanel locationId={locationId} />

      {/* Confirmation Dialog for Publishing the link to Google */}
      <Dialog open={isPublishGoogleConfirmOpen} onOpenChange={setIsPublishGoogleConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Globe className="w-5 h-5 shrink-0 text-primary" /> Publish microsite link to Google
            </DialogTitle>
            <DialogDescription className="pt-2">
              This will <strong>replace the Website link on the Google Business Profile</strong> with this microsite&apos;s URL. It is submitted as an edit and goes through the normal <strong>approval &amp; publish</strong> flow before it goes live on Google — it does not change Google immediately.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              Cancel
            </DialogClose>
            <Button onClick={handlePublishToGoogle} className="font-medium">
              Submit for approval
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog for Unpublishing */}
      <Dialog open={isUnpublishConfirmOpen} onOpenChange={setIsUnpublishConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-red-500">
              <AlertTriangle className="w-5 h-5 shrink-0" /> Confirm Unpublish
            </DialogTitle>
            <DialogDescription className="pt-2">
              Are you sure you want to unpublish this microsite? Taking this page offline will cause search engines and visitors to receive an <strong>HTTP 410 Gone</strong> response. You can re-publish this page at any time.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>
              Cancel
            </DialogClose>
            <Button
              variant="destructive"
              onClick={handleUnpublish}
              className="bg-red-500 hover:bg-red-600 text-white font-medium"
            >
              Confirm Unpublish
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
