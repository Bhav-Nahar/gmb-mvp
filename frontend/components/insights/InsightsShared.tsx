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
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell
} from 'recharts'
import { AnimatedNumber } from '@/components/ui/AnimatedNumber'

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

export interface PlatformDeviceBreakdown {
  desktop_search: number
  mobile_search: number
  desktop_maps: number
  mobile_maps: number
}

export interface ReputationVelocity {
  avg_rating: number | null
  rated_location_count: number
  review_velocity_per_day: InsightsMetricDelta
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
  yellow: 'text-yellow-400',
  pink: 'text-pink-400',
  // Golden filled star — `fill` is inherited by the SVG, so the Star renders solid gold.
  gold: 'text-amber-400 fill-amber-400',
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
  formatValue,
  valueSuffix,
  subtitle,
  hideDelta = false,
}: {
  title: string
  icon: any
  metric: InsightsMetricDelta
  color: string
  // Optional formatter for the displayed value (defaults to integer locale string).
  formatValue?: (n: number) => string
  // Small unit rendered after the value, e.g. "/day".
  valueSuffix?: string
  // Overrides the "vs prior period (...)" footer.
  subtitle?: string
  // Hide the delta badge + footer entirely (for standing metrics like rating).
  hideDelta?: boolean
}) {
  const fmt = formatValue ?? ((n: number) => n.toLocaleString())
  const isPositive = metric.percentage_change !== null && metric.percentage_change > 0
  const isNegative = metric.percentage_change !== null && metric.percentage_change < 0
  const isFlat = metric.percentage_change === 0
  // prior === 0 with current > 0 yields a null delta from the API — that's new
  // activity, not "no data", so label it as such instead of a bare dash.
  const isNew = metric.percentage_change === null && metric.current > 0 && metric.prior === 0

  return (
    <div className="glass-panel border-border/40 rounded-2xl p-6 flex flex-col justify-between relative overflow-hidden shadow-sm group hover:shadow-md transition-all">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-muted-foreground">{title}</span>
        <div className={`p-2 rounded-lg bg-muted/40 ${KPI_ICON_CLASSES[color] ?? 'text-indigo-400'}`}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
      <div className="mt-4 flex items-baseline justify-between">
        <span className="text-3xl font-extrabold text-foreground">
          {fmt(metric.current)}
          {valueSuffix && <span className="text-base font-bold text-muted-foreground ml-0.5">{valueSuffix}</span>}
        </span>
        {!hideDelta && (
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
        )}
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        {subtitle ?? (hideDelta ? ' ' : `vs prior period (${fmt(metric.prior)}${valueSuffix ?? ''})`)}
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
  if (!trends || trends.length === 0) return null

  const activeMetrics = TREND_METRICS.filter((m) => selected.has(m.key))

  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-lg border border-border bg-background/95 backdrop-blur px-3 py-2 shadow-lg">
          <div className="text-[11px] font-bold text-foreground mb-1">
            {new Date(label).toLocaleDateString(undefined, {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </div>
          <div className="space-y-0.5">
            {payload.map((entry: any, index: number) => (
              <div key={index} className="flex items-center gap-2 text-[11px]">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ backgroundColor: entry.color }}
                />
                <span className="text-muted-foreground">{entry.name}</span>
                <span className="ml-auto font-bold text-foreground">
                  {entry.value.toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )
    }
    return null
  }

  const formatXAxis = (tickItem: string) => {
    return new Date(tickItem).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  }

  return (
    <div className="w-full h-full relative" style={{ minHeight: '280px' }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={trends}
          margin={{ top: 20, right: 20, left: -20, bottom: 0 }}
        >
          <defs>
            {activeMetrics.map((m) => (
              <linearGradient key={`color-${m.key}`} id={`color-${m.key}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={m.color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={m.color} stopOpacity={0} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="currentColor" strokeOpacity={0.07} />
          <XAxis 
            dataKey="date" 
            tickFormatter={formatXAxis} 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: 'var(--muted-foreground)', fontSize: 10, fontWeight: 500 }}
            dy={10}
            minTickGap={30}
          />
          <YAxis 
            axisLine={false} 
            tickLine={false} 
            tick={{ fill: 'var(--muted-foreground)', fontSize: 10, fontWeight: 500 }}
            tickFormatter={(val) => val.toLocaleString()}
          />
          <RechartsTooltip content={<CustomTooltip />} cursor={{ stroke: 'currentColor', strokeOpacity: 0.2, strokeWidth: 1 }} />
          {activeMetrics.map((m) => (
            <Area
              key={m.key}
              type="monotone"
              dataKey={m.key}
              name={m.label}
              stroke={m.color}
              strokeWidth={2.5}
              fillOpacity={1}
              fill={`url(#color-${m.key})`}
              activeDot={{ r: 4, strokeWidth: 1.5, stroke: 'var(--background)' }}
              animationDuration={1500}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
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
        <div key={it.label} className="glass-panel border-border/40 rounded-2xl p-5 flex items-center gap-4 shadow-sm group hover:-translate-y-0.5 transition-all" title={it.help}>
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
    <div className="glass-panel border-border/40 rounded-2xl p-6 shadow-sm">
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
  const pieData = [
    { name: 'Positive', value: sentiment.positive_percentage, color: '#34d399' },
    { name: 'Neutral', value: sentiment.neutral_percentage, color: '#9ca3af' },
    { name: 'Negative', value: sentiment.negative_percentage, color: '#fb7185' }
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      {/* Customer Sentiment */}
      <div className="glass-panel border-border/40 rounded-2xl p-6 flex flex-col justify-between shadow-sm relative overflow-hidden group hover:shadow-lg transition-all duration-300">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Smile className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
            Customer Sentiment
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · tone analysis</p>
        </div>

        <div className="flex flex-col items-center justify-center flex-1 py-4">
          <div className="relative w-40 h-24 overflow-hidden mb-2">
            <ResponsiveContainer width="100%" height="200%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="100%"
                  startAngle={180}
                  endAngle={0}
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={2}
                  dataKey="value"
                  stroke="none"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute bottom-0 left-0 right-0 text-center flex flex-col">
              <span className="text-2xl font-extrabold text-foreground">
                {sentiment.positive_percentage.toFixed(0)}%
              </span>
              <span className="text-[10px] font-bold text-emerald-500">Positive</span>
            </div>
          </div>
        </div>

        {sentiment.avg_sentiment_score !== null && sentiment.avg_sentiment_score !== undefined && (
          <div className="mt-2 flex items-center justify-between text-xs sm:text-[11px] pt-3 border-t border-border/40">
            <span className="text-muted-foreground">Avg Sentiment</span>
            <span className={`font-bold ${sentiment.avg_sentiment_score > 0.1 ? 'text-emerald-600 dark:text-emerald-400' : sentiment.avg_sentiment_score < -0.1 ? 'text-rose-600 dark:text-rose-400' : 'text-muted-foreground'}`}>
              {sentiment.avg_sentiment_score > 0 ? '+' : ''}{sentiment.avg_sentiment_score.toFixed(2)} <span className="text-muted-foreground font-normal">/ 1.0</span>
            </span>
          </div>
        )}
      </div>

      {/* SLA Summary */}
      <div className="glass-panel border-border/40 rounded-2xl p-6 flex flex-col justify-between shadow-sm group hover:shadow-lg transition-all duration-300">
        <div>
          <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
            <Clock className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            Response SLA
          </h4>
          <p className="text-[10px] text-muted-foreground mt-0.5">{scopeLabel} · engagement speed</p>
        </div>
        <div className="my-6 grid grid-cols-2 gap-4">
          <div className="bg-gradient-to-br from-indigo-500/10 to-transparent p-4 rounded-xl text-center border border-indigo-500/20">
            <span className="text-[10px] uppercase font-bold text-indigo-600/80 dark:text-indigo-400/80 block mb-1">Response Rate</span>
            <span className="text-2xl font-extrabold text-indigo-600 dark:text-indigo-400 flex items-center justify-center gap-1">
              <AnimatedNumber value={sla.response_rate} />%
            </span>
          </div>
          <div className="bg-gradient-to-br from-indigo-500/10 to-transparent p-4 rounded-xl text-center border border-indigo-500/20">
            <span className="text-[10px] uppercase font-bold text-indigo-600/80 dark:text-indigo-400/80 block mb-1">Avg Reply Time</span>
            <span className="text-2xl font-extrabold text-indigo-600 dark:text-indigo-400 flex items-center justify-center gap-1">
              {sla.avg_response_time_hours !== null ? <AnimatedNumber value={sla.avg_response_time_hours} /> : '—'}
              {sla.avg_response_time_hours !== null && <span className="text-sm">h</span>}
            </span>
          </div>
        </div>
        <div className="text-[11px] text-muted-foreground flex justify-between items-center pt-3 border-t border-border/40 font-medium">
          <span>Total Reviews: <strong>{sla.total_reviews}</strong></span>
          <span>Replied: <strong>{sla.replied_reviews}</strong></span>
        </div>
      </div>

      {/* Customer Themes */}
      <div className="glass-panel border-border/40 rounded-2xl p-6 shadow-sm group hover:shadow-lg transition-all duration-300">
        <h4 className="text-sm font-bold text-foreground flex items-center gap-1.5">
          <Heart className="h-4 w-4 text-rose-600 dark:text-rose-400" />
          Key Themes
        </h4>
        <p className="text-[10px] text-muted-foreground mt-0.5 mb-4">{scopeLabel} · trending topics</p>
        <div className="flex flex-wrap gap-2 max-h-40 overflow-y-auto pr-2 custom-scrollbar">
          {topIssues.length > 0 ? (
            topIssues.map((item, idx) => (
              <div
                key={idx}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/40 border border-border/50 text-xs hover:bg-muted/60 hover:border-border transition-colors cursor-default"
              >
                <span className="font-semibold text-foreground capitalize">{item.category}</span>
                <span className="text-[10px] bg-background px-1.5 py-0.5 rounded text-muted-foreground font-bold">{item.count}</span>
              </div>
            ))
          ) : (
            <div className="w-full h-full flex flex-col items-center justify-center py-6 text-muted-foreground">
              <MessageSquare className="h-6 w-6 mb-2 opacity-20" />
              <span className="text-xs">No recurring themes found.</span>
            </div>
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
    <div className="glass-panel border-border/40 rounded-2xl p-6 shadow-sm overflow-hidden">
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

// ---- Platform & Device impressions (donut chart, custom SVG) ----------------

const PLATFORM_DEVICE_SLICES: { key: keyof PlatformDeviceBreakdown; label: string; color: string }[] = [
  { key: 'mobile_search', label: 'Mobile Search', color: '#38bdf8' },
  { key: 'desktop_search', label: 'Desktop Search', color: '#6366f1' },
  { key: 'mobile_maps', label: 'Mobile Maps', color: '#fb7185' },
  { key: 'desktop_maps', label: 'Desktop Maps', color: '#f59e0b' },
]

// Polar → cartesian on a unit circle, with 0° at 12 o'clock going clockwise.
function polar(cx: number, cy: number, r: number, fraction: number) {
  const angle = fraction * 2 * Math.PI - Math.PI / 2
  return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
}

export function PlatformDeviceImpressions({ data }: { data: PlatformDeviceBreakdown }) {
  const [active, setActive] = useState<keyof PlatformDeviceBreakdown | null>(null)

  const slices = PLATFORM_DEVICE_SLICES.map((s) => ({ ...s, value: Math.max(0, data[s.key] || 0) }))
  const total = slices.reduce((sum, s) => sum + s.value, 0)

  // ViewBox geometry — keep R + STROKE/2 comfortably inside the box so the ring
  // is never clipped (the previous version drew outside the viewBox).
  const SIZE = 180
  const C = SIZE / 2
  const R = 66
  const STROKE = 24
  const GAP = 0.012 // fractional gap between slices for visual separation

  const drawn = slices.filter((s) => s.value > 0)
  let cursor = 0
  const arcs = drawn.map((s) => {
    const frac = s.value / total
    const start = cursor
    const end = cursor + frac
    cursor = end
    // Inset each slice slightly so neighbours don't touch (skip when only one slice).
    const gap = drawn.length > 1 ? GAP / 2 : 0
    const a = polar(C, C, R, start + gap)
    const b = polar(C, C, R, end - gap)
    const largeArc = end - start - 2 * gap > 0.5 ? 1 : 0
    const d =
      frac >= 0.999
        ? `M ${C - R} ${C} A ${R} ${R} 0 1 1 ${C - R - 0.01} ${C}`
        : `M ${a.x} ${a.y} A ${R} ${R} 0 ${largeArc} 1 ${b.x} ${b.y}`
    return { ...s, d, frac }
  })

  const activeSlice = active ? slices.find((s) => s.key === active) : null

  return (
    <div className="glass-panel border-border/40 rounded-2xl p-4 sm:p-5 shadow-sm">
      <div className="flex items-center gap-2 mb-1">
        <Compass className="h-4 w-4 text-indigo-400 shrink-0" />
        <h3 className="text-sm font-bold text-foreground">Platform &amp; Device Impressions</h3>
      </div>
      <p className="text-[11px] text-muted-foreground mb-4">
        How customers found this profile, split by Search vs Maps and Desktop vs Mobile.
      </p>

      {total === 0 ? (
        <div className="flex items-center justify-center h-[160px] text-xs text-muted-foreground">
          No impression data for this period yet.
        </div>
      ) : (
        <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center sm:gap-7">
          {/* Donut — fixed, centered, never stretched */}
          <div
            className="relative mx-auto shrink-0"
            style={{ width: SIZE, height: SIZE, maxWidth: '70vw' }}
          >
            <svg
              viewBox={`0 0 ${SIZE} ${SIZE}`}
              className="w-full h-full -rotate-0"
              onMouseLeave={() => setActive(null)}
            >
              {/* Track ring */}
              <circle cx={C} cy={C} r={R} fill="none" strokeWidth={STROKE} className="stroke-muted/25" />
              {arcs.map((arc) => {
                const isActive = active === arc.key
                const dim = active !== null && !isActive
                return (
                  <path
                    key={arc.key}
                    d={arc.d}
                    fill="none"
                    stroke={arc.color}
                    strokeWidth={isActive ? STROKE + 6 : STROKE}
                    strokeLinecap="round"
                    className="cursor-pointer transition-all duration-200"
                    style={{ opacity: dim ? 0.3 : 1 }}
                    onMouseEnter={() => setActive(arc.key)}
                    onClick={() => setActive((prev) => (prev === arc.key ? null : arc.key))}
                  />
                )
              })}
            </svg>

            {/* Center label — reflects the hovered/selected slice, else the total */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none px-6 text-center">
              {activeSlice ? (
                <>
                  <span className="text-base sm:text-lg font-extrabold text-foreground leading-none tabular-nums">
                    {((activeSlice.value / total) * 100).toFixed(1)}%
                  </span>
                  <span className="text-[10px] font-medium mt-1" style={{ color: activeSlice.color }}>
                    {activeSlice.label}
                  </span>
                  <span className="text-[10px] text-muted-foreground tabular-nums">
                    {activeSlice.value.toLocaleString()}
                  </span>
                </>
              ) : (
                <>
                  <span className="text-lg sm:text-xl font-extrabold text-foreground leading-none tabular-nums">
                    {total.toLocaleString()}
                  </span>
                  <span className="text-[10px] text-muted-foreground mt-0.5">total impressions</span>
                </>
              )}
            </div>
          </div>

          {/* Legend — interactive rows, full width on mobile */}
          <ul className="w-full flex-1 space-y-1">
            {slices.map((s) => {
              const pct = total ? (s.value / total) * 100 : 0
              const isActive = active === s.key
              const dim = active !== null && !isActive
              return (
                <li key={s.key}>
                  <button
                    type="button"
                    onMouseEnter={() => setActive(s.key)}
                    onMouseLeave={() => setActive(null)}
                    onClick={() => setActive((prev) => (prev === s.key ? null : s.key))}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-xs transition-colors ${
                      isActive ? 'bg-muted/50' : 'hover:bg-muted/30'
                    }`}
                    style={{ opacity: dim ? 0.5 : 1 }}
                  >
                    <span className="h-3 w-3 rounded-full shrink-0 ring-2 ring-transparent" style={{ backgroundColor: s.color }} />
                    <span className="text-foreground/90 flex-1 text-left font-medium">{s.label}</span>
                    <span className="font-semibold text-foreground tabular-nums">{s.value.toLocaleString()}</span>
                    <span className="text-muted-foreground/70 tabular-nums w-12 text-right">{pct.toFixed(1)}%</span>
                  </button>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}
