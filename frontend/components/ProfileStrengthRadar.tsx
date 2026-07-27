"use client"

import { ResponsiveContainer, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, Tooltip } from "recharts"

// Maps health-score breakdown keys to short axis labels.
export const DIMENSION_LABELS: Record<string, string> = {
  profile_completeness: "Profile",
  reviews_rating: "Reviews",
  response_rate: "Response",
  post_activity: "Posts",
  photos_media: "Photos",
  description: "Description",
  ranking: "Ranking",
  traffic: "Traffic",
  sentiment: "Sentiment",
  website: "Website",
}

export interface RadarPoint {
  label: string
  // 0–10 scale (screenshot-style score)
  value: number
  detail?: string
}

/** Converts a health-score breakdown ({key: {score, max_score, detail?}}) into radar points on a 0–10 scale. */
export function breakdownToRadar(breakdown: Record<string, { score: number; max_score: number; detail?: string | null } | null | undefined>): RadarPoint[] {
  return Object.entries(DIMENSION_LABELS).flatMap(([key, label]) => {
    const dim = breakdown[key]
    if (!dim || !dim.max_score) return []
    return [{ label, value: Math.round((dim.score / dim.max_score) * 100) / 10, detail: dim.detail ?? undefined }]
  })
}

const PURPLE = "#7c3aed"

export function ProfileStrengthRadar({ data, height = 240 }: { data: RadarPoint[]; height?: number }) {
  if (data.length < 3) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data} outerRadius="75%">
        <PolarGrid stroke="currentColor" strokeOpacity={0.15} />
        <PolarAngleAxis dataKey="label" tick={{ fontSize: 11, fill: "currentColor", opacity: 0.7 }} />
        <PolarRadiusAxis domain={[0, 10]} tick={false} axisLine={false} />
        <Tooltip
          formatter={(v) => [`${v} / 10`, "Strength"]}
          contentStyle={{ borderRadius: 8, fontSize: 12 }}
        />
        <Radar dataKey="value" stroke={PURPLE} fill={PURPLE} fillOpacity={0.35} strokeWidth={2} isAnimationActive={false} />
      </RadarChart>
    </ResponsiveContainer>
  )
}
