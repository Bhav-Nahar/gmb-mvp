import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** YYYY-MM-DD in the viewer's own timezone. `toISOString()` converts to UTC first,
 *  which in IST (UTC+5:30) reports yesterday's date any time before 05:30 local. */
export function toDateStr(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** `days` before `from`, as a new Date. Never mutates the input. */
export function daysBefore(from: Date, days: number): Date {
  const d = new Date(from)
  d.setDate(d.getDate() - days)
  return d
}
