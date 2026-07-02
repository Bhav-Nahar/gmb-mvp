'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
import { beginGoogleLogin } from '@/lib/oauth'
import type { CtaLocation } from '@/lib/analytics'
import {
  RefreshCw,
  ArrowRight,
  Check,
  Star,
  MapPin,
  TrendingUp,
  MessageSquare,
  Calendar,
  Shield,
  Activity,
  Users,
  Menu,
  X,
  BarChart2,
  Sparkles,
  Building,
  Clock,
  ChevronDown,
  Plug,
  LayoutDashboard,
  ShieldCheck,
  KeyRound,
  CreditCard,
  XCircle,
  Trophy,
  Search,
  Map,
  Globe,
  Utensils,
  Stethoscope,
  ShoppingBag,
  Scissors,
  Home,
  Car,
} from 'lucide-react'
import { useQuote } from '@/hooks/useBilling'
import { INDIA_PATH, INDIA_PINS } from './indiaMap'

// ── Small client-side animation helpers (no deps; IntersectionObserver + rAF) ──

// Reveal: fades + slides children in the first time they scroll into view.
function Reveal({ children, delay = 0, className = '' }: { children: React.ReactNode; delay?: number; className?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setShown(true)
          io.disconnect()
        }
      },
      { threshold: 0.15 }
    )
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ease-out ${shown ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}

// Official WhatsApp glyph (lucide has no brand icon). Used on the Enterprise CTA
// and the floating chat button so both show the real logo, not a generic bubble.
function WhatsAppIcon({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`${className} fill-current`} aria-hidden>
      <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.999-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z" />
    </svg>
  )
}

