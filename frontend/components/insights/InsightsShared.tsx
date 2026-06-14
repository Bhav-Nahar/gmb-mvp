'use client'

import { useState } from 'react'
import {
  TrendingUp,
  TrendingDown,
  Minus,
  Smile,
  MessageSquare,
  Frown,
  Clock,
  Heart,
  Globe,
  Phone,
  Navigation,
  Compass,
} from 'lucide-react'

// ---- Shared types (mirrors the /insights/* payloads) -----------------------

export interface InsightsMetricDelta {
  current: number
  prior: number
  percentage_change: number | null
}

export interface OverviewKPIs {
  profile_views: InsightsMetricDelta
  search_impressions: InsightsMetricDelta
  maps_views: InsightsMetricDelta
  phone_calls: InsightsMetricDelta
  website_clicks: InsightsMetricDelta
  direction_requests: InsightsMetricDelta
}

export interface DailyMetricPoint {
  date: string
  profile_views: number
  search_impressions: number
  maps_views: number
  phone_calls: number
  website_clicks: number
  direction_requests: number
  searches_direct: number
  searches_indirect: number
  searches_chain: number
  reviews_received: number
  avg_rating: number | null
}

export interface SentimentBreakdown {
  positive: number
  neutral: number
  negative: number
  positive_percentage: number
  neutral_percentage: number
  negative_percentage: number
  avg_sentiment_score?: number | null
}

export interface SLAMetricsSummary {
  total_reviews: number
  replied_reviews: number
  response_rate: number
  avg_response_time_hours: number | null
}

export interface IssueCategorySummary {
  category: string
  count: number
}

// Static Tailwind classes — dynamic `text-${color}-400` strings get purged in
// production builds, so the KPI icon tints must be spelled out literally.
const KPI_ICON_CLASSES: Record<string, string> = {
  indigo: 'text-indigo-400',
  sky: 'text-sky-400',
  rose: 'text-rose-400',
  emerald: 'text-emerald-400',
  purple: 'text-purple-400',
  amber: 'text-amber-400',
}

// Plottable daily metrics. `color` is a hex value because it feeds SVG strokes
// (which Tailwind classes can't reach) and the legend swatches.
export type TrendMetricKey =
  | 'profile_views'
  | 'search_impressions'
  | 'maps_views'
  | 'phone_calls'
  | 'website_clicks'
  | 'direction_requests'
  | 'reviews_received'

export const TREND_METRICS: { key: TrendMetricKey; label: string; color: string }[] = [
  { key: 'profile_views', label: 'Profile Views', color: '#818cf8' },
  { key: 'search_impressions', label: 'Search Impressions', color: '#38bdf8' },
  { key: 'maps_views', label: 'Maps Views', color: '#fb7185' },
  { key: 'phone_calls', label: 'Phone Calls', color: '#34d399' },
  { key: 'website_clicks', label: 'Website Clicks', color: '#c084fc' },
  { key: 'direction_requests', label: 'Directions', color: '#fbbf24' },
  { key: 'reviews_received', label: 'Reviews', color: '#f472b6' },
]

// ---- KPI card with delta vs prior period -----------------------------------

