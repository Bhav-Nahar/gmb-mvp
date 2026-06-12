import React from "react"
import { AlertCircle, CheckCircle2, ChevronRight, MessageSquare, ClipboardList, MapPin, Sparkles, Activity } from "lucide-react"
import { useLocationWorkspace } from "@/hooks/useLocationWorkspace"

interface OverviewTabProps {
  locationId: number;
  setActiveTab: (tab: string) => void;
}

export function OverviewTab({ locationId, setActiveTab }: OverviewTabProps) {
  const { healthScore, isHealthScoreLoading, isHealthScoreError, refetchHealthScore } = useLocationWorkspace(locationId);

  // Fallbacks if data is still loading or missing
  const score = healthScore?.score ?? 0;
  const label = healthScore?.label || (isHealthScoreError ? "Unavailable" : "Calculating...");
  const recommendations = healthScore?.recommendations || [];
  const breakdown = healthScore?.breakdown;

  // Determine colors based on score label
  let ringColor = "text-muted/20";
  let textColor = "text-foreground";
  if (healthScore) {
    if (score >= 75) {
      ringColor = "text-emerald-500";
      textColor = "text-emerald-500";
    } else if (score >= 60) {
      ringColor = "text-amber-500";
      textColor = "text-amber-500";
    } else {
      ringColor = "text-red-500";
      textColor = "text-red-500";
    }
  }

  return (
    <div className="space-y-6">
      {/* Top KPI row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Health Score Card */}
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col items-center justify-center text-center">
          <h3 className="text-sm font-medium text-muted-foreground mb-4 flex items-center gap-2">
            <Activity className="w-4 h-4" />
            Profile Health
          </h3>
          {isHealthScoreLoading ? (
            <div className="w-32 h-32 flex items-center justify-center">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary"></div>
            </div>
          ) : (
            <div className="relative w-32 h-32 flex items-center justify-center">
              {/* SVG Circle Progress */}
              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                <path
                  className="text-muted/10"
                  d="M18 2.0845
                    a 15.9155 15.9155 0 0 1 0 31.831
                    a 15.9155 15.9155 0 0 1 0 -31.831"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="3"
                />
                <path
                  className={`${ringColor} transition-all duration-1000 ease-out`}
                  strokeDasharray={`${score}, 100`}
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
                <span className={`text-4xl font-bold tracking-tighter ${textColor}`}>{healthScore ? score : "—"}</span>
                <span className="text-[10px] text-muted-foreground uppercase tracking-wider font-semibold mt-1">{label}</span>
              </div>
            </div>
          )}
          {healthScore && (
            <p className="text-xs text-muted-foreground mt-4 italic">
              Last checked: {new Date(healthScore.calculated_at).toLocaleDateString()}
            </p>
          )}
        </div>

        {/* Action Required Panel (Recommendations) */}
        <div className="md:col-span-2 bg-card border border-border rounded-xl p-6 shadow-sm flex flex-col">
          <h3 className="text-sm font-medium text-foreground mb-4 flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" />
            Top Recommendations
          </h3>
          
          <div className="space-y-3 flex-1 overflow-y-auto pr-1">
            {isHealthScoreLoading ? (
               <div className="animate-pulse space-y-3">
                 {[1, 2, 3].map(i => (
                   <div key={i} className="h-16 bg-muted/50 rounded-lg"></div>
                 ))}
               </div>
            ) : isHealthScoreError || !healthScore ? (
               <div className="flex flex-col items-center justify-center h-full text-center p-4">
                 <AlertCircle className="h-8 w-8 text-amber-500 mb-2" />
                 <p className="text-sm font-semibold text-foreground">Health score unavailable</p>
                 <p className="text-xs text-muted-foreground">We couldn&apos;t calculate this profile&apos;s health right now.</p>
                 <button
                   onClick={() => refetchHealthScore()}
                   className="mt-3 text-xs font-medium text-primary hover:underline"
                 >
                   Retry
                 </button>
               </div>
            ) : recommendations.length === 0 ? (
               <div className="flex flex-col items-center justify-center h-full text-center p-4">
                 <CheckCircle2 className="h-8 w-8 text-emerald-500 mb-2" />
                 <p className="text-sm font-semibold text-emerald-600">You&apos;re doing great!</p>
                 <p className="text-xs text-muted-foreground">No critical actions required at this moment.</p>
               </div>
            ) : (
              recommendations.map((rec, idx) => (
                <button 
                  key={idx}
                  onClick={() => setActiveTab(rec.target_tab)}
                  className="w-full flex items-center justify-between p-3 rounded-lg border border-border hover:border-primary/50 hover:bg-muted/30 transition-colors text-left group"
                >
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 text-primary rounded-md group-hover:scale-110 transition-transform">
                      {rec.target_tab === 'reviews' ? <MessageSquare className="h-4 w-4" /> :
                       rec.target_tab === 'posts' ? <ClipboardList className="h-4 w-4" /> :
                       <MapPin className="h-4 w-4" />}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-foreground flex items-center gap-2">
                        {rec.title}
                        <span className="text-[10px] bg-emerald-500/10 text-emerald-600 px-1.5 py-0.5 rounded font-bold">
                          +{rec.potential_gain} pts
                        </span>
                      </div>
                      <div className="text-xs text-muted-foreground mt-0.5">{rec.description}</div>
                    </div>
                  </div>
                  <ChevronRight className="h-4 w-4 text-muted-foreground opacity-50 group-hover:opacity-100 group-hover:translate-x-1 transition-all" />
                </button>
              ))
            )}
          </div>
        </div>

      </div>

      {/* Breakdown Section */}
      {breakdown && (
        <div className="bg-card border border-border rounded-xl p-6 shadow-sm">
          <h3 className="text-sm font-medium text-foreground mb-4">Score Breakdown</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 flex flex-col items-center text-center">
              <span className="text-xs font-semibold text-muted-foreground mb-2">Profile</span>
              <span className="text-lg font-bold text-foreground">{breakdown.profile_completeness.score} <span className="text-xs text-muted-foreground font-normal">/ {breakdown.profile_completeness.max_score}</span></span>
            </div>
            
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 flex flex-col items-center text-center">
              <span className="text-xs font-semibold text-muted-foreground mb-2">Reviews</span>
              <span className="text-lg font-bold text-foreground">{breakdown.reviews_rating.score} <span className="text-xs text-muted-foreground font-normal">/ {breakdown.reviews_rating.max_score}</span></span>
            </div>
            
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 flex flex-col items-center text-center">
              <span className="text-xs font-semibold text-muted-foreground mb-2">Response</span>
              <span className="text-lg font-bold text-foreground">{breakdown.response_rate.score} <span className="text-xs text-muted-foreground font-normal">/ {breakdown.response_rate.max_score}</span></span>
            </div>
            
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 flex flex-col items-center text-center">
              <span className="text-xs font-semibold text-muted-foreground mb-2">Posts</span>
              <span className="text-lg font-bold text-foreground">{breakdown.post_activity.score} <span className="text-xs text-muted-foreground font-normal">/ {breakdown.post_activity.max_score}</span></span>
            </div>
            
            <div className="p-4 rounded-lg bg-muted/30 border border-border/50 flex flex-col items-center text-center">
              <span className="text-xs font-semibold text-muted-foreground mb-2">Photos</span>
              <span className="text-lg font-bold text-foreground">{breakdown.photos_media.score} <span className="text-xs text-muted-foreground font-normal">/ {breakdown.photos_media.max_score}</span></span>
            </div>

          </div>
        </div>
      )}

    </div>
  )
}
