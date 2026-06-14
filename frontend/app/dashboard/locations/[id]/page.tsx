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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { AlertCircle, ArrowLeft, RefreshCw, AlertTriangle, MessageSquare, Edit3, ClipboardList, TrendingUp, LayoutDashboard, Search, ImageIcon } from "lucide-react"
import Link from "next/link"
import { SkeletonLoader } from "./components/SkeletonLoader"
import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Badge } from "@/components/ui/badge"

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
  
  const { location, isLocationLoading, edits, isEditsError, refetchEdits } = useLocationWorkspace(locationId)
  const [activeTab, setActiveTab] = useState("overview")
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  
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
                <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground flex items-center gap-2 truncate">
                  {location.location_name}
                </h1>
                <p className="text-muted-foreground mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-sm">
                  <span className="break-words">{formatAddress(location.address)}</span>
                  <span className="text-muted-foreground/30 hidden sm:inline">•</span>
                  <span>{location.primary_category || 'No category'}</span>
                </p>
              </div>
            </div>

            <Button variant="outline" size="sm" className="gap-2 shrink-0 w-full min-h-[44px] self-start sm:w-auto sm:min-h-0 sm:self-auto" onClick={() => {/* Future implementation for force sync */}}>
              <RefreshCw className="w-4 h-4" />
              Force Sync
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

          <div className="bg-card border border-border rounded-xl p-4 sm:p-6 shadow-sm overflow-hidden flex flex-col">
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
              <TabsList className="w-full flex justify-start bg-transparent border-b border-border/50 rounded-none p-0 h-auto gap-4 sm:gap-6 pb-2 mb-6 overflow-x-auto overflow-y-hidden [&::-webkit-scrollbar]:hidden [-ms-overflow-style:none] [scrollbar-width:none]">
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
                </ErrorBoundary>
              </div>
            </Tabs>
          </div>
      </main>
    </div>
  )
}