export function KpiCard({
  title,
  icon: Icon,
  metric,
  color,
}: {
  title: string
  icon: any
  metric: InsightsMetricDelta
  color: string
}) {
  const isPositive = metric.percentage_change !== null && metric.percentage_change > 0
  const isNegative = metric.percentage_change !== null && metric.percentage_change < 0
  const isFlat = metric.percentage_change === 0
  // prior === 0 with current > 0 yields a null delta from the API — that's new
  // activity, not "no data", so label it as such instead of a bare dash.
  const isNew = metric.percentage_change === null && metric.current > 0 && metric.prior === 0

  return (
    <div className="glass-panel p-6 flex flex-col justify-between relative overflow-hidden">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-muted-foreground">{title}</span>
        <div className={`p-2 rounded-lg bg-muted/40 ${KPI_ICON_CLASSES[color] ?? 'text-indigo-400'}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-4 flex items-baseline justify-between">
        <span className="text-3xl font-extrabold text-foreground">
          {metric.current.toLocaleString()}
        </span>
        <div className="flex items-center gap-1">
          {metric.percentage_change !== null ? (
            <span
              className={`flex items-center text-xs font-bold ${
                isPositive ? 'text-emerald-600 dark:text-emerald-400' : isNegative ? 'text-rose-600 dark:text-rose-400' : 'text-gray-600 dark:text-gray-400'
              }`}
            >
              {isFlat ? (
                <Minus className="h-3 w-3 mr-0.5" />
              ) : isPositive ? (
                <TrendingUp className="h-3 w-3 mr-0.5" />
              ) : (
                <TrendingDown className="h-3 w-3 mr-0.5" />
              )}
              {Math.abs(metric.percentage_change).toFixed(1)}%
            </span>
          ) : isNew ? (
            <span className="flex items-center text-xs font-bold text-emerald-600 dark:text-emerald-400">
              <TrendingUp className="h-3 w-3 mr-0.5" />
              New
            </span>
          ) : (
            <span className="text-xs text-gray-500">—</span>
          )}
        </div>
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        vs prior period ({metric.prior.toLocaleString()})
      </div>
    </div>
  )
}

// ---- Multi-metric daily line chart with hover crosshair + tooltip ----------

export function TrendChart({
  trends,
  selected,
}: {
  trends: DailyMetricPoint[]
  selected: Set<TrendMetricKey>
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  if (!trends || trends.length === 0) return null

  const width = 800
  const height = 280
  const paddingLeft = 50
  const paddingRight = 20
  const paddingTop = 20
  const paddingBottom = 40

  const activeMetrics = TREND_METRICS.filter((m) => selected.has(m.key))

  const maxVal = Math.max(
    ...trends.flatMap((t) => activeMetrics.map((m) => t[m.key])),
    10
  )

  const getX = (index: number) => {
    const step = (width - paddingLeft - paddingRight) / (trends.length - 1 || 1)
    return paddingLeft + index * step
  }
  const getY = (val: number) =>
    height - paddingBottom - (val / maxVal) * (height - paddingTop - paddingBottom)

  const buildPath = (key: TrendMetricKey) =>
    trends
      .map((t, i) => `${i === 0 ? 'M' : 'L'} ${getX(i)} ${getY(t[key])}`)
      .join(' ')

  const tickCount = Math.min(trends.length, 6)
  const ticks: number[] = []
  for (let i = 0; i < tickCount; i++) {
    const index = Math.round((i * (trends.length - 1)) / (tickCount - 1 || 1))
    if (trends[index] !== undefined && !ticks.includes(index)) ticks.push(index)
  }

  const hovered = hoverIdx !== null ? trends[hoverIdx] : null

  return (
    <div className="relative w-full h-full">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-full text-muted-foreground"
        onMouseLeave={() => setHoverIdx(null)}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((p, idx) => {
          const val = Math.round(maxVal * p)
          const y = getY(val)
          return (
            <g key={idx}>
              <line
                x1={paddingLeft}
                y1={y}
                x2={width - paddingRight}
                y2={y}
                stroke="currentColor"
                strokeOpacity={0.07}
                strokeWidth={1}
              />
              <text
                x={paddingLeft - 10}
                y={y + 4}
                className="text-[10px] font-medium fill-muted-foreground"
                textAnchor="end"
              >
                {val.toLocaleString()}
              </text>
            </g>
          )
        })}

        {ticks.map((idx) => {
          const t = trends[idx]
          const x = getX(idx)
          const d = new Date(t.date)
          const dateLabel = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          return (
            <text
              key={idx}
              x={x}
              y={height - 15}
              className="text-[10px] font-medium fill-muted-foreground"
              textAnchor="middle"
            >
              {dateLabel}
            </text>
          )
        })}

        {activeMetrics.map((m) => (
          <path
            key={m.key}
            d={buildPath(m.key)}
            fill="none"
            stroke={m.color}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}

        {hoverIdx !== null && (
          <g>
            <line
              x1={getX(hoverIdx)}
              y1={paddingTop}
              x2={getX(hoverIdx)}
              y2={height - paddingBottom}
              stroke="currentColor"
              strokeOpacity={0.2}
              strokeWidth={1}
            />
            {activeMetrics.map((m) => (
              <circle
                key={m.key}
                cx={getX(hoverIdx)}
                cy={getY(trends[hoverIdx][m.key])}
                r={3.5}
                fill={m.color}
                stroke="var(--background, #fff)"
                strokeWidth={1.5}
              />
            ))}
          </g>
        )}

        {trends.map((t, i) => {
          const step = (width - paddingLeft - paddingRight) / (trends.length || 1)
          return (
            <rect
              key={i}
              x={getX(i) - step / 2}
              y={paddingTop}
              width={step}
              height={height - paddingTop - paddingBottom}
              fill="transparent"
              onMouseEnter={() => setHoverIdx(i)}
            />
          )
        })}
      </svg>

      {hovered && (
        <div
          className="pointer-events-none absolute top-2 z-10 rounded-lg border border-border bg-background/95 backdrop-blur px-3 py-2 shadow-lg"
          style={{
            left: `${(getX(hoverIdx!) / width) * 100}%`,
            transform:
              getX(hoverIdx!) > width / 2 ? 'translateX(-105%)' : 'translateX(5%)',
          }}
        >
          <div className="text-[11px] font-bold text-foreground mb-1">
            {new Date(hovered.date).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </div>
          <div className="space-y-0.5">
            {activeMetrics.map((m) => (
              <div key={m.key} className="flex items-center gap-2 text-[11px]">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: m.color }}
                />
                <span className="text-muted-foreground">{m.label}</span>
                <span className="ml-auto font-bold text-foreground">
                  {hovered[m.key].toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---- Clickable legend that doubles as a metric toggle ----------------------

export function TrendLegend({
  selected,
  onToggle,
}: {
  selected: Set<TrendMetricKey>
  onToggle: (key: TrendMetricKey) => void
}) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {TREND_METRICS.map((m) => {
        const active = selected.has(m.key)
        return (
          <button
            key={m.key}
            onClick={() => onToggle(m.key)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-colors ${
              active
                ? 'border-border bg-muted/40 text-foreground'
                : 'border-transparent bg-transparent text-muted-foreground/50 hover:text-muted-foreground'
            }`}
            title={active ? `Hide ${m.label}` : `Show ${m.label}`}
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: active ? m.color : 'currentColor' }}
            />
            {m.label}
          </button>
        )
      })}
    </div>
  )
}

