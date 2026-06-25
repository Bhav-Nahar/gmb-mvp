import React, { useState, useEffect, useRef } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Inbox, Mail, Phone, Check, Bell, BellRing } from "lucide-react"
import { toast } from "sonner"
import { enablePush, disablePush, isPushSubscribed, pushSupported } from "@/lib/push"

interface Lead {
  id: number
  name: string
  phone?: string | null
  email?: string | null
  message?: string | null
  status: string
  created_at: string
}

function timeAgo(s: string) {
  const d = new Date(s), diff = Math.floor((Date.now() - d.getTime()) / 60000)
  if (diff < 1) return "just now"
  if (diff < 60) return `${diff}m ago`
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`
  return d.toLocaleDateString()
}

const statusStyle: Record<string, string> = {
  new: "bg-indigo-500/10 text-indigo-500 border-indigo-500/20",
  contacted: "bg-amber-500/10 text-amber-500 border-amber-500/20",
  closed: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20",
}

export function LeadsPanel({ locationId }: { locationId: number }) {
  const { isAdmin } = useAuth()
  const qc = useQueryClient()
  const [emailInput, setEmailInput] = useState("")

  const { data: leads = [], isLoading } = useQuery<Lead[]>({
    queryKey: ["leads", locationId],
    queryFn: () => api.get(`/locations/${locationId}/leads`),
    refetchInterval: 30000, // live in-app updates while the dashboard is open
  })

  // In-app toast when a new lead arrives (count grows) while the tab is open.
  const prevCount = useRef<number | null>(null)
  useEffect(() => {
    if (prevCount.current !== null && leads.length > prevCount.current) {
      toast.success("New lead received!")
    }
    prevCount.current = leads.length
  }, [leads.length])

  const newCount = leads.filter((l) => l.status === "new").length

  // Push toggle state: 'unsupported' | 'denied' | 'on' | 'off'
  const [pushState, setPushState] = useState<string>("loading")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    (async () => {
      if (!pushSupported()) return setPushState("unsupported")
      if (Notification.permission === "denied") return setPushState("denied")
      setPushState((await isPushSubscribed()) ? "on" : "off")
    })()
  }, [])

  const handleTogglePush = async () => {
    setBusy(true)
    try {
      if (pushState === "on") {
        await disablePush()
        setPushState("off")
        toast.success("Notifications turned off for this device.")
      } else {
        await enablePush()
        setPushState("on")
        toast.success("Notifications enabled for this device.")
      }
    } catch (e: any) {
      toast.error(e?.message || "Could not update notifications")
    } finally {
      setBusy(false)
    }
  }

  const { data: emailData } = useQuery<{ lead_email: string | null }>({
    queryKey: ["lead-email", locationId],
    queryFn: () => api.get(`/locations/${locationId}/lead-email`),
  })

  useEffect(() => { if (emailData) setEmailInput(emailData.lead_email || "") }, [emailData])

  const saveEmail = useMutation({
    mutationFn: () => api.put(`/locations/${locationId}/lead-email`, { lead_email: emailInput }),
    onSuccess: () => { toast.success("Notification email saved"); qc.invalidateQueries({ queryKey: ["lead-email", locationId] }) },
    onError: (e: any) => toast.error(e?.message || "Failed to save"),
  })

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      api.patch(`/locations/${locationId}/leads/${id}?status_value=${status}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leads", locationId] }),
    onError: (e: any) => toast.error(e?.message || "Failed to update"),
  })

  return (
    <div className="bg-card border border-border rounded-xl p-6 shadow-sm space-y-5">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-2">
          <Inbox className="w-5 h-5 text-primary" />
          <h3 className="text-lg font-bold text-foreground">Leads</h3>
          <span className="text-xs text-muted-foreground">({leads.length})</span>
          {newCount > 0 && (
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-indigo-600 text-white">{newCount} new</span>
          )}
        </div>
        {pushState === "denied" && (
          <span className="text-xs text-muted-foreground">Notifications blocked in browser settings</span>
        )}
        {pushState === "on" && (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
              <BellRing className="w-3.5 h-3.5" /> Notifications on
            </span>
            <Button size="sm" variant="outline" onClick={handleTogglePush} disabled={busy} className="gap-1.5">
              {busy ? "…" : "Turn off"}
            </Button>
          </div>
        )}
        {pushState === "off" && (
          <Button size="sm" variant="outline" onClick={handleTogglePush} disabled={busy} className="gap-1.5">
            <Bell className="w-3.5 h-3.5" /> {busy ? "Enabling…" : "Enable notifications"}
          </Button>
        )}
      </div>

      {/* Notification email setting */}
      <div className="bg-muted/30 border border-border/60 rounded-lg p-4 space-y-2">
        <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <Mail className="w-3.5 h-3.5" /> Notification email (in addition to admins)
        </label>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={emailInput}
            onChange={(e) => setEmailInput(e.target.value)}
            disabled={!isAdmin}
            placeholder="store-inbox@example.com"
            className="flex-1 rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          {isAdmin && (
            <Button onClick={() => saveEmail.mutate()} disabled={saveEmail.isPending} className="shrink-0">
              {saveEmail.isPending ? "Saving…" : "Save"}
            </Button>
          )}
        </div>
      </div>

      {/* Leads list */}
      {isLoading ? (
        <p className="text-sm text-muted-foreground py-6 text-center">Loading leads…</p>
      ) : leads.length === 0 ? (
        <div className="text-center py-10 text-muted-foreground">
          <Inbox className="w-8 h-8 mx-auto mb-2 opacity-40" />
          <p className="text-sm">No leads yet. They&apos;ll appear here when visitors submit the microsite form.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {leads.map((l) => (
            <div key={l.id} className="border border-border rounded-lg p-4 hover:bg-muted/20 transition-colors">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-foreground">{l.name}</span>
                    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-semibold ${statusStyle[l.status] || statusStyle.new}`}>{l.status}</span>
                    <span className="text-xs text-muted-foreground">{timeAgo(l.created_at)}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5 text-sm text-muted-foreground">
                    {l.phone && <a href={`tel:${l.phone}`} className="flex items-center gap-1 hover:text-foreground"><Phone className="w-3.5 h-3.5" />{l.phone}</a>}
                    {l.email && <a href={`mailto:${l.email}`} className="flex items-center gap-1 hover:text-foreground"><Mail className="w-3.5 h-3.5" />{l.email}</a>}
                  </div>
                  {l.message && <p className="text-sm text-foreground/80 mt-2 leading-relaxed">{l.message}</p>}
                </div>
                {isAdmin && l.status !== "closed" && (
                  <div className="flex flex-col gap-1.5 shrink-0">
                    {l.status === "new" && (
                      <Button size="sm" variant="outline" onClick={() => setStatus.mutate({ id: l.id, status: "contacted" })}>Mark contacted</Button>
                    )}
                    <Button size="sm" variant="outline" className="text-emerald-600" onClick={() => setStatus.mutate({ id: l.id, status: "closed" })}>
                      <Check className="w-3.5 h-3.5 mr-1" /> Close
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
