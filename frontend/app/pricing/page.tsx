'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Check, Minus, MessageCircle } from 'lucide-react';

// Mirrors backend plan_config. Prices are per-location; annual = 12× with the standard
// 20% discount on Basic/Pro (Lite has no annual discount — kept simple/flat).
const PLANS = [
  {
    key: 'lite', name: 'Lite', tagline: 'For a single storefront',
    monthly: 999, annualPerMo: 999, credits: 10, cta: 'Start free trial',
    highlight: false,
  },
  {
    key: 'basic', name: 'Basic', tagline: 'For growing multi-location brands',
    monthly: 2500, annualPerMo: 2000, credits: 30, cta: 'Start free trial',
    highlight: true,
  },
  {
    key: 'pro', name: 'Pro', tagline: 'For teams that want to rank & convert',
    monthly: 3000, annualPerMo: 2400, credits: 45, cta: 'Start free trial',
    highlight: false,
  },
] as const;

// Feature matrix: value per plan key. true/false → check/dash; string → label.
const FEATURES: { label: string; lite: boolean | string; basic: boolean | string; pro: boolean | string }[] = [
  { label: 'Locations included', lite: '1', basic: 'Up to 500', pro: 'Up to 500' },
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
  { label: 'Microsite', lite: false, basic: false, pro: true },
];

function Cell({ v }: { v: boolean | string }) {
  if (v === true) return <Check className="mx-auto h-4 w-4 text-primary" aria-label="included" />;
  if (v === false) return <Minus className="mx-auto h-4 w-4 text-muted-foreground/40" aria-label="not included" />;
  return <span className="text-sm">{v}</span>;
}

export default function PricingPage() {
  const [annual, setAnnual] = useState(false);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center space-y-4">
          <h1 className="text-4xl font-extrabold tracking-tight sm:text-5xl">Simple, per-location pricing</h1>
          <p className="mx-auto max-w-2xl text-muted-foreground">
            Start with a 7-day free trial — no card required. Pay for the locations you manage;
            scale up any time. Enterprise? We&apos;ll tailor it.
          </p>
          {/* Billing toggle */}
          <div className="inline-flex items-center gap-3 rounded-full border border-border bg-card p-1 text-sm">
            <button onClick={() => setAnnual(false)}
              className={`rounded-full px-4 py-1.5 font-semibold transition ${!annual ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>
              Monthly
            </button>
            <button onClick={() => setAnnual(true)}
              className={`rounded-full px-4 py-1.5 font-semibold transition ${annual ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}>
              Yearly <span className="text-xs opacity-80">save 20%</span>
            </button>
          </div>
        </div>

        {/* Cards */}
        <div className="mt-12 grid grid-cols-1 gap-6 md:grid-cols-3">
          {PLANS.map((p) => {
            const price = annual ? p.annualPerMo : p.monthly;
            return (
              <div key={p.key}
                className={`relative flex flex-col rounded-2xl border p-6 ${p.highlight ? 'border-primary shadow-lg shadow-primary/10' : 'border-border'} bg-card`}>
                {p.highlight && (
                  <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-primary-foreground">
                    Most popular
                  </span>
                )}
                <h2 className="text-lg font-bold">{p.name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{p.tagline}</p>
                <div className="mt-5">
                  <span className="text-4xl font-extrabold">₹{price.toLocaleString('en-IN')}</span>
                  <span className="text-sm text-muted-foreground"> /location/mo</span>
                  {annual && p.key !== 'lite' && (
                    <p className="mt-1 text-xs text-muted-foreground">billed yearly · +18% GST</p>
                  )}
                  {(!annual || p.key === 'lite') && (
                    <p className="mt-1 text-xs text-muted-foreground">+ 18% GST</p>
                  )}
                </div>
                <p className="mt-4 text-sm"><span className="font-semibold">{p.credits}</span> AI credits / location / mo</p>
                <Link href="/login"
                  className={`mt-6 inline-flex w-full items-center justify-center rounded-lg px-4 py-2.5 text-sm font-bold transition ${p.highlight ? 'bg-primary text-primary-foreground hover:opacity-90' : 'border border-border hover:bg-muted/40'}`}>
                  {p.cta}
                </Link>
              </div>
            );
          })}
        </div>

        {/* Comparison table */}
        <div className="mt-16 overflow-x-auto">
          <table className="w-full min-w-[560px] text-center">
            <thead>
              <tr className="border-b border-border">
                <th className="py-3 text-left text-sm font-bold">Compare plans</th>
                {PLANS.map((p) => (
                  <th key={p.key} className="py-3 text-sm font-bold">{p.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {FEATURES.map((f) => (
                <tr key={f.label} className="border-b border-border/50">
                  <td className="py-3 text-left text-sm text-muted-foreground">{f.label}</td>
                  <td className="py-3"><Cell v={f.lite} /></td>
                  <td className="py-3"><Cell v={f.basic} /></td>
                  <td className="py-3"><Cell v={f.pro} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Enterprise */}
        <div className="mt-16 flex flex-col items-center justify-between gap-4 rounded-2xl border border-border bg-muted/20 p-8 sm:flex-row">
          <div>
            <h3 className="text-lg font-bold">Managing 50+ locations?</h3>
            <p className="text-sm text-muted-foreground">We offer custom per-location pricing and onboarding for enterprise brands.</p>
          </div>
          <a href="https://wa.me/917021052482?text=Hi%2C%20I%27m%20interested%20in%20enterprise%20pricing."
            target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-border px-5 py-2.5 text-sm font-bold hover:bg-muted/40">
            <MessageCircle className="h-4 w-4" /> Talk to sales
          </a>
        </div>

        <p className="mt-8 text-center text-xs text-muted-foreground">
          All plans include a 7-day free trial (3 locations, 10 AI credits). Prices exclude 18% GST.
        </p>
      </div>
    </div>
  );
}