// ---- Conversion quality (derived from KPI totals) --------------------------

export function ConversionQuality({ kpis }: { kpis: OverviewKPIs }) {
  const pv = kpis.profile_views.current
  if (!pv) return null
  const rate = (n: number) => `${((n / pv) * 100).toFixed(1)}%`
  const items = [
    { label: 'Click-through rate', help: 'Website clicks ÷ profile views', value: rate(kpis.website_clicks.current), icon: Globe },
    { label: 'Call conversion', help: 'Phone calls ÷ profile views', value: rate(kpis.phone_calls.current), icon: Phone },
    { label: 'Directions conversion', help: 'Directions ÷ profile views', value: rate(kpis.direction_requests.current), icon: Navigation },
  ]
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {items.map((it) => (
        <div key={it.label} className="glass-panel p-4 flex items-center gap-3" title={it.help}>
          <div className="p-2 rounded-lg bg-muted/40 text-indigo-400">
            <it.icon className="h-4 w-4" />
          </div>
          <div>
            <div className="text-lg font-extrabold text-foreground leading-none">{it.value}</div>
            <div className="text-[11px] text-muted-foreground mt-1">{it.label}</div>
          </div>
        </div>
      ))}
    </div>
  )
}

// ---- Search composition (direct vs discovery vs branded) -------------------

