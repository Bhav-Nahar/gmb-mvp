'use client'

import { useMemo, useState } from 'react'
import {
  startOfMonth, endOfMonth, startOfWeek, endOfWeek, addDays, addMonths,
  format, isSameMonth, isSameDay, isToday, parseISO,
} from 'date-fns'
import { ChevronLeft, ChevronRight, Sparkles, PartyPopper, Plus } from 'lucide-react'

export interface CalendarCampaign {
  id: number
  name: string
  status: string
  scheduled_at?: string | null
}

export interface CalendarHoliday {
  id: number
  date: string        // YYYY-MM-DD
  name: string
  category: string    // festival | holiday | observance
  region?: string | null
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const dayKey = (d: Date) => format(d, 'yyyy-MM-dd')

export default function PostsCalendar({
  campaigns,
  holidays,
  onPickDate,
  onPickHoliday,
  onSelectCampaign,
}: {
  campaigns: CalendarCampaign[]
  holidays: CalendarHoliday[]
  onPickDate: (isoDate: string) => void
  onPickHoliday: (holiday: CalendarHoliday) => void
  onSelectCampaign: (id: number) => void
}) {
  const [cursor, setCursor] = useState<Date>(startOfMonth(new Date()))

  // Bucket campaigns + holidays by day once per render.
  const campaignsByDay = useMemo(() => {
    const m = new Map<string, CalendarCampaign[]>()
    for (const c of campaigns) {
      if (!c.scheduled_at) continue
      const k = dayKey(parseISO(c.scheduled_at))
      ;(m.get(k) ?? m.set(k, []).get(k)!).push(c)
    }
    return m
  }, [campaigns])

  const holidaysByDay = useMemo(() => {
    // The same holiday (e.g. Independence Day) is stored once per region, so
    // collapse by name within a day — keep one chip, drop the duplicates.
    const m = new Map<string, CalendarHoliday[]>()
    for (const h of holidays) {
      const list = m.get(h.date) ?? m.set(h.date, []).get(h.date)!
      if (!list.some(x => x.name === h.name)) list.push(h)
    }
    return m
  }, [holidays])

  // Full weeks covering the visible month.
  const days = useMemo(() => {
    const start = startOfWeek(startOfMonth(cursor))
    const end = endOfWeek(endOfMonth(cursor))
    const out: Date[] = []
    for (let d = start; d <= end; d = addDays(d, 1)) out.push(d)
    return out
  }, [cursor])

  const today = new Date()
  today.setHours(0, 0, 0, 0)

  return (
    <div className="bg-card shadow-sm border border-border rounded-2xl p-4 sm:p-6">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h3 className="text-lg font-bold text-foreground">{format(cursor, 'MMMM yyyy')}</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setCursor(c => addMonths(c, -1))}
            className="p-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors cursor-pointer"
            aria-label="Previous month"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => setCursor(startOfMonth(new Date()))}
            className="px-3 py-2 rounded-lg border border-border text-xs font-bold text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors cursor-pointer"
          >
            Today
          </button>
          <button
            onClick={() => setCursor(c => addMonths(c, 1))}
            className="p-2 rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors cursor-pointer"
            aria-label="Next month"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Weekday header */}
      <div className="grid grid-cols-7 gap-px mb-px">
        {WEEKDAYS.map(d => (
          <div key={d} className="text-center text-[10px] font-bold uppercase tracking-wider text-muted-foreground/70 py-2">
            {d}
          </div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-px bg-border/40 rounded-lg overflow-hidden">
        {days.map(day => {
          const k = dayKey(day)
          const inMonth = isSameMonth(day, cursor)
          const isPast = day < today
          const dayCampaigns = campaignsByDay.get(k) ?? []
          const dayHolidays = holidaysByDay.get(k) ?? []
          const todayCell = isToday(day)

          return (
            <div
              key={k}
              className={`group relative min-h-[92px] sm:min-h-[104px] p-1.5 flex flex-col gap-1 text-left transition-colors ${
                inMonth ? 'bg-card' : 'bg-muted/30'
              } ${isPast ? 'opacity-60' : ''}`}
            >
              {/* Day number + add affordance */}
              <div className="flex items-center justify-between">
                <span
                  className={`inline-flex items-center justify-center h-6 w-6 text-xs font-bold rounded-full ${
                    todayCell ? 'bg-primary text-primary-foreground' : inMonth ? 'text-foreground' : 'text-muted-foreground/50'
                  }`}
                >
                  {format(day, 'd')}
                </span>
                {!isPast && (
                  <button
                    onClick={() => onPickDate(k)}
                    className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-0.5 rounded text-muted-foreground hover:text-primary transition-opacity cursor-pointer"
                    title="Schedule a post on this day"
                    aria-label={`Schedule a post on ${format(day, 'PP')}`}
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {/* Holiday chips */}
              {dayHolidays.map(h => (
                <button
                  key={h.id}
                  onClick={() => onPickHoliday(h)}
                  title={`Plan a post for ${h.name}`}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-700 dark:text-amber-300 hover:bg-amber-500/25 transition-colors truncate cursor-pointer"
                >
                  <PartyPopper className="h-2.5 w-2.5 shrink-0" />
                  <span className="truncate">{h.name}</span>
                </button>
              ))}

              {/* Scheduled campaign chips */}
              {dayCampaigns.map(c => (
                <button
                  key={c.id}
                  onClick={() => onSelectCampaign(c.id)}
                  title={`${c.name} · ${format(parseISO(c.scheduled_at!), 'p')}`}
                  className="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-700 dark:text-purple-300 hover:bg-purple-500/25 transition-colors truncate cursor-pointer"
                >
                  <Sparkles className="h-2.5 w-2.5 shrink-0" />
                  <span className="truncate">{c.name}</span>
                </button>
              ))}
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded bg-purple-500/40" /> Scheduled post
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded bg-amber-500/40" /> Holiday — click to plan a post
        </span>
        <span className="hidden sm:flex items-center gap-1.5 ml-auto">
          <Plus className="h-3 w-3" /> Hover a day to plan a post
        </span>
      </div>
    </div>
  )
}
