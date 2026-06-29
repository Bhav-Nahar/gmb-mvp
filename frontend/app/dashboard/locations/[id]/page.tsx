"use client";

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { ProfileTab } from "./tabs/ProfileTab"
import { ActivityTab } from "./tabs/ActivityTab"
import { TasksTab } from "./tabs/TasksTab"
import { ReviewsTab } from "./tabs/ReviewsTab"
import { PostsTab } from "./tabs/PostsTab"
import { useLocationWorkspace } from "@/hooks/useLocationWorkspace"
import { InsightsTab } from "./tabs/InsightsTab"
import { SearchIntelligenceTab } from "./tabs/SearchIntelligenceTab"
import { PhotosTab } from "./tabs/PhotosTab"
import { OverviewTab } from "./tabs/OverviewTab"
import { MicrositeTab } from "./tabs/MicrositeTab"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AlertCircle, ArrowLeft, RefreshCw, AlertTriangle, MessageSquare, Edit3, ClipboardList, TrendingUp, LayoutDashboard, Search, ImageIcon, Globe } from "lucide-react"
import Link from "next/link"
import { SkeletonLoader } from "./components/SkeletonLoader"
import { api } from "@/lib/api"
import { toast } from "sonner"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Badge } from "@/components/ui/badge"

const statusBadgeMap: Record<string, React.ReactNode> = {
  published: (
    <Badge className="h-5 text-[10px] bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/10 border-emerald-500/20 font-medium">
      Microsite: Live
    </Badge>
  ),
  draft: (
    <Badge className="h-5 text-[10px] bg-amber-500/10 text-amber-500 hover:bg-amber-500/10 border-amber-500/20 font-medium">
      Microsite: Draft
    </Badge>
  ),
  unpublished: (
    <Badge className="h-5 text-[10px] bg-red-500/10 text-red-500 hover:bg-red-500/10 border-red-500/20 font-medium">
      Microsite: Offline
    </Badge>
  )
};