// CountUp: animates 0 → value once visible.
function CountUp({ value, decimals = 0, prefix = '', suffix = '' }: { value: number; decimals?: number; prefix?: string; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const [n, setN] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return
      io.disconnect()
      const dur = 1400
      let start: number | null = null
      const tick = (t: number) => {
        if (start === null) start = t
        const p = Math.min((t - start) / dur, 1)
        const eased = 1 - Math.pow(1 - p, 3)
        setN(value * eased)
        if (p < 1) requestAnimationFrame(tick)
      }
      requestAnimationFrame(tick)
    }, { threshold: 0.5 })
    io.observe(el)
    return () => io.disconnect()
  }, [value])
  return (
    <span ref={ref}>
      {prefix}
      {n.toLocaleString('en-IN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}
      {suffix}
    </span>
  )
}

// Fixed 7x7 geo-grid of ranks (center = the business, lower is better).
const RANK_GRID = [
  [12, 9, 7, 6, 8, 11, 15],
  [8, 5, 4, 3, 4, 7, 10],
  [6, 3, 2, 1, 2, 4, 8],
  [5, 2, 1, 1, 1, 3, 7],
  [6, 3, 2, 1, 2, 5, 9],
  [9, 5, 4, 3, 5, 8, 13],
  [13, 10, 7, 6, 9, 12, 18],
].flat()
const CENTER_INDEX = 24 // middle cell of the 7x7 grid

function rankColor(r: number) {
  if (r <= 3) return 'bg-emerald-500 text-white border-emerald-300'
  if (r <= 7) return 'bg-amber-500 text-white border-amber-300'
  if (r <= 10) return 'bg-orange-500 text-white border-orange-300'
  return 'bg-rose-500 text-white border-rose-300'
}

// City pins projected from real lon/lat (see indiaMap.ts). The target is zoomed into.
const PINS = INDIA_PINS as { x: number; y: number; city: string; target?: boolean }[]
const TARGET = PINS.find((p) => p.target)!

// Official India outline (inline single path, no asset download).
function MapBackdrop() {
  return (
    <svg viewBox="0 0 1024 1024" className="absolute inset-0 h-full w-full" aria-hidden>
      <defs>
        <pattern id="dots" width="40" height="40" patternUnits="userSpaceOnUse">
          <circle cx="6" cy="6" r="3" className="fill-foreground/[0.06]" />
        </pattern>
      </defs>
      <rect width="1024" height="1024" fill="url(#dots)" />
      <path d={INDIA_PATH} className="fill-primary/10 stroke-primary/40" strokeWidth="4" />
    </svg>
  )
}

// RankMapReveal: pins drop across the map, then the view zooms into one location
// and the street-level rank heatmap fills in. Loops. Pure CSS transforms + one
// interval, no deps, no images, so it does not affect load time.
function RankMapReveal() {
  const [zoomed, setZoomed] = useState(false)
  const [revealed, setRevealed] = useState(0)

  useEffect(() => {
    let mounted = true
    const timers: ReturnType<typeof setTimeout>[] = []
    const wait = (ms: number) => new Promise<void>((r) => { timers.push(setTimeout(r, ms)) })
    const revealGrid = () =>
      new Promise<void>((resolve) => {
        let i = 0
        const id = setInterval(() => {
          i += 1
          if (!mounted) { clearInterval(id); return }
          if (i > RANK_GRID.length) { clearInterval(id); resolve(); return }
          setRevealed(i)
        }, 38)
        timers.push(id as unknown as ReturnType<typeof setTimeout>)
      })

    // Respect reduced-motion: show the final heatmap, skip the loop.
    if (typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setZoomed(true)
      setRevealed(RANK_GRID.length)
      return () => { mounted = false }
    }

    const loop = async () => {
      while (mounted) {
        setZoomed(false)
        setRevealed(0)
        await wait(2800)
        if (!mounted) break
        setZoomed(true)
        await wait(900)
        if (!mounted) break
        await revealGrid()
        await wait(3200)
        if (!mounted) break
      }
    }
    loop()
    return () => { mounted = false; timers.forEach((t) => clearTimeout(t)) }
  }, [])

  return (
    <div className="relative rounded-2xl border border-border bg-card p-5 shadow-lg">
      <div className="mb-1 flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-bold text-foreground">
          <Map className="h-4 w-4 text-primary" />
          {zoomed ? 'Local Rank Heatmap' : 'Your Locations'}
        </div>
        <span className="rounded-full border border-primary/20 bg-primary/5 px-2 py-0.5 font-mono text-[10px] text-primary">
          &quot;burger near me&quot;
        </span>
      </div>
      <p className="mb-4 text-[11px] text-muted-foreground">
        Pin every location, then zoom into one to see exactly where you rank on Google, street by street.
      </p>

      <div className="relative aspect-square w-full overflow-hidden rounded-lg border border-border/60 bg-muted/20">
        {/* MAP PHASE */}
        <div
          className="absolute inset-0 transition-all duration-[900ms] ease-in-out"
          style={{ transformOrigin: `${TARGET.x}% ${TARGET.y}%`, transform: zoomed ? 'scale(3.4)' : 'scale(1)', opacity: zoomed ? 0 : 1 }}
        >
          <MapBackdrop />
          {PINS.map((p, i) => (
            <div key={i} className="absolute -translate-x-1/2 -translate-y-full" style={{ left: `${p.x}%`, top: `${p.y}%` }}>
              <span className={`absolute left-1/2 top-full h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full ${p.target ? 'bg-emerald-500/30' : 'bg-primary/30'} animate-ping`} />
              <MapPin className={`relative h-5 w-5 ${p.target ? 'fill-emerald-500/20 text-emerald-600' : 'fill-primary/20 text-primary'}`} />
            </div>
          ))}
        </div>

        {/* HEATMAP PHASE */}
        <div
          className="absolute inset-0 flex items-center justify-center p-3 transition-all duration-[900ms] ease-in-out"
          style={{ transform: zoomed ? 'scale(1)' : 'scale(0.82)', opacity: zoomed ? 1 : 0 }}
        >
          <div className="grid w-full grid-cols-7 gap-1.5">
            {RANK_GRID.map((r, i) => (
              <div
                key={i}
                className={`relative flex aspect-square items-center justify-center rounded-md border text-[11px] font-extrabold transition-all duration-300 ${
                  zoomed && i < revealed ? `${rankColor(r)} scale-100 opacity-100` : 'scale-90 border-border/40 bg-muted/30 opacity-40'
                }`}
              >
                {i === CENTER_INDEX && zoomed && (
                  <span className="absolute -top-2 left-1/2 z-10 -translate-x-1/2 whitespace-nowrap rounded-full border border-foreground/20 bg-background px-1.5 py-0.5 text-[8px] font-bold uppercase tracking-wide text-foreground shadow-sm">
                    Your store
                  </span>
                )}
                {zoomed && i < revealed ? r : ''}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between text-[10px] font-semibold text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" /> Top 3</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-500" /> 4-7</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-orange-500" /> 8-10</span>
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-rose-500" /> 11+</span>
      </div>
    </div>
  )
}

// RankTrend: a distinct visual for the deep-dive section (not the heatmap again).
// Bars = number of keywords ranking in the local top 3, climbing week over week.
const TREND = [4, 6, 5, 9, 11, 14, 13, 18, 21, 24]
function RankTrend() {
  const max = Math.max(...TREND)
  const [grow, setGrow] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setGrow(true); io.disconnect() } }, { threshold: 0.4 })
    io.observe(el)
    return () => io.disconnect()
  }, [])
  return (
    <div ref={ref} className="rounded-2xl border border-border bg-card p-6 shadow-lg">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs font-bold text-foreground">Keywords ranking in the local top 3</span>
        <span className="font-mono text-[10px] text-muted-foreground">Last 10 weeks</span>
      </div>
      <p className="mb-5 text-[11px] text-muted-foreground">More green tiles every week as you optimize.</p>
      <div className="flex h-44 items-end gap-2 border-b border-border pb-px">
        {TREND.map((v, i) => (
          <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
            <span className="text-[9px] font-bold tabular-nums text-muted-foreground">{grow ? v : ''}</span>
            <div
              className="w-full rounded-t bg-gradient-to-t from-primary/40 to-primary transition-[height] duration-700 ease-out"
              style={{ height: grow ? `${(v / max) * 88}%` : '0%', transitionDelay: `${i * 60}ms` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-2 flex justify-between text-[10px] text-muted-foreground"><span>Week 1</span><span>Week 10</span></div>
    </div>
  )
}

// AuditPreview: static mockup of the audit result the paid hero promises — a Health
// Score + branch-wise scores + concrete findings. No animation loop; it's a product
// snapshot a business owner reads instantly, not the technical rank heatmap.
function AuditPreview() {
  const branches = [
    { name: 'Andheri West', score: 82, label: 'Good', tone: 'text-emerald-600 bg-emerald-500/10' },
    { name: 'Bandra Kurla', score: 61, label: 'Needs work', tone: 'text-amber-600 bg-amber-500/10' },
    { name: 'Powai', score: 48, label: 'At risk', tone: 'text-rose-600 bg-rose-500/10' },
  ]
  const findings = [
    { icon: Search, text: '8 missing services across locations' },
    { icon: MessageSquare, text: '23 reviews waiting for a reply' },
    { icon: Star, text: '2 branches rated below 4.0' },
  ]
  return (
    <div className="rounded-2xl border border-border bg-card p-6 shadow-lg">
      <div className="mb-4 flex items-center justify-between">
        <span className="flex items-center gap-2 text-xs font-bold text-foreground"><Building className="h-4 w-4 text-primary" />Your GBP audit</span>
        <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">3 locations</span>
      </div>
      {/* Health score ring */}
      <div className="mb-5 flex items-center gap-4">
        <div className="relative h-20 w-20 shrink-0 rounded-full" style={{ background: 'conic-gradient(hsl(var(--primary)) 234deg, hsl(var(--muted)) 0)' }}>
          <div className="absolute inset-[7px] flex flex-col items-center justify-center rounded-full bg-card">
            <span className="text-xl font-extrabold leading-none text-foreground">65</span>
            <span className="text-[8px] font-semibold text-muted-foreground">/ 100</span>
          </div>
        </div>
        <div>
          <p className="text-sm font-bold text-foreground">Avg Health Score</p>
          <p className="text-xs text-muted-foreground">Room to grow. Here is what to fix first.</p>
        </div>
      </div>
      {/* Branch-wise scores */}
      <div className="space-y-2">
        {branches.map((b) => (
          <div key={b.name} className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
            <span className="flex items-center gap-2 text-xs font-semibold text-foreground"><MapPin className="h-3.5 w-3.5 text-muted-foreground" />{b.name}</span>
            <span className="flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${b.tone}`}>{b.label}</span>
              <span className="w-6 text-right text-xs font-extrabold tabular-nums text-foreground">{b.score}</span>
            </span>
          </div>
        ))}
      </div>
      {/* Findings */}
      <div className="mt-4 space-y-2 border-t border-border pt-4">
        {findings.map((f) => (
          <div key={f.text} className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <f.icon className="h-4 w-4 shrink-0 text-primary" />{f.text}
          </div>
        ))}
      </div>
    </div>
  )
}

// Mini leaderboard used in the bento grid.
const LEADERS = [
  { rank: 1, name: 'Downtown Hub', score: 94, up: true },
  { rank: 2, name: 'Westside Plaza', score: 89, up: true },
  { rank: 3, name: 'Eastside Diner', score: 81, up: false },
  { rank: 4, name: 'Airport Kiosk', score: 76, up: true },
]

const BUILT_FOR = [
  { name: 'SEO Agencies', icon: TrendingUp },
  { name: 'Franchises', icon: Building },
  { name: 'Multi-Location Brands', icon: MapPin },
  { name: 'Restaurant Groups', icon: Activity },
  { name: 'Retail Chains', icon: Users },
]

// variant 'paid' = the ad-campaign landing page (/google-business-profile-management):
// same login/trial funnel, audit-framed hero copy + CTA. dataLayer already tags each
// event with page_path, so paid conversions separate from the homepage on their own.
export default function HomeClient({ variant = 'home' }: { variant?: 'home' | 'paid' } = {}) {
  const paid = variant === 'paid'
  const router = useRouter()
  const { user, loading: authLoading } = useAuth()

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [openFaq, setOpenFaq] = useState<number | null>(null)

  const [pricingLocations, setPricingLocations] = useState<number>(5)
  const [pricingInterval, setPricingInterval] = useState<'monthly' | 'annual'>('monthly')
  const { data: basicQuote } = useQuote(pricingLocations, pricingInterval, 'basic', true)
  const { data: proQuote } = useQuote(pricingLocations, pricingInterval, 'pro', true)

  useEffect(() => {
    if (!authLoading && user) {
      router.replace('/dashboard')
    }
  }, [user, authLoading, router])

  const handleContinueWithGoogle = async (ctaLocation: CtaLocation = 'header') => {
    setError('')
    setLoading(true)
    try {
      await beginGoogleLogin(ctaLocation)
    } catch (err: any) {
      setError(err.message || 'Failed to initiate Google Authentication flow.')
      setLoading(false)
    }
  }

  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  const GoogleIcon = ({ className = 'h-5 w-5' }: { className?: string }) => (
    <svg className={`${className} shrink-0`} viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z" />
      <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z" />
      <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z" />
      <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z" />
    </svg>
  )

  return (
    <div className={`relative min-h-screen overflow-x-clip bg-background font-sans text-foreground selection:bg-primary/30 selection:text-foreground ${paid ? 'pb-24 md:pb-0' : ''}`}>
      {/* Ambient highlight */}
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[900px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />

      {/* 1. NAVBAR */}
      <header className="sticky top-0 z-50 w-full border-b border-border/80 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <div className="flex cursor-pointer items-center gap-2" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <img src="/logo-horizontal-3.png" alt="Pinzo" className="h-8 shrink-0 object-contain" />
          </div>

          <nav className="hidden items-center gap-7 md:flex">
            {[['how', 'How it works'], ['features', 'Features'], ['rank', 'Local Rank'], ['pricing', 'Pricing'], ['faq', 'FAQ']].map(([id, label]) => (
              <button key={id} onClick={() => scrollToSection(id)} className="text-xs font-bold uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground">
                {label}
              </button>
            ))}
          </nav>

          <div className="hidden items-center gap-4 md:flex">
            <button onClick={() => handleContinueWithGoogle('navbar')} disabled={loading} className="text-xs font-bold uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50">
              Login
            </button>
            <button onClick={() => handleContinueWithGoogle('navbar')} disabled={loading} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-bold uppercase tracking-widest text-primary-foreground shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50">
              {loading ? <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" /> : <><GoogleIcon className="h-4 w-4" /> Continue with Google</>}
            </button>
          </div>

          <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground md:hidden">
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </header>

      {/* Mobile menu */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 top-16 z-40 w-full border-b border-border bg-background/95 backdrop-blur-lg duration-300 animate-in fade-in slide-in-from-top-4 md:hidden">
          <div className="flex flex-col gap-2 p-6">
            {[['how', 'How it works'], ['features', 'Features'], ['rank', 'Local Rank'], ['pricing', 'Pricing'], ['faq', 'FAQ']].map(([id, label]) => (
              <button key={id} onClick={() => scrollToSection(id)} className="border-b border-border/50 py-3 text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground">
                {label}
              </button>
            ))}
            <button onClick={() => handleContinueWithGoogle('mobile_menu')} disabled={loading} className="mt-4 flex w-full items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-950 disabled:opacity-50">
              {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon /> Continue with Google</>}
            </button>
          </div>
        </div>
      )}

      {/* 2. HERO */}
      <section className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 pb-16 pt-16 sm:px-6 lg:grid-cols-2 lg:px-8 lg:pt-24">
        <div className="space-y-7 text-center lg:text-left">
          <Reveal>
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
              <Sparkles className="h-3.5 w-3.5" />
              <span>{paid ? 'Free GBP audit in 60 seconds' : 'Operational engine for multi-location GMB SEO'}</span>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
              {paid ? (
                <>Audit every Google Business Profile{' '}
                  <span className="text-primary">in 60 seconds.</span></>
              ) : (
                <>Every Google Business Profile.{' '}
                  <span className="text-primary">One command center.</span></>
              )}
            </h1>
          </Reveal>
          <Reveal delay={160}>
            <p className="mx-auto max-w-xl text-base text-muted-foreground sm:text-lg lg:mx-0">
              {paid
                ? 'Connect Google and instantly see your Health Score, missing fields, and review gaps across every location, then fix them from one AI dashboard.'
                : 'Track local rank heatmaps, answer reviews with AI, rank every location on a leaderboard, and schedule Google Posts across hundreds of stores, from one secure dashboard.'}
            </p>
          </Reveal>
          <Reveal delay={240}>
            <div className="flex flex-col items-center gap-4 pt-2 sm:flex-row lg:justify-start">
              <button onClick={() => handleContinueWithGoogle('hero')} disabled={loading} className="flex w-full min-w-[220px] items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-6 py-3.5 text-sm font-bold text-gray-950 shadow-lg transition-colors hover:bg-gray-50 disabled:opacity-50 sm:w-auto">
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon /> {paid ? 'Get My Free GMB Audit' : 'Continue with Google'}</>}
              </button>
              <button onClick={() => scrollToSection('pricing')} className="flex w-full min-w-[150px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
                View Pricing <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row lg:justify-start">
              <div className="flex -space-x-3">
                <img className="inline-block h-9 w-9 rounded-full ring-2 ring-background shadow-sm" src="https://i.pravatar.cc/100?img=1" alt="" />
                <img className="inline-block h-9 w-9 rounded-full ring-2 ring-background shadow-sm" src="https://i.pravatar.cc/100?img=33" alt="" />
                <img className="inline-block h-9 w-9 rounded-full ring-2 ring-background shadow-sm" src="https://i.pravatar.cc/100?img=12" alt="" />
                <img className="inline-block h-9 w-9 rounded-full ring-2 ring-background shadow-sm" src="https://i.pravatar.cc/100?img=45" alt="" />
                <img className="inline-block h-9 w-9 rounded-full ring-2 ring-background shadow-sm" src="https://i.pravatar.cc/100?img=60" alt="" />
              </div>
              <p className="text-xs font-semibold text-muted-foreground">⭐ Loved by <span className="font-bold text-foreground">500+</span> local SEO agencies</p>
            </div>
          </Reveal>
          {error && <div className="mx-auto max-w-md rounded-lg border border-red-500/20 bg-red-500/10 p-3 text-xs font-semibold text-red-500 lg:mx-0">{error}</div>}
          <Reveal delay={320}>
            <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2.5 pt-2 text-[11px] font-semibold text-muted-foreground lg:justify-start">
              {[[KeyRound, 'Secure Google OAuth'], [ShieldCheck, 'Tokens encrypted at rest'], [CreditCard, 'No card for trial'], [XCircle, 'Cancel anytime']].map(([Icon, label]: any, i) => (
                <span key={i} className="inline-flex items-center gap-1.5"><Icon className="h-3.5 w-3.5 shrink-0 text-emerald-500" />{label}</span>
              ))}
            </div>
          </Reveal>
        </div>

        {/* Hero visual: paid page shows a plain audit-result mockup; homepage keeps the rank animation. */}
        <Reveal delay={200} className="relative">
          <div className="absolute -inset-4 -z-10 rounded-3xl bg-primary/5 blur-2xl" />
          {paid ? <AuditPreview /> : <RankMapReveal />}
        </Reveal>
      </section>

      {/* 2a. THE PROBLEM — paid page only. Agitate the branch-wise pain before the payoff. */}
      {paid && (
        <section className="py-20">
          <div className="mx-auto max-w-5xl space-y-10 px-4 sm:px-6 lg:px-8">
            <Reveal className="mx-auto max-w-2xl space-y-4 text-center">
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Most brands don&apos;t have one Google problem. They have a branch-wise problem.</h2>
              <p className="text-muted-foreground">Every location has its own profile, its own reviews and its own ranking. One weak branch quietly leaks calls and customers to the competitor next door, and you can&apos;t see it from a single Google dashboard.</p>
            </Reveal>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {[
                { icon: MapPin, p: 'Incomplete profiles', i: 'Lower trust and fewer calls' },
                { icon: MessageSquare, p: 'Unanswered reviews', i: 'Weak perception and lost customers' },
                { icon: TrendingUp, p: 'Branches ranking below rivals', i: 'Lost local searches and store visits' },
                { icon: Search, p: 'Missing or wrong services', i: "Google can't match you to searches" },
                { icon: Calendar, p: 'Stale photos and posts', i: 'Profiles look inactive and untrustworthy' },
                { icon: BarChart2, p: 'No branch-wise reporting', i: "You can't tell which locations are weak" },
              ].map((row, idx) => (
                <Reveal key={idx} delay={idx * 60}>
                  <div className="flex h-full flex-col gap-3 rounded-xl border border-border bg-card p-5 shadow-sm">
                    <row.icon className="h-5 w-5 text-rose-500" />
                    <p className="text-sm font-bold text-foreground">{row.p}</p>
                    <p className="text-xs leading-relaxed text-muted-foreground">{row.i}</p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* 2b. WHAT YOUR AUDIT REVEALS — paid page only. Makes the "audit" CTA concrete. */}
      {paid && (
        <section className="border-y border-border/40 bg-muted/10 py-20">
          <div className="mx-auto max-w-5xl space-y-10 px-4 sm:px-6 lg:px-8">
            <Reveal className="mx-auto max-w-2xl space-y-4 text-center">
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">What your free audit reveals</h2>
              <p className="text-muted-foreground">The moment you connect Google, Pinzo scores every location and shows exactly what to fix first, with no waiting and no sales call.</p>
            </Reveal>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {[
                'Branch-wise Google Business Profile Health Score',
                'Missing services, categories, photos and profile fields',
                'Pending review replies and weak response patterns',
                'Locations with low ratings, thin reviews or stale activity',
                'Local visibility gaps and possible ranking issues',
                'Top priority fixes, ranked per location',
              ].map((item, i) => (
                <Reveal key={i} delay={i * 60}>
                  <div className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm">
                    <Check className="mt-0.5 h-5 w-5 shrink-0 text-emerald-500" />
                    <span className="text-sm font-medium text-foreground">{item}</span>
                  </div>
                </Reveal>
              ))}
            </div>
            <Reveal className="flex justify-center">
              <button onClick={() => handleContinueWithGoogle('hero')} disabled={loading} className="flex min-w-[220px] items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-6 py-3.5 text-sm font-bold text-gray-950 shadow-lg transition-colors hover:bg-gray-50 disabled:opacity-50">
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon /> Get My Free GMB Audit</>}
              </button>
            </Reveal>
          </div>
        </section>
      )}

      {/* 2c. BY INDUSTRY — paid page only. Swipeable on mobile (CSS scroll-snap, no lib),
          grid on desktop. Shows how the audit helps concrete verticals. */}
      {paid && (
        <section className="py-20">
          <div className="mx-auto max-w-6xl space-y-10 px-4 sm:px-6 lg:px-8">
            <Reveal className="mx-auto max-w-2xl space-y-4 text-center">
              <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Built for how your industry gets found</h2>
              <p className="text-muted-foreground">Every vertical has its own local-search battle. Here is what Pinzo fixes first for yours.</p>
            </Reveal>
            {/* Mobile: horizontal swipe. Desktop: 3-col grid. */}
            <div className="-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden sm:mx-0 sm:grid sm:grid-cols-2 sm:overflow-visible sm:px-0 sm:pb-0 lg:grid-cols-3">
              {[
                { icon: Utensils, name: 'Restaurants & Cafés', desc: 'Win "near me" searches at lunch rush, keep menus and hours right across branches, and reply to reviews before they scare off diners.' },
                { icon: Stethoscope, name: 'Clinics & Healthcare', desc: 'Show accurate hours and services per location, surface trust-building reviews, and rank when patients search for care nearby.' },
                { icon: ShoppingBag, name: 'Retail & Franchises', desc: 'Keep every outlet on the map with correct info, spot branches ranking below rivals, and drive Maps footfall store by store.' },
                { icon: Scissors, name: 'Salons & Spas', desc: 'Turn 5-star reviews into bookings, keep photos fresh, and outrank the salon down the street for local searches.' },
                { icon: Home, name: 'Real Estate & Services', desc: 'Rank across every area you serve, capture leads from Google with a microsite per location, and track which branches convert.' },
                { icon: Car, name: 'Automotive & Service Centers', desc: 'Fix service listings, answer reviews fast, and make sure drivers searching "near me" find your bay, not the competitor.' },
              ].map((ind, idx) => (
                <Reveal key={ind.name} delay={(idx % 3) * 60} className="w-[80%] shrink-0 snap-center sm:w-auto">
                  <div className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-md">
                    <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><ind.icon className="h-5 w-5 text-primary" /></div>
                    <h3 className="text-base font-bold text-foreground">{ind.name}</h3>
                    <p className="text-sm leading-relaxed text-muted-foreground">{ind.desc}</p>
                  </div>
                </Reveal>
              ))}
            </div>
            <p className="text-center text-xs font-semibold text-muted-foreground sm:hidden">Swipe to see more industries →</p>
          </div>
        </section>
      )}

      {/* 3. LIVE STATS BAND */}
      <section className="border-y border-border/40 bg-muted/5 py-12">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-8 px-4 sm:px-6 md:grid-cols-4 lg:px-8">
          {[
            { v: 4.8, d: 1, suffix: ' ★', label: 'Avg rating managed' },
            { v: 1482, label: 'Reviews synced' },
            { v: 98, suffix: '%', label: 'NAP consistency' },
            { v: 12, label: 'Locations, one login' },
          ].map((s, i) => (
            <Reveal key={i} delay={i * 80} className="text-center">
              <div className="text-3xl font-extrabold text-foreground sm:text-4xl">
                <CountUp value={s.v} decimals={s.d ?? 0} suffix={s.suffix ?? ''} />
              </div>
              <p className="mt-1.5 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">{s.label}</p>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 4. BUILT FOR */}
      <section className="py-10">
        <div className="mx-auto max-w-7xl space-y-6 px-4 text-center sm:px-6 lg:px-8">
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/70">Purpose-built for teams managing local presence at scale</p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-5">
            {BUILT_FOR.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-muted-foreground"><s.icon className="h-5 w-5 text-primary" /><span className="text-sm font-bold tracking-tight">{s.name}</span></div>
            ))}
          </div>
        </div>
      </section>

      {/* 5. BENTO FEATURES */}
      <section id="features" className="mx-auto max-w-7xl scroll-mt-20 space-y-12 px-4 py-20 sm:px-6 lg:px-8">
        <Reveal className="mx-auto max-w-3xl space-y-4 text-center">
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Everything local SEO needs, in one place</h2>
          <p className="text-muted-foreground">Stop logging into twelve Google dashboards. Rank tracking, reputation, posts, and team control, unified.</p>
        </Reveal>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {/* Wide: Leaderboard with live mini ranking */}
          <Reveal className="md:col-span-2">
            <div className="flex h-full flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-amber-400/30 bg-amber-500/10"><Trophy className="h-5 w-5 text-amber-500" /></div>
                <h3 className="text-base font-bold text-foreground">Location Leaderboard</h3>
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">Rank every location by a composite score of ratings, profile health, and response rate. Cohort ranking puts each store against its peer tier, with an AI next-best-action to climb.</p>
              <div className="mt-1 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {LEADERS.map((l) => (
                  <div key={l.rank} className="flex items-center gap-2.5 rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                    <span className={`flex h-5 w-5 items-center justify-center rounded text-[10px] font-extrabold ${l.rank <= 3 ? 'bg-amber-500/20 text-amber-600' : 'bg-muted text-muted-foreground'}`}>{l.rank}</span>
                    <span className="flex-1 truncate text-[11px] font-semibold text-foreground">{l.name}</span>
                    <span className="font-mono text-[11px] font-bold text-foreground">{l.score}</span>
                    <TrendingUp className={`h-3 w-3 ${l.up ? 'text-emerald-500' : 'rotate-180 text-rose-500'}`} />
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          {/* Search Intelligence */}
          <Reveal delay={120}>
            <div className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><Search className="h-5 w-5 text-primary" /></div>
              <h3 className="text-base font-bold text-foreground">Search Intelligence</h3>
              <p className="text-sm leading-relaxed text-muted-foreground">See the exact keywords customers use to find you, split branded vs. discovery searches, and track impressions over time.</p>
            </div>
          </Reveal>

          {/* Remaining features (Local Rank is now a normal card, not a repeated heatmap) */}
          {[
            { title: 'Local Rank Tracking', desc: paid ? 'See your position on Google Maps in every area you serve, so you know exactly where customers find you and where they find a competitor instead.' : 'Per-keyword heatmaps across your trade area show exactly where you win the local pack and where you are invisible.', icon: Map },
            { title: 'Lead-Capture Microsites', desc: 'A fast, SEO-friendly public page per location, with reviews, photos, hours, and a contact form that turns Google traffic into leads.', icon: Globe },
            { title: 'Unified Review Inbox', desc: 'Every Google review from all locations in one searchable inbox. Reply, track status, never miss a customer.', icon: MessageSquare },
            { title: 'Google Posts Scheduler', desc: 'Schedule offers, updates, and events across many locations at once with CTA buttons.', icon: Calendar },
            { title: 'Multi-Location Analytics', desc: 'Track Maps clicks, calls, website actions, and search views across one location or hundreds.', icon: BarChart2 },
            { title: 'Team Roles (RBAC)', desc: 'Scoped access for managers, regional leads, or clients, without sharing Google credentials.', icon: Users },
            { title: 'GMB Profile Audits', desc: 'Automated health checks surface NAP discrepancies, missing fields, and optimization gaps.', icon: Shield },
          ].map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 60}>
              <div className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-md">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><f.icon className="h-5 w-5 text-primary" /></div>
                <h3 className="text-base font-bold text-foreground">{f.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{f.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 6. LOCAL RANK DEEP DIVE (distinct trend visual, not the heatmap again) */}
      <section id="rank" className="scroll-mt-16 border-y border-border/30 bg-muted/30 py-20">
        <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 sm:px-6 lg:grid-cols-2 lg:px-8">
          <Reveal className="space-y-6">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">{paid ? 'Where customers find you' : 'Geo-grid rank tracking'}</div>
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{paid ? 'See which areas find you first, and which find your competitor' : 'Know exactly where you show up on the map'}</h2>
            <p className="leading-relaxed text-muted-foreground">{paid ? 'When someone nearby searches "near me", your spot on Google Maps changes street by street. Pinzo checks every neighbourhood you serve and shows you the exact areas where customers see you first, and where a competitor is showing up instead of you.' : 'Rankings change block by block. Pinzo scans a grid of points across your trade area for each keyword, so you see precisely where you own the local pack and where competitors beat you, then act on it.'}</p>
            <ul className="space-y-3 text-xs font-semibold text-muted-foreground">
              {(paid
                ? ['Your Google Maps position in every area you serve', 'See if you are moving up or down, week by week', 'Simple next steps to win the areas you are losing']
                : ['Per-keyword heatmaps across your full service area', 'Track rank movement over time, week by week', 'AI next-best-action to climb the local pack']
              ).map((t) => (
                <li key={t} className="flex items-center gap-2"><Check className="h-4 w-4 shrink-0 text-emerald-500" />{t}</li>
              ))}
            </ul>
          </Reveal>
          <Reveal delay={120}><RankTrend /></Reveal>
        </div>
      </section>

      {/* 7. REVIEWS + AI (condensed, single section) */}
      <section className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 py-20 sm:px-6 lg:grid-cols-2 lg:px-8">
        <Reveal className="order-2 lg:order-1">
          <div className="space-y-4 rounded-2xl border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between border-b border-border/50 pb-3">
              <span className="flex items-center gap-2 text-xs font-bold text-foreground"><span className="h-2.5 w-2.5 rounded-full bg-primary" />Pending approval, Westside Store</span>
              <span className="text-[10px] text-muted-foreground">10m ago</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-foreground">Marcus Vance <span className="font-normal text-muted-foreground">Local Guide</span></span>
              <div className="flex gap-0.5 text-amber-400">{[...Array(5)].map((_, i) => <Star key={i} className="h-3 w-3 fill-current" />)}</div>
            </div>
            <p className="text-xs italic leading-relaxed text-muted-foreground">&quot;Best burger combo in town. Service was fast and the location was very tidy. Highly recommended.&quot;</p>
            <div className="space-y-2 rounded-lg border border-border bg-muted/30 p-3.5">
              <div className="flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5 text-primary" /><span className="text-[10px] font-bold uppercase tracking-wide text-primary">AI recommended response</span></div>
              <p className="text-xs leading-normal text-foreground">&quot;Hi Marcus, thank you so much for the 5-star review! We&apos;re glad you enjoyed the burgers and quick service at our Westside location. Hope to see you again soon!&quot;</p>
              <div className="flex justify-end gap-2 pt-1">
                <button className="rounded border border-border px-2.5 py-1.5 text-[10px] font-bold uppercase text-muted-foreground hover:text-foreground">Edit</button>
                <button className="rounded bg-primary px-3 py-1.5 text-[10px] font-extrabold uppercase text-primary-foreground hover:bg-primary/90">Publish</button>
              </div>
            </div>
          </div>
        </Reveal>
        <Reveal delay={100} className="order-1 space-y-6 lg:order-2">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Reputation management</div>
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Answer every review with AI, on time</h2>
          <p className="leading-relaxed text-muted-foreground">Reviews are a key local ranking signal. Respond instantly with brand-specific AI drafts and never leave a customer hanging. You approve every reply before it goes live.</p>
          <ul className="space-y-3 text-xs font-semibold text-muted-foreground">
            {['Automatic sentiment and issue tagging for every 1 to 5 star review', 'AI drafts that match your brand tone, approve before publishing', 'SLA tracking so no review goes unanswered past your target'].map((t) => (
              <li key={t} className="flex items-center gap-2"><Check className="h-4 w-4 shrink-0 text-emerald-500" />{t}</li>
            ))}
          </ul>
        </Reveal>
      </section>

      {/* 8. HOW IT WORKS */}
      <section id="how" className="mx-auto max-w-7xl scroll-mt-20 space-y-12 px-4 py-20 sm:px-6 lg:px-8">
        <Reveal className="mx-auto max-w-3xl space-y-4 text-center">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Get started in minutes</div>
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">How Pinzo works</h2>
          <p className="text-muted-foreground">No passwords shared, no manual exports. Connect once and manage every profile from one workspace.</p>
        </Reveal>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {[
            { step: '01', title: 'Connect with Google', desc: 'Sign in with secure Google OAuth and grant access. We never see your password, only encrypted, revocable tokens.', icon: Plug },
            { step: '02', title: 'We sync your locations', desc: 'Locations, reviews, ratings, rank, and performance are pulled in automatically and kept up to date.', icon: RefreshCw },
            { step: '03', title: 'Manage from one dashboard', desc: 'Reply with AI, schedule posts, track rank and leaderboards, run audits, all with team roles and SLAs.', icon: LayoutDashboard },
          ].map((item, i) => (
            <Reveal key={i} delay={i * 80}>
              <div className="flex h-full flex-col gap-4 rounded-2xl border border-border bg-card p-6 shadow-sm">
                <div className="flex items-center justify-between">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><item.icon className="h-5 w-5 text-primary" /></div>
                  <span className="text-2xl font-extrabold text-muted-foreground/20">{item.step}</span>
                </div>
                <h3 className="text-base font-bold text-foreground">{item.title}</h3>
                <p className="text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 9. PRICING */}
      <section id="pricing" className="mx-auto max-w-7xl scroll-mt-16 space-y-12 px-4 py-20 sm:px-6 lg:px-8">
        <Reveal className="mx-auto max-w-3xl space-y-4 text-center">
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Simple pricing that scales with you</h2>
          <p className="text-muted-foreground">Pay only for the locations you manage. Every location includes AI credits. Start with a 7-day free trial, no credit card required.</p>
          <div className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 pt-2 text-xs font-semibold text-muted-foreground">
            <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />Cancel anytime</span>
            <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />No lock-in contracts</span>
            <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />GST invoice included</span>
            <span className="flex items-center gap-1.5"><Check className="h-3.5 w-3.5 text-emerald-500" />Setup in minutes</span>
          </div>
        </Reveal>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-6">
          <div className="flex items-center justify-center rounded-full bg-muted/40 p-1.5 backdrop-blur-md border border-border/50 shadow-inner">
            <button onClick={() => setPricingInterval('monthly')} className={`rounded-full px-6 py-2.5 text-xs font-bold uppercase tracking-widest transition-all duration-300 ${pricingInterval === 'monthly' ? 'bg-background text-foreground shadow-md scale-105' : 'text-muted-foreground hover:text-foreground'}`}>Monthly</button>
            <button onClick={() => setPricingInterval('annual')} className={`rounded-full px-6 py-2.5 text-xs font-bold uppercase tracking-widest transition-all duration-300 ${pricingInterval === 'annual' ? 'bg-background text-foreground shadow-md scale-105' : 'text-muted-foreground hover:text-foreground'}`}>Yearly <span className={pricingInterval === 'annual' ? 'text-emerald-500' : 'text-emerald-500'}>· Save 20%</span></button>
          </div>
          
          {/* Shared location slider drives both per-location plans */}
          <div className="w-full max-w-xs space-y-3 rounded-2xl border border-border/50 bg-card/40 backdrop-blur-md p-4 shadow-sm transition-all hover:border-primary/40 hover:shadow-md">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-muted-foreground">Locations</label>
              <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-bold text-primary">{pricingLocations} {pricingLocations === 1 ? 'loc' : 'locs'}</span>
            </div>
            <input type="range" min={1} max={50} value={pricingLocations} onChange={(e) => setPricingLocations(Number(e.target.value))} className="w-full cursor-pointer accent-primary transition-all" aria-label="Number of locations" />
          </div>
        </div>

        <div className="mx-auto grid max-w-6xl grid-cols-1 items-stretch gap-6 lg:grid-cols-3 pt-6">
          {/* BASIC */}
          <div className="group flex flex-col gap-5 rounded-[2rem] border border-border/60 bg-card/40 backdrop-blur-xl p-8 shadow-sm transition-all duration-500 hover:-translate-y-2 hover:border-primary/30 hover:shadow-xl hover:bg-card/80">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Basic</span>
              <p className="text-xs font-medium text-muted-foreground">Everything you need to manage Google reviews & posts.</p>
              <div className="flex items-baseline gap-1 text-foreground">
                <span className="text-4xl font-extrabold">{basicQuote ? `₹${Math.round(basicQuote.price_paise / 100).toLocaleString('en-IN')}` : '...'}</span>
                <span className="text-sm font-semibold text-muted-foreground">/{pricingInterval === 'monthly' ? 'mo' : 'yr'}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">{basicQuote ? `≈ ₹${Math.round(basicQuote.price_paise / 100 / pricingLocations / (pricingInterval === 'annual' ? 12 : 1)).toLocaleString('en-IN')} per location / month · + ${Math.round(basicQuote.gst_rate * 100)}% GST` : ''}</p>
            </div>
            <button onClick={() => handleContinueWithGoogle('pricing')} disabled={loading} className="flex items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-5 py-3 text-xs font-bold uppercase tracking-widest text-foreground transition-colors hover:bg-muted/50 disabled:opacity-50">Start Free Trial</button>
            <ul className="space-y-2.5 border-t border-border pt-5 text-xs font-semibold text-muted-foreground">
              {[
                `${basicQuote ? basicQuote.monthly_ai_credits.toLocaleString('en-IN') : pricingLocations * 30} AI credits / month`,
                '30 AI credits per location',
                'Unified review inbox with AI drafts',
                'Automated review SLAs & tracking',
                'Bulk Google Posts scheduler',
                'Multi-location performance analytics',
                'Automated GMB health audits',
                'Role-based access (RBAC) & permissions'
              ].map((t) => (
                <li key={t} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 shrink-0 text-primary" />{t}</li>
              ))}
            </ul>
          </div>

          {/* PRO (highlighted) */}
          <div className="group relative flex flex-col gap-5 rounded-[2rem] border-2 border-primary bg-card/90 backdrop-blur-2xl p-8 shadow-2xl transition-all duration-500 hover:-translate-y-2 hover:shadow-primary/20 hover:bg-card">
            {/* Background glow */}
            <div className="pointer-events-none absolute -inset-0.5 -z-10 rounded-[2rem] bg-gradient-to-br from-primary/40 via-primary/10 to-transparent blur-xl opacity-60 group-hover:opacity-100 transition-opacity duration-500" />
            <div className="absolute -top-4 left-1/2 -translate-x-1/2 flex items-center gap-1.5 rounded-full bg-gradient-to-r from-primary to-primary/80 px-4 py-1.5 text-[10px] font-extrabold uppercase tracking-widest text-primary-foreground shadow-lg shadow-primary/30">
              <Sparkles className="h-3.5 w-3.5" /> Most popular
            </div>
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-primary">Pro · Local Rank + Microsites</span>
              <p className="text-xs font-medium text-foreground/70">Rank higher on Maps & turn searches into leads.</p>
              <div className="flex items-baseline gap-1 text-foreground">
                <span className="text-4xl font-extrabold">{proQuote ? `₹${Math.round(proQuote.price_paise / 100).toLocaleString('en-IN')}` : '...'}</span>
                <span className="text-sm font-semibold text-muted-foreground">/{pricingInterval === 'monthly' ? 'mo' : 'yr'}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">{proQuote ? `≈ ₹${Math.round(proQuote.price_paise / 100 / pricingLocations / (pricingInterval === 'annual' ? 12 : 1)).toLocaleString('en-IN')} per location / month · + ${Math.round(proQuote.gst_rate * 100)}% GST` : ''}</p>
            </div>
            <button onClick={() => handleContinueWithGoogle('pricing')} disabled={loading} className="flex items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-xs font-bold uppercase tracking-widest text-primary-foreground shadow transition-colors hover:bg-primary/90 disabled:opacity-50">Start Free Trial</button>
            <ul className="space-y-2.5 border-t border-primary/20 pt-5 text-xs font-semibold text-foreground">
              {[
                'Everything in Basic, plus:',
                `${proQuote ? proQuote.monthly_ai_credits.toLocaleString('en-IN') : pricingLocations * 45} AI credits / month`,
                '45 AI credits per location',
                paid ? 'Google Maps rank across every area you serve' : 'Local rank heatmaps (7x7 geo-grid)',
                'Lead-capture microsite per location',
                'Location leaderboard & cohort ranking',
                'Search term intelligence',
                'Review sentiment & issue AI tagging',
                'Competitor tracking & insights'
              ].map((t, i) => (
                <li key={t} className="flex items-center gap-2">{i === 0 ? <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary" /> : <Check className="h-3.5 w-3.5 shrink-0 text-primary" />}{t}</li>
              ))}
            </ul>
          </div>

          {/* ENTERPRISE */}
          <div className="group flex flex-col justify-between gap-5 rounded-[2rem] border border-border/60 bg-card/40 backdrop-blur-xl p-8 shadow-sm transition-all duration-500 hover:-translate-y-2 hover:border-foreground/30 hover:shadow-xl hover:bg-card/80">
            <div className="space-y-4">
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Enterprise</span>
              <div className="flex items-baseline gap-1 text-foreground"><span className="text-3xl font-extrabold">Let&apos;s talk</span></div>
              <p className="text-xs text-muted-foreground">Managing 50+ locations or need custom AI credits, onboarding, and support? We&apos;ll tailor a plan to fit.</p>
              <div className="h-px bg-border" />
              <ul className="space-y-2.5 text-xs font-semibold text-muted-foreground">
                {['50+ locations', 'Custom AI credit volume', 'Priority support & onboarding', 'Custom invoicing & SLA'].map((t) => (
                  <li key={t} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 shrink-0 text-primary" />{t}</li>
                ))}
              </ul>
            </div>
            <a href="https://wa.me/917021052482?text=Hi%2C%20I%27m%20interested%20in%20the%20Enterprise%20plan%20for%2050%2B%20locations." target="_blank" rel="noopener noreferrer" className="flex w-full items-center justify-center gap-2 rounded-lg border border-border px-4 py-3 text-xs font-bold uppercase tracking-widest text-muted-foreground transition-all hover:border-foreground hover:text-foreground">
              <WhatsAppIcon className="h-4 w-4" /> Chat on WhatsApp
            </a>
          </div>
        </div>

        <p className="text-center text-[11px] text-muted-foreground">7-day free trial · 3 locations · 10 AI credits included. No credit card required.</p>

        <div className="flex justify-center">
          <a href="/pricing" className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:underline">
            Compare all plans, including Lite <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      </section>

      {/* 10. FAQ */}
      <section id="faq" className="scroll-mt-16 border-y border-border/30 bg-muted/10 py-20">
        <div className="mx-auto max-w-4xl space-y-12 px-4 sm:px-6 lg:px-8">
          <Reveal className="space-y-4 text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground">Frequently asked questions</h2>
            <p className="text-muted-foreground">Clear answers on Google API limits, syncing speed, and workspace security.</p>
          </Reveal>
          <div className="space-y-3">
            {[
              ...(paid ? [{ q: 'What does the free audit show, and is it really free?', a: 'Yes, it is free. The moment you connect Google, Pinzo scores each location and surfaces missing fields, pending review replies, weak branches and priority fixes, and no card is required to see it.' }] : []),
              { q: 'Do I need to give you my Google password?', a: 'Absolutely not. We authenticate using Google OAuth secure scopes. You sign in with Google once and grant read/write access. We never store or see your password.' },
              { q: 'How fast do edits update on Google Maps?', a: 'Updates such as phone numbers, hours, and posts are pushed via the Google Business Profile API and typically appear on Google Maps within 2 to 5 minutes.' },
              { q: 'Is there a limit to how many locations I can connect?', a: 'There are no hard limits. Our Enterprise package lets you connect hundreds or thousands of physical locations under a single workspace.' },
              { q: 'How does the AI review responder work?', a: 'Our engine reads the review sentiment, matches it with your storefront details, and prepares a draft in your brand tone. Nothing is published automatically. You review and approve each reply before it goes live.' },
              { q: 'How is my data kept secure?', a: 'We connect through Google official OAuth and receive a revocable access token, never your password. Tokens are encrypted at rest, and access is scoped by role so team members only see what they should.' },
              { q: 'Can I cancel anytime?', a: 'Yes. There are no lock-in contracts on self-serve plans. Cancel from billing settings any time and you will not be charged again. You can also revoke our access from your Google account whenever you like.' },
              { q: 'What does the free trial include?', a: 'The 7-day free trial includes up to 3 locations and 10 AI credits, no credit card required. You get full access to reviews, AI replies, posts, analytics, rank, and audits to evaluate end-to-end.' },
            ].map((faq, i) => (
              <div key={i} className="overflow-hidden rounded-xl border border-border bg-card transition-colors hover:bg-muted/20" onClick={() => setOpenFaq(openFaq === i ? null : i)} role="button">
                <div className="flex select-none items-center justify-between p-5 text-sm font-bold text-foreground">
                  <span>{faq.q}</span>
                  <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${openFaq === i ? 'rotate-180 text-foreground' : ''}`} />
                </div>
                {openFaq === i && <div className="border-t border-border px-5 pb-5 pt-3.5 text-xs leading-relaxed text-muted-foreground duration-200 animate-in slide-in-from-top-2">{faq.a}</div>}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 11. FINAL CTA */}
      <section className="mx-auto max-w-5xl px-4 py-20 sm:px-6 lg:px-8">
        <Reveal>
          <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-primary/5 p-8 text-center sm:p-12 lg:p-16">
            <div className="pointer-events-none absolute left-1/2 top-1/2 -z-10 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl" />
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">{paid ? 'Find weak branches. Fix profile gaps. Grow local visibility.' : 'Start syncing your storefronts today'}</h2>
            <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">{paid ? 'Connect Google and get your free Health Score audit across every location in under a minute. No card required to start.' : 'Join local SEO directors, franchise owners, and agency operators who have abandoned manual spreadsheets. Connect your locations and start automating.'}</p>
            <div className="flex justify-center pt-6">
              <button onClick={() => handleContinueWithGoogle('footer')} disabled={loading} className="flex items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-6 py-3.5 text-sm font-bold text-gray-950 shadow-lg transition-colors hover:bg-gray-50 disabled:opacity-50">
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon /> {paid ? 'Get My Free GMB Audit' : 'Continue with Google'}</>}
              </button>
            </div>
          </div>
        </Reveal>
      </section>

      {/* 12. FOOTER */}
      <footer className="border-t border-border/80 py-12">
        <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 px-4 sm:px-6 md:grid-cols-4 lg:px-8">
          <div className="col-span-2 space-y-4 md:col-span-1">
            <img src="/logo-horizontal-3.png" alt="Pinzo" className="h-8 shrink-0 object-contain" />
            <p className="max-w-xs text-[11px] leading-relaxed text-muted-foreground">Synchronize, automate, and schedule locations under Google Business Profile. Dominating the local maps pack made simple.</p>
          </div>
          <div className="space-y-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">Product</span>
            <ul className="space-y-1.5 text-xs font-semibold text-muted-foreground">
              <li><button onClick={() => scrollToSection('features')} className="transition-colors hover:text-foreground">Features</button></li>
              <li><button onClick={() => scrollToSection('rank')} className="transition-colors hover:text-foreground">Local Rank</button></li>
              <li><button onClick={() => scrollToSection('pricing')} className="transition-colors hover:text-foreground">Pricing</button></li>
            </ul>
          </div>
          <div className="space-y-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">Legal &amp; Security</span>
            <ul className="space-y-1.5 text-xs font-semibold text-muted-foreground">
              <li><a href="/privacy" className="transition-colors hover:text-foreground">Privacy Policy</a></li>
              <li><a href="/terms" className="transition-colors hover:text-foreground">Terms of Service</a></li>
              <li><a href="/refund" className="transition-colors hover:text-foreground">Cancellation &amp; Refund Policy</a></li>
              <li><a href="/contact" className="transition-colors hover:text-foreground">Contact Us</a></li>
              <li><a href="/privacy#oauth" className="transition-colors hover:text-foreground">Google API &amp; OAuth Usage</a></li>
            </ul>
          </div>
          <div className="col-span-2 space-y-3 md:col-span-1">
            <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">Google Integration</span>
            <p className="text-[10px] leading-normal text-muted-foreground">Pinzo is a management platform. Google and Google Business Profile are trademarks of Google LLC. We interact with official Google API channels.</p>
          </div>
        </div>
        <div className="mx-auto mt-12 flex max-w-7xl flex-col items-center justify-between gap-4 border-t border-border/50 px-4 pt-6 text-[10px] font-semibold text-muted-foreground/60 sm:flex-row sm:px-6 lg:px-8">
          <span>&copy; {new Date().getFullYear()} Pinzo. All rights reserved.</span>
          <span>Not affiliated with or endorsed by Google LLC.</span>
        </div>
      </footer>

      {/* Sticky mobile audit CTA — paid page only, hidden once the desktop nav appears. */}
      {paid && (
        <div
          className="fixed inset-x-0 bottom-0 z-40 border-t border-border bg-background/95 px-4 py-3 backdrop-blur-md md:hidden"
          style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom))' }}
        >
          <button
            onClick={() => handleContinueWithGoogle('sticky_mobile')}
            disabled={loading}
            className="flex w-full items-center justify-center gap-2.5 rounded-lg border border-gray-200 bg-white px-5 py-3.5 text-sm font-bold text-gray-950 shadow-lg disabled:opacity-50"
          >
            {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon className="h-5 w-5" /> Get My Free GMB Audit</>}
          </button>
        </div>
      )}

      {/* Floating WhatsApp button — bottom-right on mobile and desktop.
          On the paid page it sits above the sticky mobile CTA bar until md. */}
      <a
        href="https://wa.me/917021052482?text=Hi%2C%20I%27d%20like%20to%20know%20more%20about%20Pinzo."
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Chat with us on WhatsApp"
        className={`group fixed right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-lg shadow-black/20 transition-transform hover:scale-105 active:scale-95 sm:right-6 ${paid ? 'bottom-24 md:bottom-6' : 'bottom-5 sm:bottom-6'}`}
      >
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#25D366] opacity-30" />
        <WhatsAppIcon className="relative h-7 w-7" />
      </a>
    </div>
  )
}
