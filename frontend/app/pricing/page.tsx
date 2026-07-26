'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Check, X, MessageCircle, Sparkles, ArrowRight, Store, Building2, Rocket, ChevronDown, ShieldCheck, CreditCard, Zap } from 'lucide-react';
import { MarketingHeader } from '@/components/MarketingHeader';
import { MarketingFooter } from '@/components/MarketingFooter';
import { SurfaceLogo } from '@/components/aeo/brandMarks';

const ENGINES = [
  { key: 'google', label: 'Google AI Overviews' },
  { key: 'chatgpt', label: 'ChatGPT' },
  { key: 'gemini', label: 'Gemini' },
  { key: 'perplexity', label: 'Perplexity' },
] as const;

// Mirrors backend plan_config. Prices are per-location; annual = 12× with the standard
// 20% discount on Basic/Pro. Lite has no annual discount (kept flat/simple).
const PLANS = [
  {
    key: 'lite', name: 'Lite', tagline: 'For a single storefront', Icon: Store, engines: [],
    monthly: 999, annualPerMo: 999, credits: 10, highlight: false,
    perks: ['1 location', 'AI review replies', 'All reviews + Google posts', 'Credit top-ups'],
  },
  {
    key: 'basic', name: 'Basic', tagline: 'For growing multi-location brands', Icon: Building2,
    engines: ['google'],
    monthly: 2500, annualPerMo: 2000, credits: 30, highlight: true,
    perks: ['Unlimited locations', 'AI Search Visibility (Google AI)', 'Post scheduling + reply templates',
            'Auto-reply + email alerts', 'Unauthorised change alerts', 'Team members & roles',
            'Full insights & search intelligence'],
  },
  {
    key: 'pro', name: 'Pro', tagline: 'To rank higher & convert more', Icon: Rocket,
    engines: ['google', 'chatgpt', 'gemini', 'perplexity'],
    monthly: 3000, annualPerMo: 2400, credits: 45, highlight: false,
    perks: ['Everything in Basic', 'Full AI Search Visibility (ChatGPT, Gemini, Perplexity)',
            'Local Rank geo-grid heatmaps', 'Lead-capture microsite', 'Most AI credits per location'],
  },
] as const;

const FAQS = [
  { q: 'Is there a free trial?', a: 'Yes — a 7-day free trial covering every location you connect, with 10 AI credits included. The audit itself needs no card at all.' },
  { q: 'How does per-location pricing work?', a: 'You pay the plan price for each Google Business Profile location you connect. Add or remove locations any time; billing adjusts from the next cycle.' },
  { q: 'What are AI credits?', a: 'Each AI action — a review reply draft, a post, an AI visibility scan — spends one credit. Credits reset monthly per location and you can top up any time.' },
  { q: 'Can I cancel anytime?', a: 'Yes. No lock-in on self-serve plans. Cancel from billing settings and you will not be charged again.' },
  { q: 'Which payment methods do you accept?', a: 'Cards, UPI AutoPay and netbanking via Razorpay. International cards are charged in INR at your card network rate.' },
  { q: 'Do prices include GST?', a: 'No — all prices exclude 18% GST, which is added at checkout for Indian customers.' },
];

// Display-only FX. Razorpay still charges/settles in INR (international cards convert
// at the card network's live rate); this just shows US visitors a familiar number.
// ponytail: hardcoded rate, swap for a live FX fetch if the peg ever drifts materially.
const USD_PER_INR = 1 / 100; // 1 USD = 100 INR