export function SearchComposition({ trends }: { trends: DailyMetricPoint[] }) {
  const direct = trends.reduce((s, t) => s + (t.searches_direct || 0), 0)
  const indirect = trends.reduce((s, t) => s + (t.searches_indirect || 0), 0)
  const chain = trends.reduce((s, t) => s + (t.searches_chain || 0), 0)
  const totalSearches = direct + indirect + chain
  if (totalSearches === 0) return null
  const segs = [
    { label: 'Direct', help: 'Searched your business name or address', value: direct, color: '#818cf8' },
    { label: 'Discovery', help: 'Searched a category, product, or service', value: indirect, color: '#34d399' },
    { label: 'Branded', help: 'Searched a related brand or chain', value: chain, color: '#fbbf24' },
  ]
  return (
    <div className="glass-panel p-6">
      <div className="flex items-center gap-1.5 mb-1">
        <Compass className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
        <h3 className="text-base font-bold text-foreground">How Customers Found You</h3>
      </div>
      <p className="text-xs text-muted-foreground mb-4">Search composition across the selected period</p>
      <div className="w-full h-3 rounded-full overflow-hidden flex bg-muted/40">
        {segs.map((s) => (
          <div
            key={s.label}
            style={{ width: `${(s.value / totalSearches) * 100}%`, backgroundColor: s.color }}
            title={`${s.label}: ${s.value.toLocaleString()} (${((s.value / totalSearches) * 100).toFixed(1)}%)`}
          />
        ))}
      </div>
      <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
        {segs.map((s) => (
          <div key={s.label} className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: s.color }} />
              <span className="text-xs font-semibold text-foreground">{s.label}</span>
              <span className="text-xs text-muted-foreground ml-auto font-bold">
                {((s.value / totalSearches) * 100).toFixed(0)}%
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground mt-0.5">{s.help}</span>
            <span className="text-[11px] text-muted-foreground/70">{s.value.toLocaleString()} searches</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ---- Reputation grid: sentiment / SLA / themes -----------------------------

export function ReputationGrid({
  sentiment,
  sla,
  topIssues,
  scopeLabel,
}: {
  sentiment: SentimentBreakdown
  sla: SLAMetricsSummary
  topIssues: IssueCategorySummary[]
  scopeLabel: string
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Customer Sentiment */}
      <div className="glass-panel p-6 flex flex-col justify-between">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Smile className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            Customer Sentiment
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · positive vs negative tags</p>
        </div>
        <div className="my-4 space-y-3">
          <div className="flex justify-between items-center text-xs">
            <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1"><Smile className="h-3.5 w-3.5" />Positive</span>
            <span className="text-foreground font-bold">{sentiment.positive_percentage.toFixed(0)}%</span>
          </div>
          <div className="flex justify-between items-center text-xs">
            <span className="text-gray-600 dark:text-gray-400 font-semibold flex items-center gap-1"><MessageSquare className="h-3.5 w-3.5" />Neutral</span>
            <span className="text-foreground font-bold">{sentiment.neutral_percentage.toFixed(0)}%</span>
          </div>
          <div className="flex justify-between items-center text-xs">
            <span className="text-rose-600 dark:text-rose-400 font-semibold flex items-center gap-1"><Frown className="h-3.5 w-3.5" />Negative</span>
            <span className="text-foreground font-bold">{sentiment.negative_percentage.toFixed(0)}%</span>
          </div>
        </div>
        <div className="w-full h-2 rounded-full overflow-hidden flex bg-muted/40">
          <div className="bg-emerald-400" style={{ width: `${sentiment.positive_percentage}%` }} />
          <div className="bg-gray-400" style={{ width: `${sentiment.neutral_percentage}%` }} />
          <div className="bg-rose-400" style={{ width: `${sentiment.negative_percentage}%` }} />
        </div>
        {sentiment.avg_sentiment_score !== null && sentiment.avg_sentiment_score !== undefined && (
          <div className="mt-3 flex items-center justify-between text-[11px]">
            <span className="text-muted-foreground">Sentiment score</span>
            <span className={`font-bold ${sentiment.avg_sentiment_score > 0.1 ? 'text-emerald-600 dark:text-emerald-400' : sentiment.avg_sentiment_score < -0.1 ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'}`}>
              {sentiment.avg_sentiment_score > 0 ? '+' : ''}{sentiment.avg_sentiment_score.toFixed(2)} <span className="text-muted-foreground font-normal">/ 1.0</span>
            </span>
          </div>
        )}
      </div>

      {/* SLA Summary */}
      <div className="glass-panel p-6 flex flex-col justify-between">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            SLA Performance
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · reply speeds and statuses</p>
        </div>
        <div className="my-4 grid grid-cols-2 gap-4">
          <div className="bg-muted/30 p-3 rounded-lg text-center border border-border/30">
            <span className="text-[10px] uppercase font-bold text-muted-foreground block">Response Rate</span>
            <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 block">
              {sla.response_rate.toFixed(0)}%
            </span>
          </div>
          <div className="bg-muted/30 p-3 rounded-lg text-center border border-border/30">
            <span className="text-[10px] uppercase font-bold text-muted-foreground block">Avg Reply Time</span>
            <span className="text-lg font-extrabold text-indigo-600 dark:text-indigo-400 mt-1 block">
              {sla.avg_response_time_hours !== null ? `${sla.avg_response_time_hours.toFixed(1)}h` : '—'}
            </span>
          </div>
        </div>
        <div className="text-[10px] text-muted-foreground text-center">
          Total Reviews: {sla.total_reviews} • Replied: {sla.replied_reviews}
        </div>
      </div>

      {/* Customer Themes */}
      <div className="glass-panel p-6">
        <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
          <Heart className="h-4 w-4 text-rose-600 dark:text-rose-400" />
          Customer Themes
        </h4>
        <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · recurring issue categories</p>
        <div className="mt-4 space-y-2 max-h-36 overflow-y-auto">
          {topIssues.length > 0 ? (
            topIssues.map((item, idx) => (
              <div key={idx} className="flex justify-between items-center text-xs border-b border-border/20 pb-1.5">
                <span className="text-muted-foreground font-semibold capitalize">{item.category}</span>
                <span className="text-foreground font-bold">{item.count} tags</span>
              </div>
            ))
          ) : (
            <span className="text-xs text-muted-foreground block text-center py-6">No recurring themes found.</span>
          )}
        </div>
      </div>
    </div>
  )
}

// ---- Period comparison table -----------------------------------------------

export function PeriodComparison({ kpis }: { kpis: OverviewKPIs }) {
  const rows = [
    { name: 'Profile Views', m: kpis.profile_views },
    { name: 'Search Impressions', m: kpis.search_impressions },
    { name: 'Maps Views', m: kpis.maps_views },
    { name: 'Phone Calls', m: kpis.phone_calls },
    { name: 'Website Clicks', m: kpis.website_clicks },
    { name: 'Directions Requests', m: kpis.direction_requests },
  ]
  return (
    <div className="glass-panel p-6">
      <h3 className="text-base font-bold text-foreground mb-4">Period Comparison</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-border text-muted-foreground font-semibold">
              <th className="pb-3">Metric</th>
              <th className="pb-3 text-right">Current Period</th>
              <th className="pb-3 text-right">Prior Period</th>
              <th className="pb-3 text-right">Delta</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-medium">
            {rows.map((row, idx) => {
              const delta = row.m.percentage_change
              const isPos = delta !== null && delta > 0
              const isNeg = delta !== null && delta < 0
              return (
                <tr key={idx} className="hover:bg-muted/10 transition-colors">
                  <td className="py-3 text-foreground">{row.name}</td>
                  <td className="py-3 text-right text-muted-foreground">{row.m.current.toLocaleString()}</td>
                  <td className="py-3 text-right text-muted-foreground">{row.m.prior.toLocaleString()}</td>
                  <td className={`py-3 text-right font-bold ${isPos ? 'text-emerald-600 dark:text-emerald-400' : isNeg ? 'text-rose-600 dark:text-rose-400' : 'text-gray-600 dark:text-gray-400'}`}>
                    {delta !== null ? `${isPos ? '+' : ''}${delta.toFixed(1)}%` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
