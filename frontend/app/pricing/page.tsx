'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Check, X, MessageCircle, Sparkles, ArrowRight } from 'lucide-react';
import { MarketingHeader } from '@/components/MarketingHeader';
import { MarketingFooter } from '@/components/MarketingFooter';

// Mirrors backend plan_config. Prices are per-location; annual = 12× with the standard
// 20% discount on Basic/Pro. Lite has no annual discount (kept flat/simple).
const PLANS = [
  {
    key: 'lite', name: 'Lite', tagline: 'For a single storefront',
    monthly: 999, annualPerMo: 999, credits: 10, highlight: false,
    perks: ['1 location', 'AI review replies', 'All reviews + Google posts', 'Credit top-ups'],
  },
  {
    key: 'basic', name: 'Basic', tagline: 'For growing multi-location brands',
    monthly: 2500, annualPerMo: 2000, credits: 30, highlight: false,
    perks: ['Unlimited locations', 'Post scheduling + reply templates', 'Auto-reply + email alerts',
            'Team members & roles', 'Full insights & search intelligence'],
  },
  {
    key: 'pro', name: 'Pro', tagline: 'To rank higher & convert more',
    monthly: 3000, annualPerMo: 2400, credits: 45, highlight: false,
    perks: ['Everything in Basic', 'Local Rank geo-grid heatmaps', 'Lead-capture microsite',
            'Most AI credits per location'],
  },
] as const;

// Display-only FX. Razorpay still charges/settles in INR (international cards convert
// at the card network's live rate); this just shows US visitors a familiar number.
// ponytail: hardcoded rate, swap for a live FX fetch if the peg ever drifts materially.
const USD_PER_INR = 1 / 100; // 1 USD = 100 INR

const FEATURES: { label: string; lite: boolean | string; basic: boolean | string; pro: boolean | string }[] = [
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
  { label: 'Local Rank (geo-grid)', lite: false, basic: false, pro: true },
  { label: 'Lead-capture microsite', lite: false, basic: false, pro: true },
];

function Cell({ v }: { v: boolean | string }) {
  if (v === true) return <Check className="mx-auto h-4 w-4 text-primary" aria-label="included" />;
  if (v === false) return <X className="mx-auto h-4 w-4 text-muted-foreground/50" aria-label="not included" />;
  return <span className="text-sm font-medium">{v}</span>;
}

export default function PricingPage() {
  const [annual, setAnnual] = useState(false);
  const [usd, setUsd] = useState(false);

  const fmtPrice = (inr: number) =>
    usd
      ? '$' + Math.round(inr * USD_PER_INR).toLocaleString('en-US')
      : '₹' + inr.toLocaleString('en-IN');

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
            Per-location pricing with a 7-day free trial — no card required. Start small, grow to
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

        {/* Price breakup cards */}
        <div className="mt-12 grid grid-cols-1 gap-6 md:grid-cols-3 md:items-start">
          {PLANS.map((p) => {
            const price = annual ? p.annualPerMo : p.monthly;
            return (
              <div key={p.key}
                className={`relative flex flex-col rounded-2xl border bg-card p-6 transition ${p.highlight ? 'border-primary shadow-xl shadow-primary/10 md:-translate-y-2' : 'border-border'}`}>
                {p.highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary-foreground">
                    Most popular
                  </span>
                )}
                <h2 className="text-lg font-bold">{p.name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{p.tagline}</p>
                <div className="mt-5">
                  <span className="text-4xl font-extrabold">{fmtPrice(price)}</span>
                  <span className="text-sm text-muted-foreground"> /location/mo</span>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {annual && p.key !== 'lite' ? 'billed yearly · ' : ''}
                    {usd ? 'charged in INR at checkout' : '+ 18% GST'}
                  </p>
                </div>
                <Link href="/login"
                  className={`mt-6 inline-flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-bold transition ${p.highlight ? 'bg-primary text-primary-foreground hover:opacity-90' : 'border border-border hover:bg-muted/40'}`}>
                  Start free trial
                </Link>
                <ul className="mt-6 space-y-2.5 text-sm">
                  {p.perks.map((perk) => (
                    <li key={perk} className="flex items-start gap-2">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span className="text-muted-foreground">{perk}</span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Full comparison — below the price breakup */}
        <div className="mt-20">
          <h2 className="text-center text-2xl font-bold">Compare all features</h2>
          <div className="mt-8 overflow-x-auto rounded-2xl border border-border">
            <table className="w-full min-w-[560px] text-center">
              <thead>
                <tr className="border-b border-border bg-muted/30">
                  <th className="py-3 pl-5 text-left text-sm font-bold">Feature</th>
                  {PLANS.map((p) => (
                    <th key={p.key} className="py-3 text-sm font-bold">{p.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {FEATURES.map((f, i) => (
                  <tr key={f.label} className={i % 2 ? 'bg-muted/10' : ''}>
                    <td className="py-3 pl-5 text-left text-sm text-muted-foreground">{f.label}</td>
                    <td className="py-3"><Cell v={f.lite} /></td>
                    <td className="py-3"><Cell v={f.basic} /></td>
                    <td className="py-3"><Cell v={f.pro} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Enterprise */}
        <div className="mt-16 flex flex-col items-center justify-between gap-4 rounded-2xl border border-border bg-muted/20 p-8 sm:flex-row">
          <div>
            <h3 className="text-lg font-bold">Managing a large chain?</h3>
            <p className="text-sm text-muted-foreground">We offer custom per-location pricing and onboarding for enterprise brands.</p>
          </div>
          <a href="https://wa.me/917021052482?text=Hi%2C%20I%27m%20interested%20in%20enterprise%20pricing."
            target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-bold text-primary-foreground hover:opacity-90">
            <MessageCircle className="h-4 w-4" /> Talk to sales <ArrowRight className="h-4 w-4" />
          </a>
        </div>

        <p className="mt-8 text-center text-xs text-muted-foreground">
          All plans include a 7-day free trial (3 locations, 10 AI credits). Prices exclude 18% GST.
        </p>
      </main>

      <MarketingFooter />
    </div>
  );
}
