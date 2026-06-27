'use client'

import { useState, useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'
import { api } from '@/lib/api'
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
  MessageCircle,
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

export default function HomeClient() {
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

  const handleContinueWithGoogle = async () => {
    setError('')
    setLoading(true)
    try {
      const response: any = await api.get('/auth/google/login')
      if (response && response.url) {
        window.location.href = response.url
      } else {
        throw new Error('Failed to retrieve authorization URL')
      }
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
    <svg className={`${className} shrink-0`} viewBox="0 0 24 24">
      <path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114A5.99 5.99 0 0 1 8 12.5a5.99 5.99 0 0 1 5.99-6.015c1.474 0 2.812.538 3.854 1.424l3.22-3.22A10.93 10.93 0 0 0 13.99 2 10.99 10.99 0 0 0 3 13c0 6.075 4.925 11 10.99 11 5.753 0 10.457-4.143 10.94-9.673H12.24Z" />
      <path fill="#FBBC05" d="M13.99 2a10.93 10.93 0 0 0-7.045 2.58l3.22 3.22A5.99 5.99 0 0 1 13.99 5.985V2Z" />
      <path fill="#34A853" d="M3 13c0 2.215.656 4.275 1.785 6.015l3.22-3.22A5.99 5.99 0 0 1 8 12.5c0-1.282.4-2.472 1.085-3.465L5.865 5.815A10.93 10.93 0 0 0 3 13Z" />
      <path fill="#4285F4" d="M13.99 24c3.045 0 5.81-1.233 7.82-3.225l-3.22-3.22A5.99 5.99 0 0 1 13.99 18.5a5.99 5.99 0 0 1-5.99-6.015c0-.46.057-.905.158-1.332L4.938 7.913A10.97 10.97 0 0 0 13.99 24Z" />
    </svg>
  )

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background font-sans text-foreground selection:bg-primary/30 selection:text-foreground">
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
            <button onClick={handleContinueWithGoogle} disabled={loading} className="text-xs font-bold uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50">
              Login
            </button>
            <button onClick={handleContinueWithGoogle} disabled={loading} className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-bold uppercase tracking-widest text-primary-foreground shadow-sm transition-all hover:bg-primary/90 disabled:opacity-50">
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
        <div className="fixed inset-0 top-16 z-40 w-full border-b border-border bg-background/95 backdrop-blur-lg duration-200 animate-in fade-in md:hidden">
          <div className="flex flex-col gap-2 p-6">
            {[['how', 'How it works'], ['features', 'Features'], ['rank', 'Local Rank'], ['pricing', 'Pricing'], ['faq', 'FAQ']].map(([id, label]) => (
              <button key={id} onClick={() => scrollToSection(id)} className="border-b border-border/50 py-3 text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground">
                {label}
              </button>
            ))}
            <button onClick={handleContinueWithGoogle} disabled={loading} className="mt-4 flex w-full items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-4 py-3 text-sm font-semibold text-gray-950 disabled:opacity-50">
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
              <span>Operational engine for multi-location GMB SEO</span>
            </div>
          </Reveal>
          <Reveal delay={80}>
            <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl lg:text-6xl">
              Every Google Business Profile.{' '}
              <span className="text-primary">One command center.</span>
            </h1>
          </Reveal>
          <Reveal delay={160}>
            <p className="mx-auto max-w-xl text-base text-muted-foreground sm:text-lg lg:mx-0">
              Track local rank heatmaps, answer reviews with AI, rank every location on a leaderboard, and schedule Google Posts across hundreds of stores, from one secure dashboard.
            </p>
          </Reveal>
          <Reveal delay={240}>
            <div className="flex flex-col items-center gap-4 pt-2 sm:flex-row lg:justify-start">
              <button onClick={handleContinueWithGoogle} disabled={loading} className="flex w-full min-w-[220px] items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-6 py-3.5 text-sm font-bold text-gray-950 shadow-lg transition-colors hover:bg-gray-50 disabled:opacity-50 sm:w-auto">
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon /> Continue with Google</>}
              </button>
              <button onClick={() => scrollToSection('pricing')} className="flex w-full min-w-[150px] items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-6 py-3.5 text-sm font-semibold text-muted-foreground transition-all hover:bg-muted/50 hover:text-foreground sm:w-auto">
                View Pricing <ArrowRight className="h-4 w-4" />
              </button>
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

        {/* Hero visual: the animated heatmap (used only here) */}
        <Reveal delay={200} className="relative">
          <div className="absolute -inset-4 -z-10 rounded-3xl bg-primary/5 blur-2xl" />
          <RankMapReveal />
        </Reveal>
      </section>

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
              <h3 className="text-sm font-bold text-foreground">Search Intelligence</h3>
              <p className="text-xs leading-relaxed text-muted-foreground">See the exact keywords customers use to find you, split branded vs. discovery searches, and track impressions over time.</p>
            </div>
          </Reveal>

          {/* Remaining features (Local Rank is now a normal card, not a repeated heatmap) */}
          {[
            { title: 'Local Rank Tracking', desc: 'Per-keyword heatmaps across your trade area show exactly where you win the local pack and where you are invisible.', icon: Map },
            { title: 'Lead-Capture Microsites', desc: 'A fast, SEO-friendly public page per location — reviews, photos, hours, and a contact form that turns Google traffic into leads.', icon: Globe },
            { title: 'Unified Review Inbox', desc: 'Every Google review from all locations in one searchable inbox. Reply, track status, never miss a customer.', icon: MessageSquare },
            { title: 'Google Posts Scheduler', desc: 'Schedule offers, updates, and events across many locations at once with CTA buttons.', icon: Calendar },
            { title: 'Multi-Location Analytics', desc: 'Track Maps clicks, calls, website actions, and search views across one location or hundreds.', icon: BarChart2 },
            { title: 'Team Roles (RBAC)', desc: 'Scoped access for managers, regional leads, or clients, without sharing Google credentials.', icon: Users },
            { title: 'GMB Profile Audits', desc: 'Automated health checks surface NAP discrepancies, missing fields, and optimization gaps.', icon: Shield },
          ].map((f, i) => (
            <Reveal key={f.title} delay={(i % 3) * 60}>
              <div className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-card p-6 shadow-sm transition-shadow hover:shadow-md">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10"><f.icon className="h-5 w-5 text-primary" /></div>
                <h3 className="text-sm font-bold text-foreground">{f.title}</h3>
                <p className="text-xs leading-relaxed text-muted-foreground">{f.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* 6. LOCAL RANK DEEP DIVE (distinct trend visual, not the heatmap again) */}
      <section id="rank" className="scroll-mt-16 border-y border-border/30 bg-muted/30 py-20">
        <div className="mx-auto grid max-w-7xl grid-cols-1 items-center gap-12 px-4 sm:px-6 lg:grid-cols-2 lg:px-8">
          <Reveal className="space-y-6">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary">Geo-grid rank tracking</div>
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Know exactly where you show up on the map</h2>
            <p className="leading-relaxed text-muted-foreground">Rankings change block by block. Pinzo scans a grid of points across your trade area for each keyword, so you see precisely where you own the local pack and where competitors beat you, then act on it.</p>
            <ul className="space-y-3 text-xs font-semibold text-muted-foreground">
              {['Per-keyword heatmaps across your full service area', 'Track rank movement over time, week by week', 'AI next-best-action to climb the local pack'].map((t) => (
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
                <h3 className="text-sm font-bold text-foreground">{item.title}</h3>
                <p className="text-xs leading-relaxed text-muted-foreground">{item.desc}</p>
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
        </Reveal>

        <div className="flex items-center justify-center gap-2">
          <button onClick={() => setPricingInterval('monthly')} className={`rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-widest transition-colors ${pricingInterval === 'monthly' ? 'bg-primary text-primary-foreground' : 'bg-muted/30 text-muted-foreground hover:text-foreground'}`}>Monthly</button>
          <button onClick={() => setPricingInterval('annual')} className={`rounded-lg px-4 py-2 text-xs font-bold uppercase tracking-widest transition-colors ${pricingInterval === 'annual' ? 'bg-primary text-primary-foreground' : 'bg-muted/30 text-muted-foreground hover:text-foreground'}`}>Yearly <span className="text-emerald-500">· Save 20%</span></button>
        </div>
        {/* Shared location slider drives both per-location plans */}
        <div className="mx-auto max-w-md space-y-3 rounded-2xl border border-border bg-card p-5 shadow-sm">
          <div className="flex items-center justify-between">
            <label className="text-sm font-semibold text-foreground">How many locations?</label>
            <span className="text-sm font-bold text-primary">{pricingLocations} {pricingLocations === 1 ? 'location' : 'locations'}</span>
          </div>
          <input type="range" min={1} max={50} value={pricingLocations} onChange={(e) => setPricingLocations(Number(e.target.value))} className="w-full cursor-pointer accent-primary" aria-label="Number of locations" />
          <div className="flex justify-between font-mono text-[10px] text-muted-foreground"><span>1</span><span>50</span></div>
        </div>

        <div className="mx-auto grid max-w-6xl grid-cols-1 items-stretch gap-6 lg:grid-cols-3">
          {/* BASIC */}
          <div className="flex flex-col gap-5 rounded-2xl border border-border bg-card p-8 shadow-sm">
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Basic</span>
              <div className="flex items-baseline gap-1 text-foreground">
                <span className="text-4xl font-extrabold">{basicQuote ? `₹${Math.round(basicQuote.price_paise / 100).toLocaleString('en-IN')}` : '...'}</span>
                <span className="text-sm font-semibold text-muted-foreground">/{pricingInterval === 'monthly' ? 'mo' : 'yr'}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">{basicQuote ? `+ ${Math.round(basicQuote.gst_rate * 100)}% GST · ` : ''}for {pricingLocations} {pricingLocations === 1 ? 'location' : 'locations'}</p>
            </div>
            <button onClick={handleContinueWithGoogle} disabled={loading} className="flex items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 px-5 py-3 text-xs font-bold uppercase tracking-widest text-foreground transition-colors hover:bg-muted/50 disabled:opacity-50">Start Free Trial</button>
            <ul className="space-y-2.5 border-t border-border pt-5 text-xs font-semibold text-muted-foreground">
              {[`${basicQuote ? basicQuote.monthly_ai_credits.toLocaleString('en-IN') : pricingLocations * 30} AI credits / month`, '30 AI credits per location', 'Unified review inbox + AI replies', 'Google Posts scheduler', 'Multi-location analytics & audits', 'Team roles & permissions'].map((t) => (
                <li key={t} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 shrink-0 text-primary" />{t}</li>
              ))}
            </ul>
          </div>

          {/* PRO (highlighted) */}
          <div className="relative flex flex-col gap-5 rounded-2xl border-2 border-primary bg-primary/5 p-8 shadow-md">
            <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-[9px] font-extrabold uppercase tracking-widest text-primary-foreground">Most popular</span>
            <div className="space-y-1">
              <span className="text-[10px] font-bold uppercase tracking-widest text-primary">Pro · Local Rank + Microsites</span>
              <div className="flex items-baseline gap-1 text-foreground">
                <span className="text-4xl font-extrabold">{proQuote ? `₹${Math.round(proQuote.price_paise / 100).toLocaleString('en-IN')}` : '...'}</span>
                <span className="text-sm font-semibold text-muted-foreground">/{pricingInterval === 'monthly' ? 'mo' : 'yr'}</span>
              </div>
              <p className="text-[11px] text-muted-foreground">{proQuote ? `+ ${Math.round(proQuote.gst_rate * 100)}% GST · ` : ''}for {pricingLocations} {pricingLocations === 1 ? 'location' : 'locations'}</p>
            </div>
            <button onClick={handleContinueWithGoogle} disabled={loading} className="flex items-center justify-center gap-2 rounded-lg bg-primary px-5 py-3 text-xs font-bold uppercase tracking-widest text-primary-foreground shadow transition-colors hover:bg-primary/90 disabled:opacity-50">Start Free Trial</button>
            <ul className="space-y-2.5 border-t border-primary/20 pt-5 text-xs font-semibold text-foreground">
              {['Everything in Basic, plus:', `${proQuote ? proQuote.monthly_ai_credits.toLocaleString('en-IN') : pricingLocations * 45} AI credits / month`, '45 AI credits per location', 'Local Rank heatmaps (geo-grid)', 'Lead-capture microsites', 'Location leaderboard + cohort ranking', 'Search intelligence'].map((t, i) => (
                <li key={t} className="flex items-center gap-2">{i === 0 ? <Sparkles className="h-3.5 w-3.5 shrink-0 text-primary" /> : <Check className="h-3.5 w-3.5 shrink-0 text-primary" />}{t}</li>
              ))}
            </ul>
          </div>

          {/* ENTERPRISE */}
          <div className="flex flex-col justify-between gap-5 rounded-2xl border border-border bg-card p-8 shadow-sm">
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
              <MessageCircle className="h-4 w-4" /> Chat on WhatsApp
            </a>
          </div>
        </div>

        <p className="text-center text-[11px] text-muted-foreground">7-day free trial · 3 locations · 10 AI credits included. No credit card required.</p>
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
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">Start syncing your storefronts today</h2>
            <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">Join local SEO directors, franchise owners, and agency operators who have abandoned manual spreadsheets. Connect your locations and start automating.</p>
            <div className="flex justify-center pt-6">
              <button onClick={handleContinueWithGoogle} disabled={loading} className="flex items-center justify-center gap-3 rounded-lg border border-gray-200 bg-white px-6 py-3.5 text-sm font-bold text-gray-950 shadow-lg transition-colors hover:bg-gray-50 disabled:opacity-50">
                {loading ? <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent" /> : <><GoogleIcon /> Continue with Google</>}
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

      {/* Floating WhatsApp button — bottom-right on mobile and desktop */}
      <a
        href="https://wa.me/917021052482?text=Hi%2C%20I%27d%20like%20to%20know%20more%20about%20Pinzo."
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Chat with us on WhatsApp"
        className="group fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-lg shadow-black/20 transition-transform hover:scale-105 active:scale-95 sm:bottom-6 sm:right-6"
      >
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#25D366] opacity-30" />
        <svg viewBox="0 0 24 24" className="relative h-7 w-7 fill-current" aria-hidden>
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.999-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z" />
        </svg>
      </a>
    </div>
  )
}
