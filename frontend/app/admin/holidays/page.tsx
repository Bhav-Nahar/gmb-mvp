'use client'

import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { PartyPopper, Upload, Sparkles, Trash2, Loader2, RefreshCw, AlertTriangle, CheckCircle2 } from 'lucide-react'

interface Holiday {
  id: number
  date: string
  name: string
  category: string
  region?: string | null
  country: string
  source: string
}

// India state subdivision codes the `holidays` package understands (ISO 3166-2 suffix).
const SUBDIVISIONS = ['TN', 'KL', 'KA', 'MH', 'GJ', 'WB', 'PB', 'RJ', 'UP', 'DL', 'TS', 'AP', 'AS', 'BR', 'OD']

export default function AdminHolidaysPage() {
  const [holidays, setHolidays] = useState<Holiday[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)

  const [year, setYear] = useState(new Date().getFullYear())
  const [picked, setPicked] = useState<string[]>(['TN', 'KL', 'KA', 'MH'])
  const fileRef = useRef<HTMLInputElement>(null)

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const d = await api.get<any>('/holidays')
      setHolidays(d.holidays || [])
    } catch (e: any) {
      setError(e.message || 'Failed to load holidays')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const flash = (msg: string) => { setNotice(msg); setTimeout(() => setNotice(''), 6000) }

  const seed = async () => {
    setBusy(true); setError('')
    try {
      const r = await api.post<any>('/holidays/seed', { year, subdivisions: picked })
      flash(`Seeded ${year}: ${r.created} added, ${r.skipped} already present.${r.errors?.length ? ' Errors: ' + r.errors.join('; ') : ''}`)
      await load()
    } catch (e: any) {
      setError(e.message || 'Seed failed')
    } finally {
      setBusy(false)
    }
  }

  const upload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setBusy(true); setError('')
    try {
      const form = new FormData()
      form.append('file', file)
      const r = await api.post<any>('/holidays/import', form)
      flash(`Imported: ${r.created} added, ${r.skipped} skipped.${r.errors?.length ? ' Errors: ' + r.errors.slice(0, 5).join('; ') : ''}`)
      await load()
    } catch (e: any) {
      setError(e.message || 'Import failed')
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const remove = async (id: number) => {
    if (!confirm('Delete this holiday?')) return
    try {
      await api.delete(`/holidays/${id}`)
      setHolidays(hs => hs.filter(h => h.id !== id))
    } catch (e: any) {
      setError(e.message || 'Delete failed')
    }
  }

  const toggleSub = (s: string) =>
    setPicked(p => p.includes(s) ? p.filter(x => x !== s) : [...p, s])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold flex items-center gap-2">
          <PartyPopper className="h-5 w-5 text-primary" /> Holidays &amp; Festivals
        </h1>
        <button onClick={load} className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground">
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 text-red-600 text-sm font-medium rounded-lg">
          <AlertTriangle className="h-4 w-4 shrink-0" /> {error}
        </div>
      )}
      {notice && (
        <div className="flex items-center gap-2 p-3 bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 text-sm font-medium rounded-lg">
          <CheckCircle2 className="h-4 w-4 shrink-0" /> {notice}
        </div>
      )}

      {/* Auto-seed from the open-source library — zero manual data entry */}
      <div className="bg-card border border-border rounded-2xl p-5 space-y-4">
        <div>
          <h2 className="text-sm font-bold flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /> Auto-populate</h2>
          <p className="text-xs text-muted-foreground mt-1">Pulls national + selected state festivals from the open-source holidays database. Safe to re-run — duplicates are skipped.</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs font-bold text-muted-foreground">Year</label>
          <input
            type="number"
            value={year}
            onChange={e => setYear(parseInt(e.target.value) || year)}
            className="w-24 px-3 py-1.5 rounded-lg border border-border bg-background text-sm"
          />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {SUBDIVISIONS.map(s => (
            <button
              key={s}
              onClick={() => toggleSub(s)}
              className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition-colors ${picked.includes(s) ? 'bg-primary/10 text-primary border border-primary/30' : 'bg-muted/40 text-muted-foreground border border-transparent hover:text-foreground'}`}
            >
              {s}
            </button>
          ))}
        </div>
        <button
          onClick={seed}
          disabled={busy}
          className="inline-flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg text-sm font-bold transition-colors disabled:opacity-60 cursor-pointer"
        >
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          Seed {year}
        </button>
      </div>

      {/* CSV override */}
      <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
        <h2 className="text-sm font-bold flex items-center gap-2"><Upload className="h-4 w-4 text-primary" /> Import CSV</h2>
        <p className="text-xs text-muted-foreground">
          Columns: <code className="text-foreground">date,name,category,region</code> — date as <code className="text-foreground">YYYY-MM-DD</code>. Re-uploads are idempotent.
        </p>
        <input ref={fileRef} type="file" accept=".csv" onChange={upload} disabled={busy} className="block text-sm text-muted-foreground file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-primary/10 file:text-primary file:text-xs file:font-bold hover:file:bg-primary/20 file:cursor-pointer" />
      </div>

      {/* List */}
      <div className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="px-5 py-3 border-b border-border flex items-center justify-between">
          <h2 className="text-sm font-bold">All holidays</h2>
          <span className="text-xs text-muted-foreground">{holidays.length} total</span>
        </div>
        {loading ? (
          <div className="p-10 text-center text-sm text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>
        ) : holidays.length === 0 ? (
          <div className="p-10 text-center text-sm text-muted-foreground">No holidays yet. Seed a year or import a CSV above.</div>
        ) : (
          <div className="max-h-[520px] overflow-y-auto divide-y divide-border/60">
            {holidays.map(h => (
              <div key={h.id} className="flex items-center gap-3 px-5 py-2.5 text-sm hover:bg-muted/20">
                <span className="w-24 shrink-0 font-mono text-xs text-muted-foreground">{h.date}</span>
                <span className="flex-1 font-semibold truncate">{h.name}</span>
                {h.region && <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-500/10 text-blue-600">{h.region}</span>}
                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-muted/60 text-muted-foreground">{h.source}</span>
                <button onClick={() => remove(h.id)} className="p-1 text-muted-foreground hover:text-red-500 transition-colors cursor-pointer" title="Delete">
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
