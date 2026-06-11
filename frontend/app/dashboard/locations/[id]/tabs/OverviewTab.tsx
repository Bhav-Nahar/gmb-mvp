import React from "react"
import { AlertCircle, CheckCircle2, ChevronRight, MessageSquare, ClipboardList, MapPin } from "lucide-react"

interface OverviewTabProps {
  locationId: number;
  setActiveTab: (tab: string) => void;
}

export function OverviewTab({ locationId, setActiveTab }: OverviewTabProps) {
  // Placeholder metrics
  const healthScore = 78;
  const unrepliedReviews = 3;
  const pendingTasks = 2;

  return (
    <div className="space-y-6">
      {/* Top KPI row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Health Score Card */}
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col items-center justify-center text-center">
          <h3 className="text-sm font-medium text-muted-foreground mb-4">Profile Health Score</h3>
          <div className="relative w-32 h-32 flex items-center justify-center">
            {/* SVG Circle Progress */}
            <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-muted/20"
                d="M18 2.0845
                  a 15.9155 15.9155 0 0 1 0 31.831
                  a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
              />
              <path
                className="text-primary"
                strokeDasharray={`${healthScore}, 100`}
                d="M18 2.0845
                  a 15.9155 15.9155 0 0 1 0 31.831
                  a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
                strokeLinecap="round"
              />
            </svg>
            <div className="absolute flex flex-col items-center justify-center">
              <span className="text-3xl font-bold text-foreground">{healthScore}</span>
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide">Good</span>
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-4">We will calculate actual score later.</p>
        </div>

        {/* Action Required Panel */}
        <div className="md:col-span-2 bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col">
          <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500" />
            Action Required
          </h3>
          
          <div className="space-y-3 flex-1">
            {/* Action Item 1 */}
            <button 
              onClick={() => setActiveTab('reviews')}
              className="w-full flex items-center justify-between p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-muted/30 transition-colors text-left"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-100 text-indigo-600 rounded-md">
                  <MessageSquare className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">Unreplied Reviews</div>
                  <div className="text-xs text-muted-foreground">You have {unrepliedReviews} reviews awaiting response.</div>
                </div>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </button>

            {/* Action Item 2 */}
            <button 
              onClick={() => setActiveTab('tasks')}
              className="w-full flex items-center justify-between p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-muted/30 transition-colors text-left"
            >
              <div className="flex items-center gap-3">
                <div className="p-2 bg-amber-100 text-amber-600 rounded-md">
                  <ClipboardList className="h-4 w-4" />
                </div>
                <div>
                  <div className="text-sm font-semibold text-foreground">Pending Profile Tasks</div>
                  <div className="text-xs text-muted-foreground">Complete {pendingTasks} tasks to improve local SEO.</div>
                </div>
              </div>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