const FEATURES: { label: string; lite: boolean | string; basic: boolean | string; pro: boolean | string; marks?: string[] }[] = [
  { label: 'Locations', lite: '1', basic: 'Unlimited', pro: 'Unlimited' },
  { label: 'AI credits / location / mo', lite: '10', basic: '30', pro: '45' },
  { label: 'AI review replies', lite: true, basic: true, pro: true },
  { label: 'All reviews synced', lite: true, basic: true, pro: true },
  { label: 'Google posts (post now)', lite: true, basic: true, pro: true },
  { label: 'Credit top-ups', lite: true, basic: true, pro: true },
  { label: 'Post scheduling', lite: false, basic: true, pro: true },
  { label: 'Reply templates', lite: false, basic: true, pro: true },
  { label: 'Auto-reply + email alerts', lite: false, basic: true, pro: true },
  { label: 'Team members / roles', lite: false, basic: true, pro: true },
  { label: 'Search intelligence', lite: 'Top 10', basic: 'Full', pro: 'Full' },
  { label: 'Insights history', lite: '7 days', basic: 'Full', pro: 'Full' },
  { label: 'Leaderboard & comparison', lite: false, basic: true, pro: true },
  { label: 'Unauthorised change alerts', lite: false, basic: true, pro: true },
  { label: 'AI Visibility — Google AI answers', lite: false, basic: true, pro: true, marks: ['google'] },
  { label: 'AI Visibility — ChatGPT / Gemini / Perplexity', lite: false, basic: false, pro: true, marks: ['chatgpt', 'gemini', 'perplexity'] },
  { label: 'Local Rank (geo-grid)', lite: false, basic: false, pro: true },
  { label: 'Lead-capture microsite', lite: false, basic: false, pro: true },
];

function Cell({ v }: { v: boolean | string }) {
  if (v === true) return (
    <span className="mx-auto flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500/15" aria-label="included">
      <Check className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
    </span>
  );
  if (v === false) return (
    <span className="mx-auto flex h-5 w-5 items-center justify-center rounded-full bg-red-500/15" aria-label="not included">
      <X className="h-3.5 w-3.5 text-red-500" />
    </span>
  );
  return <span className="text-sm font-medium">{v}</span>;
}

