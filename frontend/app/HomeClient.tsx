'use client'

import { useState, useEffect } from 'react'
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
  Lock, 
  BarChart2, 
  Settings, 
  Sparkles, 
  Building, 
  Clock, 
  ChevronDown, 
  CheckCircle2,
  AlertCircle,
  MessageCircle,
  Plug,
  LayoutDashboard,
  ShieldCheck,
  KeyRound,
  CreditCard,
  XCircle
} from 'lucide-react'
import { useQuote } from '@/hooks/useBilling'

// Honest "built for" segments — we lead with who the product is designed for
// instead of fabricated customer logos while we are at MVP stage.
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
  const [activeTab, setActiveTab] = useState<'reviews' | 'analytics' | 'posts'>('reviews')
  const [openFaq, setOpenFaq] = useState<number | null>(null)

  // Live, server-authoritative pricing for the homepage calculator. Uses the same
  // public /billing/quote endpoint as in-app checkout, so the homepage price can
  // never drift from what the user is actually charged.
  const [pricingLocations, setPricingLocations] = useState<number>(5)
  const [pricingInterval, setPricingInterval] = useState<'monthly' | 'annual'>('monthly')
  const { data: pricingQuote } = useQuote(pricingLocations, pricingInterval, true)

  // Redirect if already authenticated
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

  // Smooth scroll helper
  const scrollToSection = (id: string) => {
    setMobileMenuOpen(false)
    const element = document.getElementById(id)
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="relative min-h-screen overflow-x-hidden bg-background text-foreground font-sans selection:bg-primary/30 selection:text-foreground">
      {/* Background radial highlight */}
      <div className="absolute top-0 left-1/2 -z-10 h-[1000px] w-full max-w-[1440px] -translate-x-1/2 bg-[radial-gradient(circle_at_50%_0%,rgba(0,0,0,0.03)_0%,rgba(0,0,0,0.01)_30%,rgba(0,0,0,0)_70%)] pointer-events-none" />
      
      {/* 1. NAVBAR */}
      <header className="sticky top-0 z-50 w-full border-b border-border/80 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          {/* Brand Logo */}
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <img
              src="/logo-horizontal-3.png"
              alt="Pinzo"
              className="h-8 object-contain shrink-0"
            />
          </div>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-6">
            <button onClick={() => scrollToSection('how')} className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
              How it works
            </button>
            <button onClick={() => scrollToSection('features')} className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
              Features
            </button>
            <button onClick={() => scrollToSection('showcase')} className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
              Analytics
            </button>
            <button onClick={() => scrollToSection('pricing')} className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
              Pricing
            </button>
            <button onClick={() => scrollToSection('faq')} className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
              FAQ
            </button>
          </nav>

          {/* Action CTAs */}
          <div className="hidden md:flex items-center gap-4">
            <button 
              onClick={handleContinueWithGoogle}
              disabled={loading}
              className="text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            >
              Login
            </button>
            
            <button
              onClick={handleContinueWithGoogle}
              disabled={loading}
              className="flex items-center gap-2 rounded-lg py-2 px-4 text-xs font-bold uppercase tracking-widest text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50 shadow-sm cursor-pointer"
            >
              {loading ? (
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent"></div>
              ) : (
                <>
                  <svg className="h-4 w-4 shrink-0" viewBox="0 0 24 24">
                    <path fill="currentColor" d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114A5.99 5.99 0 0 1 8 12.5a5.99 5.99 0 0 1 5.99-6.015c1.474 0 2.812.538 3.854 1.424l3.22-3.22A10.93 10.93 0 0 0 13.99 2 10.99 10.99 0 0 0 3 13c0 6.075 4.925 11 10.99 11 5.753 0 10.457-4.143 10.94-9.673H12.24Z" />
                  </svg>
                  Continue with Google
                </>
              )}
            </button>
          </div>

          {/* Mobile Menu Icon */}
          <button 
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="flex md:hidden h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
          >
            {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </header>

      {/* Mobile Menu Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 top-16 z-40 w-full bg-background/95 backdrop-blur-lg border-b border-border md:hidden animate-in fade-in duration-200">
          <div className="flex flex-col gap-6 p-6">
            <button onClick={() => scrollToSection('how')} className="text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground py-2 border-b border-border/50">
              How it works
            </button>
            <button onClick={() => scrollToSection('features')} className="text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground py-2 border-b border-border/50">
              Features
            </button>
            <button onClick={() => scrollToSection('showcase')} className="text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground py-2 border-b border-border/50">
              Analytics & Showcases
            </button>
            <button onClick={() => scrollToSection('pricing')} className="text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground py-2 border-b border-border/50">
              Pricing
            </button>
            <button onClick={() => scrollToSection('faq')} className="text-left text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground py-2 border-b border-border/50">
              FAQ
            </button>
            
            <div className="flex flex-col gap-3 pt-4">
              {error && (
                <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs font-semibold text-red-400">
                  {error}
                </div>
              )}
              
              <button
                onClick={handleContinueWithGoogle}
                disabled={loading}
                className="w-full flex justify-center items-center gap-3 rounded-lg py-3 px-4 text-sm font-semibold bg-white hover:bg-gray-50 border border-gray-200 text-gray-950 shadow-sm cursor-pointer disabled:opacity-50 transition-colors"
              >
                {loading ? (
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent"></div>
                ) : (
                  <>
                    <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24">
                      <path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114A5.99 5.99 0 0 1 8 12.5a5.99 5.99 0 0 1 5.99-6.015c1.474 0 2.812.538 3.854 1.424l3.22-3.22A10.93 10.93 0 0 0 13.99 2 10.99 10.99 0 0 0 3 13c0 6.075 4.925 11 10.99 11 5.753 0 10.457-4.143 10.94-9.673H12.24Z" />
                      <path fill="#FBBC05" d="M13.99 2a10.93 10.93 0 0 0-7.045 2.58l3.22 3.22A5.99 5.99 0 0 1 13.99 5.985V2Z" />
                      <path fill="#34A853" d="M3 13c0 2.215.656 4.275 1.785 6.015l3.22-3.22A5.99 5.99 0 0 1 8 12.5c0-1.282.4-2.472 1.085-3.465L5.865 5.815A10.93 10.93 0 0 0 3 13Z" />
                      <path fill="#4285F4" d="M13.99 24c3.045 0 5.81-1.233 7.82-3.225l-3.22-3.22A5.99 5.99 0 0 1 13.99 18.5a5.99 5.99 0 0 1-5.99-6.015c0-.46.057-.905.158-1.332L4.938 7.913A10.97 10.97 0 0 0 13.99 24Z" />
                    </svg>
                    Continue with Google
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. HERO SECTION */}
      <section className="mx-auto max-w-7xl px-4 pt-16 pb-12 sm:px-6 lg:px-8 lg:pt-24 text-center">
        <div className="mx-auto max-w-4xl space-y-6">
          {/* Badge */}
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Operational Engine for Multi-Location GMB SEO</span>
          </div>

          {/* Main Title */}
          <h1 className="text-4xl font-extrabold tracking-tight text-foreground sm:text-5xl lg:text-6xl font-sans">
            Manage Every Google Business Profile <br />
            <span className="text-primary">
              From One Dashboard
            </span>
          </h1>

          {/* Description */}
          <p className="mx-auto max-w-2xl text-base text-muted-foreground sm:text-lg">
            Centralize customer reviews with AI-assisted replies, schedule Google Posts across every location, track multi-location analytics, run profile audits, and manage your team&apos;s access &mdash; all from one secure dashboard. Built for agencies, franchises, and multi-location operators.
          </p>

          {/* CTAs */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
            <button
              onClick={handleContinueWithGoogle}
              disabled={loading}
              className="w-full sm:w-auto min-w-[220px] flex items-center justify-center gap-3 rounded-lg py-3.5 px-6 text-sm font-semibold bg-white hover:bg-gray-50 border border-gray-200 text-gray-950 shadow-lg cursor-pointer disabled:opacity-50 transition-colors"
            >
              {loading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent"></div>
              ) : (
                <>
                  <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24">
                    <path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114A5.99 5.99 0 0 1 8 12.5a5.99 5.99 0 0 1 5.99-6.015c1.474 0 2.812.538 3.854 1.424l3.22-3.22A10.93 10.93 0 0 0 13.99 2 10.99 10.99 0 0 0 3 13c0 6.075 4.925 11 10.99 11 5.753 0 10.457-4.143 10.94-9.673H12.24Z" />
                    <path fill="#FBBC05" d="M13.99 2a10.93 10.93 0 0 0-7.045 2.58l3.22 3.22A5.99 5.99 0 0 1 13.99 5.985V2Z" />
                    <path fill="#34A853" d="M3 13c0 2.215.656 4.275 1.785 6.015l3.22-3.22A5.99 5.99 0 0 1 8 12.5c0-1.282.4-2.472 1.085-3.465L5.865 5.815A10.93 10.93 0 0 0 3 13Z" />
                    <path fill="#4285F4" d="M13.99 24c3.045 0 5.81-1.233 7.82-3.225l-3.22-3.22A5.99 5.99 0 0 1 13.99 18.5a5.99 5.99 0 0 1-5.99-6.015c0-.46.057-.905.158-1.332L4.938 7.913A10.97 10.97 0 0 0 13.99 24Z" />
                  </svg>
                  <span className="font-bold text-gray-950">Continue with Google</span>
                </>
              )}
            </button>
            
            <button
              onClick={() => scrollToSection('pricing')}
              className="w-full sm:w-auto min-w-[160px] flex items-center justify-center gap-2 rounded-lg py-3.5 px-6 text-sm font-semibold bg-muted/30 border border-border text-muted-foreground hover:text-white hover:bg-muted/50 transition-all transition-colors"
            >
              <span>View Pricing</span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          {error && (
            <div className="mx-auto max-w-md rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs font-semibold text-red-400">
              {error}
            </div>
          )}

          {/* Security & trust strip */}
          <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2.5 pt-4 text-[11px] font-semibold text-muted-foreground">
            {[
              { icon: KeyRound, label: 'Secure Google OAuth, we never see your password' },
              { icon: ShieldCheck, label: 'Tokens encrypted at rest' },
              { icon: CreditCard, label: 'No credit card for trial' },
              { icon: XCircle, label: 'Cancel anytime' },
            ].map((item, idx) => (
              <span key={idx} className="inline-flex items-center gap-1.5">
                <item.icon className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                {item.label}
              </span>
            ))}
          </div>
        </div>

        {/* 3. HERO VISUAL - SaaS Dashboard Preview */}
        <div className="mt-16 relative mx-auto max-w-6xl rounded-2xl border border-border bg-card shadow-sm p-4 sm:p-6 lg:p-8 overflow-hidden">
          
          {/* Dashboard Frame Header */}
          <div className="flex items-center justify-between border-b border-border pb-4 mb-6">
            <div className="flex items-center gap-2">
              <div className="flex gap-1.5">
                <span className="w-3 h-3 rounded-full bg-red-500/60" />
                <span className="w-3 h-3 rounded-full bg-yellow-500/60" />
                <span className="w-3 h-3 rounded-full bg-green-500/60" />
              </div>
              <div className="h-4 w-px bg-border mx-2" />
              <div className="flex items-center gap-1 bg-muted/40 border border-border/80 px-2 py-0.5 rounded text-[10px] text-muted-foreground font-mono">
                <Lock className="w-3 h-3" /> pinzo.com/dashboard
              </div>
            </div>
            <div className="flex gap-2">
              <span className="h-2 w-12 rounded bg-muted/40" />
              <span className="h-2 w-16 rounded bg-muted/40" />
            </div>
          </div>

          {/* Actual Mock Dashboard Content */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 text-left">
            {/* Sidebar */}
            <div className="hidden lg:flex flex-col gap-4 border-r border-border pr-6">
              <div className="p-3 bg-primary/10 border border-primary/20 rounded-lg flex items-center gap-3">
                <div className="h-8 w-8 rounded-md bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm">
                  G
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-foreground">Gourmet Burger LLC</span>
                  <span className="text-[10px] text-primary font-semibold uppercase tracking-wider">12 Locations Active</span>
                </div>
              </div>

              <div className="space-y-1">
                {[
                  { label: 'Overview', icon: BarChart2, active: true },
                  { label: 'Locations Directory', icon: MapPin },
                  { label: 'Reviews Inbox', icon: MessageSquare, badge: '5 New' },
                  { label: 'Google Posts Schedule', icon: Calendar },
                  { label: 'Reputation Audits', icon: Shield },
                  { label: 'Team Settings', icon: Settings },
                ].map((item, idx) => (
                  <div 
                    key={idx} 
                    className={`flex items-center justify-between p-2.5 rounded-lg text-xs font-semibold cursor-pointer transition-colors ${
                      item.active ? 'bg-primary/10 border border-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <item.icon className="h-4 w-4 shrink-0" />
                      <span>{item.label}</span>
                    </div>
                    {item.badge && (
                      <span className="px-1.5 py-0.5 rounded-full bg-primary/20 text-[9px] text-primary font-bold border border-primary/30">
                        {item.badge}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Dashboard Workspace */}
            <div className="lg:col-span-3 space-y-6">
              {/* Metric Row */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {[
                  { title: 'Global Rating', value: '4.8 ★', label: '+0.2 this month', color: 'text-amber-400' },
                  { title: 'Total Reviews Sync', value: '1,482', label: '14 pending approval', color: 'text-indigo-400' },
                  { title: 'Local Search Volume', value: '98.4K', label: '+18.2% vs last month', color: 'text-emerald-400' },
                ].map((stat, idx) => (
                  <div key={idx} className="p-4 rounded-xl border border-border bg-muted/10 flex flex-col gap-1.5">
                    <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">{stat.title}</span>
                    <span className={`text-2xl font-bold ${stat.color}`}>{stat.value}</span>
                    <span className="text-[10px] text-muted-foreground/80 font-semibold">{stat.label}</span>
                  </div>
                ))}
              </div>

              {/* Main Preview Container with tabs */}
              <div className="border border-border rounded-xl bg-background overflow-hidden">
                <div className="flex border-b border-border bg-muted/30 p-2">
                  {(['reviews', 'analytics', 'posts'] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveTab(tab)}
                      className={`px-4 py-2 text-xs font-bold uppercase tracking-wider rounded-lg transition-all ${
                        activeTab === tab ? 'bg-primary border border-primary/30 text-primary-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {tab}
                    </button>
                  ))}
                </div>

                <div className="p-4 sm:p-6 min-h-[260px] flex flex-col justify-between">
                  {activeTab === 'reviews' && (
                    <div className="space-y-4">
                      {/* Review Card 1 */}
                      <div className="p-3.5 rounded-lg border border-border bg-card flex flex-col gap-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="h-6 w-6 rounded-full bg-primary/20 flex items-center justify-center text-[10px] font-bold text-primary">AM</span>
                            <span className="text-xs font-bold text-foreground">Austin Miller</span>
                            <span className="text-[10px] text-muted-foreground">• Downtown Branch</span>
                          </div>
                          <div className="flex items-center gap-0.5 text-amber-400">
                            {[...Array(5)].map((_, i) => <Star key={i} className="h-3.5 w-3.5 fill-current" />)}
                          </div>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          &quot;Outstanding service! Ordered the Classic Truffle Burger and the fries were super crispy. The staff were very helpful and GMB directions were precise.&quot;
                        </p>
                        <div className="flex items-center gap-2 mt-1 border-t border-border pt-2.5">
                          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-primary/20">
                            <Sparkles className="h-3 w-3 text-primary" />
                          </div>
                          <span className="text-[10px] font-bold text-primary uppercase tracking-wide">Suggested AI Draft:</span>
                          <span className="text-[10px] text-muted-foreground truncate max-w-sm">&quot;Hi Austin, thank you for your kind words! We are thrilled...&quot;</span>
                          <button className="ml-auto text-[10px] font-extrabold uppercase bg-primary text-primary-foreground px-2 py-1 rounded border border-primary">
                            Approve Reply
                          </button>
                        </div>
                      </div>

                      {/* Review Card 2 */}
                      <div className="p-3.5 rounded-lg border border-border bg-card flex flex-col gap-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="h-6 w-6 rounded-full bg-purple-500/20 flex items-center justify-center text-[10px] font-bold text-purple-600">SD</span>
                            <span className="text-xs font-bold text-foreground">Sarah Davis</span>
                            <span className="text-[10px] text-muted-foreground">• Westside Plaza</span>
                          </div>
                          <div className="flex items-center gap-0.5 text-amber-400">
                            {[...Array(4)].map((_, i) => <Star key={i} className="h-3.5 w-3.5 fill-current" />)}
                          </div>
                        </div>
                        <p className="text-xs text-muted-foreground leading-relaxed">
                          &quot;Great location, easy to locate parking. Food was delicious but service was slightly slow on a Friday afternoon.&quot;
                        </p>
                      </div>
                    </div>
                  )}

                  {activeTab === 'analytics' && (
                    <div className="space-y-4">
                      {/* Custom SVG Performance Graph */}
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-bold text-foreground">Local Action Conversions (Clicks, Calls, Directions)</span>
                        <span className="text-[10px] text-muted-foreground font-mono">Last 30 Days vs Prior</span>
                      </div>
                      <div className="h-36 w-full flex items-end gap-1.5 border-b border-l border-border pb-1.5 pl-1.5 relative">
                        {/* SVG Line / Bars */}
                        {[35, 42, 38, 55, 68, 74, 62, 85, 98, 110, 105, 120, 115, 135].map((val, i) => (
                          <div key={i} className="flex-1 flex flex-col items-center gap-1 group/bar">
                            <div className="w-full bg-gradient-to-t from-primary/20 to-primary rounded-t-sm transition-all" style={{ height: `${(val / 150) * 100}px` }} />
                            <span className="text-[8px] text-muted-foreground font-mono hidden sm:inline">{i * 2 + 1} Jun</span>
                          </div>
                        ))}
                      </div>
                      <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
                        <span>Jun 1</span>
                        <span>Jun 15</span>
                        <span>Jun 30</span>
                      </div>
                    </div>
                  )}

                  {activeTab === 'posts' && (
                    <div className="space-y-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-bold text-foreground">Upcoming Post Schedule</span>
                        <button className="text-[10px] font-extrabold uppercase bg-muted/40 border border-border px-2 py-1 rounded hover:text-foreground">
                          Schedule New
                        </button>
                      </div>
                      
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                        <div className="p-3.5 rounded-lg border border-border bg-card flex flex-col gap-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[9px] uppercase font-bold tracking-widest text-primary">Offer Post</span>
                            <span className="text-[10px] text-muted-foreground">In 2 days • 12 Locations</span>
                          </div>
                          <span className="text-xs font-bold text-foreground">Summer Special: 20% Off Burgers</span>
                          <p className="text-[11px] text-muted-foreground line-clamp-2">
                            &quot;Beat the heat with our special Summer burger combo! Use code SUMMER20 on pickup or show this post in store...&quot;
                          </p>
                          <div className="flex items-center justify-between border-t border-border/50 pt-2 mt-1">
                            <span className="text-[10px] text-muted-foreground font-mono">Button: Order Online</span>
                            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-[9px] text-emerald-400 font-semibold">
                              Ready
                            </span>
                          </div>
                        </div>

                        <div className="p-3.5 rounded-lg border border-border bg-card flex flex-col gap-2">
                          <div className="flex items-center justify-between">
                            <span className="text-[9px] uppercase font-bold tracking-widest text-purple-600">Update Post</span>
                            <span className="text-[10px] text-muted-foreground">In 5 days • 4 Locations</span>
                          </div>
                          <span className="text-xs font-bold text-foreground">Westside Store Hours Update</span>
                          <p className="text-[11px] text-muted-foreground line-clamp-2">
                            &quot;Starting next Monday, our Westside location will open until 11:00 PM every Friday and Saturday to serve...&quot;
                          </p>
                          <div className="flex items-center justify-between border-t border-border/50 pt-2 mt-1">
                            <span className="text-[10px] text-muted-foreground font-mono">Button: Call Now</span>
                            <span className="px-1.5 py-0.5 rounded bg-emerald-500/10 border border-emerald-500/30 text-[9px] text-emerald-400 font-semibold">
                              Ready
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Operational Footer Bar */}
                  <div className="border-t border-border/80 pt-4 mt-6 flex items-center justify-between text-[11px] text-muted-foreground font-semibold">
                    <div className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                      <span>Live: syncing 12/12 locations</span>
                    </div>
                    <span>via Google Business Profile API</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 3. SOCIAL PROOF / BUILT FOR */}
      <section className="border-t border-b border-border/40 bg-muted/5 py-10">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 text-center space-y-6">
          <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground/70">
            Purpose-built for teams that manage local presence at scale
          </p>
          <div className="flex flex-wrap items-center justify-center gap-x-10 gap-y-6">
            {BUILT_FOR.map((segment, idx) => (
              <div key={idx} className="flex items-center gap-2 text-muted-foreground">
                <segment.icon className="h-5 w-5 text-primary" />
                <span className="text-sm font-bold tracking-tight">{segment.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3b. HOW IT WORKS */}
      <section id="how" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 space-y-12 scroll-mt-20">
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold text-primary uppercase tracking-wider">
            Get Started in Minutes
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            How Pinzo Works
          </h2>
          <p className="text-muted-foreground">
            No passwords shared, no manual exports. Connect once and manage every Google Business Profile from a single secure workspace.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {[
            {
              step: '01',
              title: 'Connect with Google',
              desc: 'Sign in with secure Google OAuth and grant access to your Business Profile locations. We never see or store your password, only encrypted, revocable tokens.',
              icon: Plug,
            },
            {
              step: '02',
              title: 'We sync your locations',
              desc: 'Your locations, reviews, ratings, and performance metrics are pulled in automatically and kept up to date in the background.',
              icon: RefreshCw,
            },
            {
              step: '03',
              title: 'Manage from one dashboard',
              desc: 'Reply to reviews with AI assistance, schedule Google Posts, run profile audits, and track analytics across every location, with team roles and SLA tracking.',
              icon: LayoutDashboard,
            },
          ].map((item, idx) => (
            <div key={idx} className="relative p-6 rounded-xl border border-border bg-card flex flex-col gap-4 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                  <item.icon className="h-5 w-5 text-primary" />
                </div>
                <span className="text-2xl font-extrabold text-muted-foreground/20">{item.step}</span>
              </div>
              <h3 className="text-sm font-bold text-foreground">{item.title}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 4. FEATURES GRID */}
      <section id="features" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 space-y-12 scroll-mt-20">
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            Complete Command Center for Google Business Profile
          </h2>
          <p className="text-muted-foreground">
            Everything your SEO, agency, or management team needs to dominate local search rankings without logging into twelve different Google dashboards.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[
            {
              title: 'Unified Review Inbox',
              desc: 'Consolidate every Google review from all your locations into a single searchable inbox. Reply, track status, and never miss a customer again.',
              icon: MessageSquare,
            },
            {
              title: 'AI Review Replies',
              desc: 'Generate precise, context-aware responses with AI that matches your brand tone. Review and approve each suggested reply in one click.',
              icon: Sparkles,
            },
            {
              title: 'Sentiment Analysis',
              desc: 'Every review is automatically classified by sentiment and issue type, so you can spot recurring problems and prioritize what matters.',
              icon: Activity,
            },
            {
              title: 'Multi-Location Analytics',
              desc: 'Track Maps direction clicks, calls, website actions, and search views over time, across one location or hundreds.',
              icon: BarChart2,
            },
            {
              title: 'Google Posts Scheduler',
              desc: 'Schedule promotions, updates, and events across multiple locations at once, with call-to-action buttons and paced publishing.',
              icon: Calendar,
            },
            {
              title: 'Team Roles & Permissions (RBAC)',
              desc: 'Give store managers, regional leads, or clients scoped access to only their locations, without ever sharing Google credentials.',
              icon: Users,
            },
            {
              title: 'GMB Profile Audits',
              desc: 'Automated health checks surface NAP discrepancies, missing fields, and optimization gaps that hurt your local visibility.',
              icon: Shield,
            },
            {
              title: 'SLA Tracking',
              desc: 'Set response-time targets for reviews and track them per location, so your team stays accountable and customers stay happy.',
              icon: Clock,
            },
            {
              title: 'Listing Profile Editing',
              desc: 'Update business details across locations through a moderated, audited edit workflow, with full history of every change.',
              icon: RefreshCw,
            },
          ].map((feat, idx) => (
            <div key={idx} className="p-6 rounded-xl border border-border bg-card hover:bg-card/80 flex flex-col gap-3 shadow-sm transition-shadow">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                <feat.icon className="h-5 w-5 text-primary" />
              </div>
              <h3 className="text-sm font-bold text-foreground">{feat.title}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{feat.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* 5. MULTI-LOCATION SYNC DETAIL */}
      <section id="showcase" className="border-t border-border/30 bg-muted/30 py-20 scroll-mt-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold text-primary uppercase tracking-wider">
              Bulk Location Sync
            </div>
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
              One Edit. Synchronized Everywhere.
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              Updating holiday hours or telephone lines shouldn&apos;t mean logging in and out of multiple Google accounts. With Pinzo, push edits to your storefronts from one place, through a moderated, fully audited workflow.
            </p>

            <ul className="space-y-3 font-semibold text-xs text-muted-foreground">
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Edit business details across locations from a single dashboard</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Moderated edit workflow with full change history</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Role-based access prevents unauthorized profile changes</span>
              </li>
            </ul>
          </div>

          {/* Sync Visual Cards */}
          <div className="space-y-4 relative">
            <div className="p-4 rounded-xl border border-border bg-card shadow-sm relative flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center font-bold text-primary">
                  01
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-foreground">Eastside Burger Diner</span>
                  <span className="text-[10px] text-muted-foreground">142 Broadway St, NY</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[9px] text-emerald-400 font-extrabold uppercase tracking-widest">
                Synced
              </span>
            </div>

            <div className="p-4 rounded-xl border border-border bg-card shadow-sm relative flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-primary/20 flex items-center justify-center font-bold text-primary">
                  02
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-foreground">Westside Burger Bar</span>
                  <span className="text-[10px] text-muted-foreground">882 Sunset Blvd, LA</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-[9px] text-emerald-400 font-extrabold uppercase tracking-widest">
                Synced
              </span>
            </div>

            <div className="p-4 rounded-xl border border-primary/40 bg-primary/5 shadow-sm relative flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-lg bg-primary flex items-center justify-center font-bold text-primary-foreground animate-spin">
                  <RefreshCw className="h-4 w-4" />
                </div>
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-foreground">Downtown Diner Hub</span>
                  <span className="text-[10px] text-muted-foreground">Pushing updated menu link...</span>
                </div>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-primary/20 border border-primary/30 text-[9px] text-primary font-extrabold uppercase tracking-widest animate-pulse">
                Updating
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 6. REVIEWS MANAGEMENT DETAIL */}
      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
        {/* Sync Visual Cards */}
        <div className="order-2 lg:order-1 space-y-4">
          <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-border/50 pb-3">
              <div className="flex items-center gap-2">
                <span className="h-3 w-3 rounded-full bg-primary" />
                <span className="text-xs font-bold text-foreground">Pending Approval (Westside Store)</span>
              </div>
              <span className="text-[10px] text-muted-foreground">Received 10m ago</span>
            </div>
            
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-foreground">Marcus Vance</span>
                <span className="text-[10px] text-muted-foreground">Local Guide</span>
              </div>
              <div className="flex items-center text-amber-400 gap-0.5">
                {[...Array(5)].map((_, i) => <Star key={i} className="h-3 w-3 fill-current" />)}
              </div>
            </div>

            <p className="text-xs text-muted-foreground italic leading-relaxed">
              &quot;Best burger combination in town! Service was fast, and location was very tidy. Highly recommended.&quot;
            </p>

            <div className="bg-muted/30 border border-border p-3.5 rounded-lg space-y-2">
              <div className="flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                <span className="text-[10px] font-bold text-primary uppercase tracking-wide">AI Recommended Response</span>
              </div>
              <p className="text-xs text-foreground leading-normal">
                &quot;Hi Marcus, thank you so much for the 5-star review! We&apos;re glad you enjoyed the burgers and quick service at our Westside location. Hope to see you again soon!&quot;
              </p>
              <div className="flex gap-2 justify-end pt-2">
                <button className="text-[10px] font-bold uppercase text-muted-foreground hover:text-foreground px-2.5 py-1.5 rounded border border-border bg-transparent">
                  Edit Response
                </button>
                <button className="text-[10px] font-extrabold uppercase text-primary-foreground px-3 py-1.5 rounded bg-primary hover:bg-primary/90 border border-primary">
                  Publish Answer
                </button>
              </div>
            </div>
          </div>
        </div>

        <div className="order-1 lg:order-2 space-y-6">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold text-primary uppercase tracking-wider">
            Reputation Management
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            Automate Response Loops With AI
          </h2>
          <p className="text-muted-foreground leading-relaxed">
            Reviews are a key local SEO ranking factor. Respond to reviews instantly using brand-specific AI templates. Ensure you never leave a client, customer, or local guide hanging.
          </p>

          <ul className="space-y-3 font-semibold text-xs text-muted-foreground">
            <li className="flex items-center gap-2">
              <Check className="h-4 w-4 text-emerald-400 shrink-0" />
              <span>Automatic sentiment &amp; issue tagging for every 1&ndash;5 star review</span>
            </li>
            <li className="flex items-center gap-2">
              <Check className="h-4 w-4 text-emerald-400 shrink-0" />
              <span>AI drafts that match your brand tone &mdash; approve before publishing</span>
            </li>
            <li className="flex items-center gap-2">
              <Check className="h-4 w-4 text-emerald-400 shrink-0" />
              <span>SLA tracking so no review goes unanswered past your target</span>
            </li>
          </ul>
        </div>
      </section>

      {/* 7. GOOGLE POSTS SCHEDULER DETAIL */}
      <section className="border-t border-border/30 bg-muted/10 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="space-y-6">
            <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold text-primary uppercase tracking-wider">
              Marketing Scheduler
            </div>
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
              Keep Your Storefronts Active with Posts
            </h2>
            <p className="text-muted-foreground leading-relaxed">
              Google rewards active profiles. Schedule promotions, holiday updates, event details, and product releases natively. Scale your content distribution without manual logging.
            </p>

            <ul className="space-y-3 font-semibold text-xs text-muted-foreground">
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Configure CTA buttons (Order, Learn More, Call Now, Book)</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Publish one campaign across many locations at once</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-400 shrink-0" />
                <span>Paced, jitter-aware scheduling that respects Google&apos;s limits</span>
              </li>
            </ul>
          </div>

          {/* Posts Mock Scheduler Grid */}
          <div className="p-5 rounded-xl border border-border bg-card shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-border/50 pb-3">
              <span className="text-xs font-bold text-foreground">Post Campaign Queue</span>
              <span className="text-[10px] text-muted-foreground">3 Active Campaigns</span>
            </div>
            
            <div className="space-y-3">
              {[
                { title: 'Promo: Buy 1 Get 1 Free Shake', locations: 'All Stores (12 Locations)', date: 'June 10th - June 15th', type: 'Offer' },
                { title: 'Update: New Summer Dining Hours', locations: 'Downtown Diner Only', date: 'June 18th - Permanent', type: 'Update' },
                { title: 'Product Launch: Smokey Bacon Classic', locations: 'All Stores (12 Locations)', date: 'June 22nd - July 30th', type: 'What\'s New' },
              ].map((campaign, idx) => (
                <div key={idx} className="p-3 rounded-lg border border-border/80 bg-muted/10 flex items-center justify-between gap-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-bold text-white">{campaign.title}</span>
                    <div className="flex flex-wrap items-center gap-x-2 text-[10px] text-muted-foreground">
                      <span>{campaign.locations}</span>
                      <span>•</span>
                      <span>{campaign.date}</span>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1.5 shrink-0">
                    <span className="px-2 py-0.5 rounded bg-indigo-500/10 border border-indigo-500/30 text-[9px] text-indigo-400 font-extrabold uppercase tracking-wide">
                      {campaign.type}
                    </span>
                    <span className="text-[8px] text-muted-foreground font-mono">Scheduled</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 8. AI INSIGHTS / REPUTATION SECTION */}
      <section className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 space-y-12">
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3 py-1 text-[11px] font-bold text-primary uppercase tracking-wider">
            SEO Audits
          </div>
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            Intelligent GMB Optimization & Health Checks
          </h2>
          <p className="text-muted-foreground">
            Get automated audit checks that detect incorrect coordinates, NAP discrepancies (Name, Address, Phone), and missing optimization tags across maps.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8 items-stretch">
          <div className="p-6 rounded-xl border border-border bg-card flex flex-col gap-4 shadow-sm">
            <h3 className="text-sm font-bold text-foreground flex items-center gap-2">
              <CheckCircle2 className="h-5 w-5 text-emerald-500" />
              <span>Recommended Optimization Actions</span>
            </h3>
            
            <div className="space-y-3 flex-1">
              {[
                { location: 'Downtown Store', msg: 'Missing store description tag. Fix to boost local visibility.', category: 'SEO' },
                { location: 'Eastside Diner', msg: 'Website URL link returns 404. Update to avoid profile suspension.', category: 'Critical' },
                { location: 'Westside Diner', msg: 'No customer posts uploaded in last 30 days.', category: 'Engagement' },
              ].map((item, idx) => (
                <div key={idx} className="p-3.5 rounded-lg border border-border/80 bg-muted/30 flex items-start justify-between gap-3 text-xs">
                  <div className="space-y-1">
                    <span className="font-bold text-foreground text-[11px]">{item.location}</span>
                    <p className="text-muted-foreground text-[11px]">{item.msg}</p>
                  </div>
                  <span className={`px-1.5 py-0.5 rounded text-[8px] font-bold uppercase tracking-wider ${
                    item.category === 'Critical' ? 'bg-red-500/10 border border-red-500/30 text-red-600' : 'bg-primary/10 border border-primary/30 text-primary'
                  }`}>
                    {item.category}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div className="p-6 rounded-xl border border-border bg-card shadow-sm flex flex-col justify-between gap-6">
            <div className="space-y-3">
              <h3 className="text-sm font-bold text-foreground">Local Audit Results</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Dominating your local pack requires constant consistency checks. Pinzo continuously crawls your business coordinates against multiple indexes to flag discrepancies.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-4 text-center">
              <div className="p-3 rounded-lg border border-border/80 bg-muted/30">
                <span className="text-xl font-bold text-foreground font-mono">98%</span>
                <p className="text-[10px] text-muted-foreground/80 mt-1 uppercase font-bold tracking-wider">Consistency</p>
              </div>
              <div className="p-3 rounded-lg border border-border/80 bg-muted/30">
                <span className="text-xl font-bold text-foreground font-mono">1.2K</span>
                <p className="text-[10px] text-muted-foreground/80 mt-1 uppercase font-bold tracking-wider">Indexed Citations</p>
              </div>
              <div className="p-3 rounded-lg border border-border/80 bg-muted/30">
                <span className="text-xl font-bold text-foreground font-mono">0</span>
                <p className="text-[10px] text-muted-foreground/80 mt-1 uppercase font-bold tracking-wider">Pending Suspensions</p>
              </div>
            </div>

            <div className="flex items-center gap-2 rounded-lg bg-emerald-500/5 border border-emerald-500/20 p-3.5 text-[11px] font-semibold text-emerald-400">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>All GMB active locations are currently validated and compliant with Google guidelines.</span>
            </div>
          </div>
        </div>
      </section>

      {/* 9. WHY TEAMS CHOOSE US */}
      <section className="border-t border-border/30 bg-muted/30 py-20">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="text-center max-w-3xl mx-auto space-y-4">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
              Built to Replace the Manual Grind
            </h2>
            <p className="text-muted-foreground">
              Managing Google Business Profiles location-by-location doesn&apos;t scale. Here&apos;s what changes when everything lives in one workspace.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              {
                icon: Clock,
                title: 'Stop logging in and out',
                desc: 'One secure dashboard for every location means no more juggling separate Google accounts to update hours, reply to reviews, or post an update.',
              },
              {
                icon: Sparkles,
                title: 'Answer every review faster',
                desc: 'AI-drafted replies and SLA tracking help your team respond consistently and on time. Review response speed is a real local-ranking signal.',
              },
              {
                icon: ShieldCheck,
                title: 'Keep credentials safe',
                desc: 'Give staff and clients scoped, role-based access to only their locations. No shared passwords, and OAuth tokens are encrypted at rest.',
              },
            ].map((item, idx) => (
              <div key={idx} className="p-6 rounded-xl border border-border bg-card flex flex-col gap-4 shadow-sm">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 border border-primary/20">
                  <item.icon className="h-5 w-5 text-primary" />
                </div>
                <h3 className="text-sm font-bold text-foreground">{item.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 10. PRICING */}
      <section id="pricing" className="mx-auto max-w-7xl px-4 py-20 sm:px-6 lg:px-8 space-y-12 scroll-mt-16">
        <div className="text-center max-w-3xl mx-auto space-y-4">
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            Simple Pricing That Scales With You
          </h2>
          <p className="text-muted-foreground">
            Pay only for the locations you manage. Every location includes AI credits for review replies and posts. Start with a 7-day free trial &mdash; no credit card required.
          </p>
        </div>

        {/* Billing interval toggle */}
        <div className="flex items-center justify-center gap-2">
          <button
            onClick={() => setPricingInterval('monthly')}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-colors ${pricingInterval === 'monthly' ? 'bg-primary text-primary-foreground' : 'bg-muted/30 text-muted-foreground hover:text-foreground'}`}
          >
            Monthly
          </button>
          <button
            onClick={() => setPricingInterval('annual')}
            className={`px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-colors ${pricingInterval === 'annual' ? 'bg-primary text-primary-foreground' : 'bg-muted/30 text-muted-foreground hover:text-foreground'}`}
          >
            Yearly <span className="text-emerald-400">&middot; Save 20%</span>
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch max-w-5xl mx-auto">
          {/* Self-serve per-location calculator */}
          <div className="lg:col-span-2 p-8 rounded-2xl border-2 border-primary bg-primary/5 flex flex-col gap-6 shadow-md">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase font-bold tracking-widest text-primary">Pay Per Location</span>
              <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">
                {pricingInterval === 'monthly' ? 'Billed monthly' : 'Billed yearly'}
              </span>
            </div>

            {/* Location slider */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-sm font-semibold text-foreground">How many locations?</label>
                <span className="text-sm font-bold text-primary">
                  {pricingLocations} {pricingLocations === 1 ? 'location' : 'locations'}
                </span>
              </div>
              <input
                type="range"
                min={1}
                max={50}
                value={pricingLocations}
                onChange={(e) => setPricingLocations(Number(e.target.value))}
                className="w-full accent-primary cursor-pointer"
                aria-label="Number of locations"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground font-mono">
                <span>1</span>
                <span>50</span>
              </div>
            </div>

            {/* Live price */}
            <div className="flex items-end justify-between border-t border-primary/20 pt-6">
              <div>
                <div className="flex items-baseline gap-1 text-foreground">
                  <span className="text-4xl font-extrabold">
                    {pricingQuote ? `₹${Math.round(pricingQuote.price_paise / 100).toLocaleString('en-IN')}` : '—'}
                  </span>
                  <span className="text-sm font-semibold text-muted-foreground">
                    /{pricingInterval === 'monthly' ? 'mo' : 'yr'}
                  </span>
                </div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  for {pricingLocations} {pricingLocations === 1 ? 'location' : 'locations'}
                </p>
              </div>
              <div className="flex flex-col items-end gap-1.5">
                <button
                  onClick={handleContinueWithGoogle}
                  disabled={loading}
                  className="flex justify-center items-center gap-2 rounded-lg py-3 px-5 text-xs font-bold uppercase tracking-widest bg-primary text-primary-foreground hover:bg-primary/90 shadow cursor-pointer disabled:opacity-50 transition-colors"
                >
                  Start Free Trial
                </button>
                <p className="text-[10px] text-muted-foreground text-right max-w-[200px] leading-snug">
                  Estimate only. Free for 7 days, then{' '}
                  {pricingQuote
                    ? `₹${Math.round(pricingQuote.price_paise / 100).toLocaleString('en-IN')}/${pricingInterval === 'monthly' ? 'mo' : 'yr'}`
                    : 'your plan price'}{' '}
                  for the locations you connect. No card to start.
                </p>
              </div>
            </div>

            {/* What's included */}
            <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs text-foreground font-semibold border-t border-primary/20 pt-6">
              <li className="flex items-center gap-2">
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                <span>{pricingQuote ? pricingQuote.monthly_ai_credits.toLocaleString('en-IN') : pricingLocations * 30} AI credits / month</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                <span>30 AI credits per location</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                <span>Unified review inbox + AI replies</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                <span>Google Posts scheduler</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                <span>Multi-location analytics &amp; audits</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                <span>Team roles &amp; permissions</span>
              </li>
            </ul>

            <p className="text-[11px] text-muted-foreground">
              7-day free trial &middot; 3 locations &middot; 10 AI credits included. No credit card required.
            </p>
          </div>

          {/* Enterprise */}
          <div className="p-8 rounded-2xl border border-border bg-card flex flex-col justify-between gap-6 shadow-sm">
            <div className="space-y-4">
              <span className="text-[10px] uppercase font-bold tracking-widest text-muted-foreground">Enterprise</span>
              <div className="flex items-baseline gap-1 text-foreground">
                <span className="text-3xl font-extrabold">Let&apos;s talk</span>
              </div>
              <p className="text-xs text-muted-foreground">
                Managing 50+ locations or need custom AI credits, onboarding, and support? We&apos;ll tailor a plan to fit.
              </p>
              <div className="h-px bg-border" />
              <ul className="space-y-2.5 text-xs text-muted-foreground font-semibold">
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span>50+ locations</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span>Custom AI credit volume</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span>Priority support &amp; onboarding</span>
                </li>
                <li className="flex items-center gap-2">
                  <Check className="h-3.5 w-3.5 text-primary shrink-0" />
                  <span>Custom invoicing &amp; SLA</span>
                </li>
              </ul>
            </div>
            <a
              href="https://wa.me/917021052482?text=Hi%2C%20I%27m%20interested%20in%20the%20Enterprise%20plan%20for%2050%2B%20locations."
              target="_blank"
              rel="noopener noreferrer"
              className="w-full flex justify-center items-center gap-2 rounded-lg py-3 px-4 text-xs font-bold uppercase tracking-widest border border-border hover:border-foreground text-muted-foreground hover:text-foreground bg-transparent transition-all"
            >
              <MessageCircle className="h-4 w-4" />
              Chat on WhatsApp
            </a>
          </div>
        </div>
      </section>

      {/* 11. FAQ */}
      <section id="faq" className="border-t border-border/30 bg-muted/10 py-20 scroll-mt-16">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 space-y-12">
          <div className="text-center space-y-4">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground">
              Frequently Asked Questions
            </h2>
            <p className="text-muted-foreground">
              Clear answers regarding Google API limits, syncing speeds, and workspace security.
            </p>
          </div>

          <div className="space-y-4">
            {[
              {
                q: "Do I need to give you my Google password?",
                a: "Absolutely not. We authenticate using Google OAuth secure scopes. You simply sign in with Google once and grant read/write access. We never store or see your password."
              },
              {
                q: "How fast do edits update on Google Maps?",
                a: "Updates such as phone numbers, operating hours, and posts are pushed via Google Business Profile API and are typically updated on Google Maps within 2 to 5 minutes."
              },
              {
                q: "Is there a limit to how many locations I can connect?",
                a: "There are no hard limits. Our Enterprise package allows you to connect hundreds or thousands of physical locations under a single dashboard workspace."
              },
              {
                q: "How does the AI review responder work?",
                a: "Our engine reads the incoming review's sentiment, matches it with your storefront details, and prepares a draft response based on your brand tone. Nothing is published automatically. You review and approve each reply before it goes live."
              },
              {
                q: "How is my data kept secure?",
                a: "We connect through Google's official OAuth. You sign in with Google and we receive a revocable access token, never your password. Those tokens are encrypted at rest, and access to your locations is scoped by role so team members only see what they should."
              },
              {
                q: "Can I cancel anytime?",
                a: "Yes. There are no lock-in contracts on self-serve plans. You can cancel from your billing settings at any time and you won't be charged again. You can also revoke our access directly from your Google account whenever you like."
              },
              {
                q: "What does the free trial include?",
                a: "The 7-day free trial includes up to 3 locations and 10 AI credits, with no credit card required. You get full access to reviews, AI replies, Google Posts, analytics, and audits so you can evaluate the product end-to-end."
              }
            ].map((faq, idx) => (
              <div 
                key={idx} 
                className="border border-border bg-card rounded-xl overflow-hidden cursor-pointer transition-colors hover:bg-muted/20"
                onClick={() => setOpenFaq(openFaq === idx ? null : idx)}
              >
                <div className="flex items-center justify-between p-5 text-sm font-bold text-foreground select-none">
                  <span>{faq.q}</span>
                  <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${openFaq === idx ? 'rotate-180 text-foreground' : ''}`} />
                </div>
                {openFaq === idx && (
                  <div className="px-5 pb-5 text-xs text-muted-foreground leading-relaxed border-t border-border pt-3.5 animate-in slide-in-from-top-2 duration-200">
                    {faq.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 12. FINAL CTA */}
      <section className="mx-auto max-w-5xl px-4 py-20 sm:px-6 lg:px-8">
        <div className="relative rounded-2xl border border-primary/20 bg-primary/5 p-8 sm:p-12 lg:p-16 text-center space-y-6 overflow-hidden">
          <div className="absolute top-1/2 left-1/2 -z-10 h-96 w-96 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
          
          <h2 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            Start Syncing Your Storefronts Today
          </h2>
          <p className="mx-auto max-w-xl text-xs sm:text-sm text-muted-foreground">
            Join local SEO directors, multi-unit franchise owners, and agency operators who have abandoned manual spreadsheets. Connect GMB locations and start automating.
          </p>

          <div className="flex justify-center pt-4">
            <button
              onClick={handleContinueWithGoogle}
              disabled={loading}
              className="flex justify-center items-center gap-3 rounded-lg py-3.5 px-6 text-sm font-semibold bg-white hover:bg-gray-50 border border-gray-200 text-gray-950 shadow-lg cursor-pointer disabled:opacity-50 transition-colors"
            >
              {loading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-600 border-t-transparent"></div>
              ) : (
                <>
                  <svg className="h-5 w-5 shrink-0" viewBox="0 0 24 24">
                    <path fill="#EA4335" d="M12.24 10.285V14.4h6.887c-.648 2.41-2.519 4.114-5.136 4.114A5.99 5.99 0 0 1 8 12.5a5.99 5.99 0 0 1 5.99-6.015c1.474 0 2.812.538 3.854 1.424l3.22-3.22A10.93 10.93 0 0 0 13.99 2 10.99 10.99 0 0 0 3 13c0 6.075 4.925 11 10.99 11 5.753 0 10.457-4.143 10.94-9.673H12.24Z" />
                    <path fill="#FBBC05" d="M13.99 2a10.93 10.93 0 0 0-7.045 2.58l3.22 3.22A5.99 5.99 0 0 1 13.99 5.985V2Z" />
                    <path fill="#34A853" d="M3 13c0 2.215.656 4.275 1.785 6.015l3.22-3.22A5.99 5.99 0 0 1 8 12.5c0-1.282.4-2.472 1.085-3.465L5.865 5.815A10.93 10.93 0 0 0 3 13Z" />
                    <path fill="#4285F4" d="M13.99 24c3.045 0 5.81-1.233 7.82-3.225l-3.22-3.22A5.99 5.99 0 0 1 13.99 18.5a5.99 5.99 0 0 1-5.99-6.015c0-.46.057-.905.158-1.332L4.938 7.913A10.97 10.97 0 0 0 13.99 24Z" />
                  </svg>
                  <span className="font-bold text-gray-950">Continue with Google</span>
                </>
              )}
            </button>
          </div>
        </div>
      </section>

      {/* 13. FOOTER */}
      <footer className="border-t border-border/80 bg-background py-12">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 grid grid-cols-2 md:grid-cols-4 gap-8">
          <div className="col-span-2 md:col-span-1 space-y-4">
            <div className="flex items-center gap-2">
              <img
                src="/logo-horizontal-3.png"
                alt="Pinzo"
                className="h-8 object-contain shrink-0"
              />
            </div>
            <p className="text-[11px] text-muted-foreground leading-relaxed max-w-xs">
              Synchronize, automate, and schedule locations under Google Business Profile. Dominating local maps pack made simple.
            </p>
          </div>

          <div className="space-y-3">
            <span className="text-[10px] uppercase font-bold tracking-widest text-foreground">Product</span>
            <ul className="space-y-1.5 text-xs text-muted-foreground font-semibold">
              <li><button onClick={() => scrollToSection('features')} className="hover:text-foreground transition-colors">Features</button></li>
              <li><button onClick={() => scrollToSection('showcase')} className="hover:text-foreground transition-colors">Analytics</button></li>
              <li><button onClick={() => scrollToSection('pricing')} className="hover:text-foreground transition-colors">Pricing</button></li>
            </ul>
          </div>

          <div className="space-y-3">
            <span className="text-[10px] uppercase font-bold tracking-widest text-foreground">Legal &amp; Security</span>
            <ul className="space-y-1.5 text-xs text-muted-foreground font-semibold">
              <li><a href="/privacy" className="hover:text-foreground transition-colors">Privacy Policy</a></li>
              <li><a href="/terms" className="hover:text-foreground transition-colors">Terms of Service</a></li>
              <li><a href="/privacy#oauth" className="hover:text-foreground transition-colors">Google API &amp; OAuth Usage</a></li>
            </ul>
          </div>

          <div className="space-y-3 col-span-2 md:col-span-1">
            <span className="text-[10px] uppercase font-bold tracking-widest text-foreground">Google Integration</span>
            <p className="text-[10px] text-muted-foreground/80 leading-normal">
              Pinzo is a management platform. Google and Google Business Profile are trademarks of Google LLC. We interact with official Google API channels.
            </p>
          </div>
        </div>

        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 mt-12 pt-6 border-t border-border/50 flex flex-col sm:flex-row items-center justify-between text-[10px] text-muted-foreground/60 font-semibold gap-4">
          <span>&copy; {new Date().getFullYear()} Pinzo. All rights reserved.</span>
          <span>Not affiliated with or endorsed by Google LLC.</span>
        </div>
      </footer>
    </div>
  )
}