const formatAddress = (addressVal: any): string => {
  if (!addressVal) return 'No address provided';
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

export default function LocationProfilePage() {
  const params = useParams()
  const locationId = Number(params.id)
  
  const {
    location,
    isLocationLoading,
    edits,
    isEditsError,
    refetchEdits,
    microsite,
    isMicrositeLoading,
    isMicrositeError
  } = useLocationWorkspace(locationId)
  const [activeTab, setActiveTab] = useState("overview")
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)

  const handleForceSync = async () => {
    setIsSyncing(true)
    try {
      await api.post('/locations/sync')
      toast.success("Sync started — refreshing from Google. This can take a minute.")
    } catch (err: any) {
      toast.error(err?.message || "Failed to start sync.")
    } finally {
      setIsSyncing(false)
    }
  }
  
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasUnsavedChanges) {
        e.preventDefault()
        e.returnValue = "You have unsaved edits. Are you sure you want to discard them and leave?"
        return e.returnValue
      }
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [hasUnsavedChanges])

  if (isLocationLoading) {
    return (
      <div className="min-h-screen bg-background">
        <main className="mx-auto max-w-7xl px-4 py-8">
          <SkeletonLoader />
        </main>
      </div>
    )
  }

  if (!location) {
    return (
      <div className="min-h-screen bg-background">
        <main className="mx-auto max-w-7xl px-4 py-8">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Location Not Found</AlertTitle>
            <AlertDescription>
              The location you are looking for does not exist or you do not have permission to view it.
            </AlertDescription>
          </Alert>
        </main>
      </div>
    )
  }

  const pendingCount = edits?.filter(e => e.status === 'Pending').length || 0

  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="mx-auto max-w-7xl px-4 py-4 sm:py-8 space-y-4 sm:space-y-6">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-3 sm:gap-4 min-w-0">
              <Link href="/dashboard" className="p-2 rounded-full hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors shrink-0">
                <ArrowLeft className="h-5 w-5" />
              </Link>
              <div className="min-w-0">
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground flex flex-wrap items-center gap-2 truncate">
                  {location.location_name}
                  {isMicrositeLoading ? (
                    <Badge variant="outline" className="h-5 text-[10px] animate-pulse">Microsite: Loading...</Badge>
                  ) : isMicrositeError || !microsite ? (
                    <Badge variant="outline" className="h-5 text-[10px] bg-muted/40 text-muted-foreground">Microsite: None</Badge>
                  ) : (
                    statusBadgeMap[microsite.status] || (
                      <Badge variant="outline" className="h-5 text-[10px] bg-muted/40 text-muted-foreground">Microsite: None</Badge>
                    )
                  )}
                </h1>
                <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                  <span className="break-words">{formatAddress(location.address)}</span>
                  <span className="text-muted-foreground/30 hidden sm:inline">•</span>
                  <span>{location.primary_category || 'No category'}</span>
                  {Array.isArray(location.additional_categories) && location.additional_categories.length > 0 && (
                    <>
                      <span className="text-muted-foreground/30 hidden sm:inline">•</span>
                      <span className="text-muted-foreground/80">
                        {location.additional_categories
                          .map((c: any) => (typeof c === 'object' && c !== null ? c.displayName : c))
                          .filter(Boolean)
                          .join(', ')}
                      </span>
                    </>
                  )}
                </p>
              </div>
            </div>

            <Button variant="outline" size="sm" disabled={isSyncing} className="gap-2 shrink-0 w-full min-h-[44px] sm:h-9 self-start sm:w-auto sm:min-h-0 sm:self-auto text-xs font-bold shadow-sm hover:shadow hover:-translate-y-0.5 transition-all rounded-xl bg-background/50 backdrop-blur-md" onClick={handleForceSync}>
              <RefreshCw className={`w-3.5 h-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
              {isSyncing ? 'Syncing…' : 'Force Sync'}
            </Button>
          </div>

          {isEditsError && (
            <Alert variant="destructive" className="bg-red-950/20 border-red-500/30 text-red-200">
              <AlertTriangle className="h-4 w-4 text-red-400" />
              <AlertTitle className="text-red-400 font-semibold">Real-time Sync Connection Error</AlertTitle>
              <AlertDescription className="flex items-center justify-between text-xs mt-1">
                <span>Failed to poll changes from the server. Real-time updates are temporarily paused.</span>
                <Button size="sm" variant="outline" onClick={() => refetchEdits()} className="ml-4 h-7 text-xs border-red-500/20 hover:bg-red-500/10 text-red-300">
                  <RefreshCw className="mr-1.5 h-3 w-3" /> Retry Connection
                </Button>
              </AlertDescription>
            </Alert>
          )}

          <div className="glass-panel border-border/40 rounded-2xl p-4 sm:p-8 shadow-sm overflow-hidden flex flex-col mt-4">
            <Tabs 
              value={activeTab} 
              onValueChange={(value) => {
                if (hasUnsavedChanges) {
                  if (confirm("You are currently editing a field. Switching tabs will lose your unsaved typing. Are you sure you want to discard changes?")) {
                    setHasUnsavedChanges(false)
                    setActiveTab(value)
                  }
                } else {
                  setActiveTab(value)
                }
              }} 
              className="w-full flex flex-col"
            >
              <TabsList className="w-full flex flex-wrap justify-start bg-transparent border-b border-border/50 rounded-none p-0 h-auto gap-x-4 gap-y-1 sm:gap-x-6 pb-2 mb-6">
                <TabsTrigger value="overview" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <LayoutDashboard className="w-4 h-4 mr-2" />
                  Overview
                </TabsTrigger>
                <TabsTrigger value="profile" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <Edit3 className="w-4 h-4 mr-2" />
                  Profile Details
                </TabsTrigger>
                <TabsTrigger value="tasks" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0 relative">
                  <ClipboardList className="w-4 h-4 mr-2" />
                  Tasks
                  {pendingCount > 0 && (
                    <Badge variant="destructive" className="ml-2 h-4 px-1.5 py-0 text-[10px] min-w-[1rem] flex items-center justify-center">
                      {pendingCount}
                    </Badge>
                  )}
                </TabsTrigger>
                <TabsTrigger value="activity" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <RefreshCw className="w-4 h-4 mr-2" />
                  Activity Log
                </TabsTrigger>
                <TabsTrigger value="reviews" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <MessageSquare className="w-4 h-4 mr-2" />
                  Reviews
                </TabsTrigger>
                <TabsTrigger value="posts" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <AlertTriangle className="w-4 h-4 mr-2" />
                  Posts
                </TabsTrigger>
                <TabsTrigger value="photos" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <ImageIcon className="w-4 h-4 mr-2" />
                  Photos
                </TabsTrigger>
                <TabsTrigger value="insights" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <TrendingUp className="w-4 h-4 mr-2" />
                  Insights
                </TabsTrigger>
                <TabsTrigger value="search" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <Search className="w-4 h-4 mr-2" />
                  Search
                </TabsTrigger>
                <TabsTrigger value="microsite" className="data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-2 py-3 sm:pb-2 sm:pt-1 text-muted-foreground data-[state=active]:text-primary whitespace-nowrap shrink-0">
                  <Globe className="w-4 h-4 mr-2" />
                  Microsite
                </TabsTrigger>
              </TabsList>
              
              <div className="min-h-[400px]">
                <ErrorBoundary>
                  <TabsContent value="overview" className="mt-0">
                    <OverviewTab locationId={locationId} setActiveTab={setActiveTab} />
                  </TabsContent>
                  <TabsContent value="profile" className="mt-0">
                    <ProfileTab locationId={locationId} setHasUnsavedChanges={setHasUnsavedChanges} />
                  </TabsContent>
                  <TabsContent value="tasks" className="mt-0">
                    <TasksTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="activity" className="mt-0">
                    <ActivityTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="reviews" className="mt-0">
                    <ReviewsTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="posts" className="mt-0">
                    <PostsTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="photos" className="mt-0">
                    <PhotosTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="insights" className="mt-0">
                    <InsightsTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="search" className="mt-0">
                    <SearchIntelligenceTab locationId={locationId} />
                  </TabsContent>
                  <TabsContent value="microsite" className="mt-0">
                    <MicrositeTab locationId={locationId} />
                  </TabsContent>
                </ErrorBoundary>
              </div>
            </Tabs>
          </div>
      </main>
    </div>
  )
}