export default function PricingPage() {
  const [annual, setAnnual] = useState(false);
  const [usd, setUsd] = useState(false);

  const fmtPrice = (inr: number) =>
    usd
      ? '$' + Math.round(inr * USD_PER_INR).toLocaleString('en-US')
      : '₹' + inr.toLocaleString('en-IN');

  // Default currency: an explicit ?ccy= hint wins (e.g. links from non-India pSEO pages
  // pass ?ccy=usd), otherwise fall back to the visitor timezone. User can still toggle.
  useEffect(() => {
    const ccy = new URLSearchParams(window.location.search).get('ccy');
    if (ccy === 'usd') { setUsd(true); return; }
    if (ccy === 'inr') { setUsd(false); return; }
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    if (!/Kolkata|Calcutta/.test(tz)) setUsd(true);
  }, []);

  return (
    <div className="relative min-h-screen bg-background text-foreground">
      <div className="pointer-events-none absolute left-1/2 top-0 -z-10 h-[700px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.08)_0%,hsl(var(--primary)/0.03)_35%,transparent_70%)]" />
      <MarketingHeader />

      <main className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
        {/* Hero */}
        <div className="text-center space-y-5">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/5 px-3.5 py-1 text-xs font-semibold text-primary">
            <Sparkles className="h-3.5 w-3.5" /> Pay only for the locations you manage
          </div>
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">Pricing that scales with you</h1>
          <p className="mx-auto max-w-2xl text-muted-foreground">
            Per-location pricing. Free audit with no card, then a 7-day free trial — no charge today. Start small, grow to
            hundreds of locations. Enterprise? We&apos;ll tailor it.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <div className="inline-flex items-center gap-1 rounded-full border border-border bg-card p-1 text-sm">
              <button onClick={() => setAnnual(false)}
                className={`rounded-full px-5 py-1.5 font-semibold transition ${!annual ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
                Monthly
              </button>
              <button onClick={() => setAnnual(true)}
                className={`rounded-full px-5 py-1.5 font-semibold transition ${annual ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
                Yearly <span className="text-xs text-emerald-500">· save 20%</span>
              </button>
            </div>
            <div className="inline-flex items-center gap-1 rounded-full border border-border bg-card p-1 text-sm">
              <button onClick={() => setUsd(false)}
                className={`rounded-full px-5 py-1.5 font-semibold transition ${!usd ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
                ₹ INR
              </button>
              <button onClick={() => setUsd(true)}
                className={`rounded-full px-5 py-1.5 font-semibold transition ${usd ? 'bg-primary text-primary-foreground shadow' : 'text-muted-foreground hover:text-foreground'}`}>
                $ USD
              </button>
            </div>
          </div>
        </div>

        {/* Engine strip — the surfaces we actually track */}
        <div className="mt-12 flex flex-col items-center gap-4">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-muted-foreground">Get found on every answer engine</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {ENGINES.map((e) => (
              <span key={e.key}
                className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-4 py-2 text-sm font-semibold shadow-sm transition hover:border-primary/40 hover:shadow">
                <SurfaceLogo surfaceKey={e.key} className="h-5 w-5" />
                {e.label}
              </span>
            ))}
          </div>
        </div>

        {/* Price breakup cards */}
        <div className="mt-14 grid grid-cols-1 gap-6 md:grid-cols-3 md:items-start">
          {PLANS.map((p) => {
            const price = annual ? p.annualPerMo : p.monthly;
            const saves = annual && p.monthly > p.annualPerMo;
            return (
              <div key={p.key}
                className={`group relative flex flex-col rounded-2xl border p-6 transition-all duration-300 hover:-translate-y-1 hover:shadow-xl ${
                  p.highlight
                    ? 'border-primary/60 bg-gradient-to-b from-primary/[0.07] to-card shadow-xl shadow-primary/10 md:-translate-y-3'
                    : 'border-border bg-card hover:border-primary/30'}`}>
                {p.highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 whitespace-nowrap rounded-full bg-primary px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary-foreground shadow-lg shadow-primary/30">
                    Most popular
                  </span>
                )}
                <div className={`flex h-11 w-11 items-center justify-center rounded-xl ${p.highlight ? 'bg-primary text-primary-foreground' : 'bg-primary/10 text-primary'}`}>
                  <p.Icon className="h-5 w-5" />
                </div>
                <h2 className="mt-4 text-lg font-bold">{p.name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{p.tagline}</p>
                <div className="mt-5">
                  <span className="bg-gradient-to-br from-foreground to-foreground/60 bg-clip-text text-5xl font-extrabold tracking-tight text-transparent">{fmtPrice(price)}</span>
                  <span className="text-sm text-muted-foreground"> /location/mo</span>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {annual && p.key !== 'lite' ? 'billed yearly · ' : ''}
                    {usd ? 'charged in INR at checkout' : '+ 18% GST'}
                  </p>
                  {saves && (
                    <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-600 dark:text-emerald-400">
                      Save {fmtPrice((p.monthly - p.annualPerMo) * 12)}/location/yr
                    </p>
                  )}
                </div>
                <Link href="/login"
                  className={`mt-6 inline-flex w-full items-center justify-center gap-1.5 rounded-lg px-4 py-2.5 text-sm font-bold transition ${p.highlight ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20 hover:opacity-90' : 'border border-border hover:border-primary/40 hover:bg-primary/5'}`}>
                  Start free trial <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </Link>
                {p.engines.length > 0 && (
                  <div className="mt-5 rounded-xl border border-border/70 bg-muted/25 p-3">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">AI visibility tracked on</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      {p.engines.map((e) => {
                        const eng = ENGINES.find((x) => x.key === e)!;
                        return (
                          <span key={e} title={eng.label}
                            className="inline-flex items-center gap-1.5 rounded-full border border-border bg-background px-2.5 py-1 text-[11px] font-semibold">
                            <SurfaceLogo surfaceKey={e} className="h-3.5 w-3.5" />
                            {eng.label.replace(' AI Overviews', ' AI')}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
                <ul className="mt-6 space-y-2.5 border-t border-border/60 pt-5 text-sm">
                  {p.perks.map((perk) => (
                    <li key={perk} className="flex items-start gap-2">
                      <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/10">
                        <Check className="h-2.5 w-2.5 text-primary" />
                      </span>
                      <span className="text-muted-foreground">{perk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Reassurance strip */}
        <div className="mt-10 flex flex-wrap items-center justify-center gap-x-8 gap-y-3 rounded-2xl border border-border bg-muted/20 px-6 py-4 text-xs font-semibold text-muted-foreground">
          <span className="inline-flex items-center gap-2"><CreditCard className="h-4 w-4 text-primary" /> No charge for 7 days</span>
          <span className="inline-flex items-center gap-2"><Zap className="h-4 w-4 text-primary" /> Free audit without a card</span>
          <span className="inline-flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-primary" /> Google OAuth · cancel anytime</span>
        </div>

        {/* Full comparison — below the price breakup */}
        <div className="mt-24">
          <h2 className="text-center text-3xl font-extrabold tracking-tight">Compare all features</h2>
          <p className="mt-2 text-center text-sm text-muted-foreground">Everything in every plan, side by side.</p>
          <div className="mt-8 overflow-x-auto rounded-2xl border border-border shadow-sm">
            <table className="w-full min-w-[560px] text-center">
              <thead>
                <tr className="border-b border-border bg-muted/40">
                  <th className="py-4 pl-5 text-left text-sm font-bold">Feature</th>
                  {PLANS.map((p) => (
                    <th key={p.key} className={`py-4 text-sm font-bold ${p.highlight ? 'bg-primary/[0.06] text-primary' : ''}`}>{p.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {FEATURES.map((f, i) => (
                  <tr key={f.label} className={`transition-colors hover:bg-primary/[0.04] ${i % 2 ? 'bg-muted/10' : ''}`}>
                    <td className="py-3 pl-5 text-left text-sm text-muted-foreground">
                      <span className="inline-flex items-center gap-2">
                        {f.marks?.map((m) => <SurfaceLogo key={m} surfaceKey={m} className="h-4 w-4 shrink-0" />)}
                        {f.label}
                      </span>
                    </td>
                    <td className="py-3"><Cell v={f.lite} /></td>
                    <td className="bg-primary/[0.04] py-3"><Cell v={f.basic} /></td>
                    <td className="py-3"><Cell v={f.pro} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* FAQ — native <details>, no state needed */}
        <div className="mt-24">
          <h2 className="text-center text-3xl font-extrabold tracking-tight">Pricing questions</h2>
          <div className="mx-auto mt-8 max-w-3xl space-y-3">
            {FAQS.map((f) => (
              <details key={f.q} className="group overflow-hidden rounded-xl border border-border bg-card transition-colors hover:border-primary/30">
                <summary className="flex cursor-pointer select-none items-center justify-between gap-4 p-5 text-sm font-bold [&::-webkit-details-marker]:hidden">
                  {f.q}
                  <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
                </summary>
                <p className="border-t border-border px-5 pb-5 pt-3.5 text-sm leading-relaxed text-muted-foreground">{f.a}</p>
              </details>
            ))}
          </div>
        </div>

        {/* Enterprise */}
        <div className="mt-20 flex flex-col items-center justify-between gap-4 rounded-2xl border border-border bg-muted/20 p-8 sm:flex-row">
          <div>
            <h3 className="text-lg font-bold">Managing a large chain?</h3>
            <p className="text-sm text-muted-foreground">We offer custom per-location pricing and onboarding for enterprise brands.</p>
          </div>
          <a href="https://wa.me/917715845972?text=Hi%2C%20I%27m%20interested%20in%20enterprise%20pricing."
            target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-bold text-primary-foreground hover:opacity-90">
            <MessageCircle className="h-4 w-4" /> Talk to sales <ArrowRight className="h-4 w-4" />
          </a>
        </div>

        {/* Closing CTA */}
        <div className="relative mt-16 overflow-hidden rounded-3xl border border-primary/20 bg-primary/5 p-10 text-center sm:p-14">
          <div className="pointer-events-none absolute left-1/2 top-0 h-64 w-[600px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_50%_0%,hsl(var(--primary)/0.15),transparent_70%)]" />
          <h2 className="relative text-3xl font-extrabold tracking-tight">Try Pinzo free for 7 days</h2>
          <p className="relative mx-auto mt-3 max-w-xl text-sm text-muted-foreground">
            Run the free audit without a card. Start the trial when you like — nothing is charged today.
          </p>
          <Link href="/login"
            className="relative mt-7 inline-flex items-center gap-2 rounded-lg bg-primary px-7 py-3.5 text-sm font-bold text-primary-foreground shadow-lg shadow-primary/25 transition hover:opacity-90">
            Start free trial <ArrowRight className="h-4 w-4" />
          </Link>
        </div>

        <p className="mt-8 text-center text-xs text-muted-foreground">
          All plans include a 7-day free trial for all your locations, with 10 AI credits included. Prices exclude 18% GST.
        </p>
      </main>

      <MarketingFooter />
    </div>
  );
}
