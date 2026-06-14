'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { api } from '@/lib/api'
import { FileClock, CheckCircle2, XCircle, RefreshCw, ChevronLeft, ChevronRight, ArrowLeft } from 'lucide-react'

interface SyncLog {
  id: number
  location_id: number | null
  status: string
  error_message?: string
  run_type: string
  created_at: string
}

interface SyncLogResponse {
  items: SyncLog[]
  total: number
  page: number
  size: number
}

const PAGE_SIZE = 20

export default function ActivityLogsPage() {
  const [syncLogs, setSyncLogs] = useState<SyncLog[]>([])
  const [loading, setLoading] = useState(true)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)

  const loadSyncLogs = useCallback(async (page: number) => {
    setLoading(true)
    try {
      const data = await api.get<SyncLogResponse>(`/locations/sync-logs?page=${page}&size=${PAGE_SIZE}`)
      setSyncLogs(data.items)
      setTotal(data.total)
      setTotalPages(Math.max(1, Math.ceil(data.total / data.size)))
      setCurrentPage(data.page)
    } catch (e: any) {
      console.error('Failed to load sync logs:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadSyncLogs(1) }, [loadSyncLogs])

  return (
    <div className="w-full font-sans">
      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link href="/dashboard/settings" className="p-2 rounded-full hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors">
              <ArrowLeft className="h-5 w-5" />
            </Link>
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground flex items-center gap-2">
                <FileClock className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
                Activity Logs
              </h1>
              <p className="mt-1 text-sm font-medium text-muted-foreground">
                History of backend synchronization tasks across all locations{total > 0 ? ` · ${total} entries` : ''}.
              </p>
            </div>
          </div>
          <button
            onClick={() => loadSyncLogs(currentPage)}
            disabled={loading}
            className="flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:bg-indigo-500/10 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
            title="Refresh"
          >
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loading ? (
          <div className="flex h-40 w-full items-center justify-center rounded-2xl border border-border bg-muted/10">
            <RefreshCw className="h-5 w-5 animate-spin text-indigo-500" />
          </div>
        ) : syncLogs.length === 0 ? (
          <div className="text-center p-12 border border-border rounded-2xl bg-muted/10 text-sm text-muted-foreground">
            No synchronization logs generated yet.
          </div>
        ) : (
          <div className="space-y-4">
            {/* Mobile stacked cards */}
            <div className="space-y-3 sm:hidden">
              {syncLogs.map((log) => (
                <div key={log.id} className="rounded-2xl border border-border bg-card shadow-sm p-4 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex px-2 py-1 rounded-md text-xs font-bold border ${
                      log.run_type === 'Scheduled'
                        ? 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30'
                        : 'bg-purple-100 text-purple-800 border-purple-300 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30'
                    }`}>
                      {log.run_type}
                    </span>
                    {log.status === 'Success' ? (
                      <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400 font-bold text-xs uppercase">
                        <CheckCircle2 className="h-3.5 w-3.5" /> Success
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-400 font-bold text-xs uppercase">
                        <XCircle className="h-3.5 w-3.5" /> Failed
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{new Date(log.created_at).toLocaleString()}</p>
                  <p className="text-muted-foreground/90 font-mono text-xs leading-normal break-all">
                    {log.error_message || 'N/A'}
                  </p>
                </div>
              ))}
            </div>

            {/* Desktop table */}
            <div className="hidden sm:block overflow-x-auto rounded-2xl border border-border bg-card shadow-sm">
              <table className="hidden sm:table w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-border/70 text-[10px] uppercase font-bold tracking-wider text-muted-foreground bg-muted/20">
                    <th className="px-4 sm:px-6 py-3.5">Timestamp</th>
                    <th className="px-4 sm:px-6 py-3.5">Run Type</th>
                    <th className="px-4 sm:px-6 py-3.5">Status</th>
                    <th className="px-4 sm:px-6 py-3.5">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/40 text-xs font-medium">
                  {syncLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-muted/20 transition-colors">
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-muted-foreground">{new Date(log.created_at).toLocaleString()}</td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex px-2 py-0.5 rounded-md text-[10px] font-bold border ${
                          log.run_type === 'Scheduled'
                            ? 'bg-blue-100 text-blue-800 border-blue-300 dark:bg-blue-500/15 dark:text-blue-300 dark:border-blue-500/30'
                            : 'bg-purple-100 text-purple-800 border-purple-300 dark:bg-purple-500/15 dark:text-purple-300 dark:border-purple-500/30'
                        }`}>
                          {log.run_type}
                        </span>
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        {log.status === 'Success' ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400 font-bold text-[10px] uppercase">
                            <CheckCircle2 className="h-3.5 w-3.5" /> Success
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-red-700 dark:text-red-400 font-bold text-[10px] uppercase">
                            <XCircle className="h-3.5 w-3.5" /> Failed
                          </span>
                        )}
                      </td>
                      <td className="px-4 sm:px-6 py-4 text-muted-foreground/90 font-mono text-[11px] leading-normal break-all max-w-md">
                        {log.error_message || 'N/A'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-1">
                <span className="text-xs text-muted-foreground">Page {currentPage} of {totalPages}</span>
                <div className="flex gap-2">
                  <button onClick={() => loadSyncLogs(currentPage - 1)} disabled={currentPage === 1 || loading} className="flex items-center gap-1 px-3 h-11 sm:h-auto sm:py-1.5 rounded-lg border border-border bg-muted/20 text-xs font-bold text-foreground hover:bg-muted/40 disabled:opacity-50 transition-colors">
                    <ChevronLeft className="h-4 w-4" /> Previous
                  </button>
                  <button onClick={() => loadSyncLogs(currentPage + 1)} disabled={currentPage === totalPages || loading} className="flex items-center gap-1 px-3 h-11 sm:h-auto sm:py-1.5 rounded-lg border border-border bg-muted/20 text-xs font-bold text-foreground hover:bg-muted/40 disabled:opacity-50 transition-colors">
                    Next <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
