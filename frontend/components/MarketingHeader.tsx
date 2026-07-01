'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Menu, X } from 'lucide-react';

const NAV = [
  { href: '/#how', label: 'How it works' },
  { href: '/#features', label: 'Features' },
  { href: '/#rank', label: 'Local Rank' },
  { href: '/pricing', label: 'Pricing' },
  { href: '/#faq', label: 'FAQ' },
];

/** Shared marketing top-nav (matches the homepage). Used on standalone marketing pages
 * like /pricing so every page carries the header. */
export function MarketingHeader() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <header className="sticky top-0 z-50 w-full border-b border-border/80 bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link href="/" className="flex items-center gap-2">
            <img src="/logo-horizontal-3.png" alt="Pinzo" className="h-8 shrink-0 object-contain" />
          </Link>
          <nav className="hidden items-center gap-7 md:flex">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} className="text-xs font-bold uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground">
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="hidden items-center gap-4 md:flex">
            <Link href="/login" className="text-xs font-bold uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground">Login</Link>
            <Link href="/login" className="rounded-lg bg-primary px-4 py-2 text-xs font-bold uppercase tracking-widest text-primary-foreground shadow-sm transition-all hover:bg-primary/90">
              Start free trial
            </Link>
          </div>
          <button onClick={() => setOpen(!open)} className="flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground md:hidden">
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </header>
      {open && (
        <div className="fixed inset-0 top-16 z-40 w-full border-b border-border bg-background/95 backdrop-blur-lg md:hidden">
          <div className="flex flex-col gap-2 p-6">
            {NAV.map((n) => (
              <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
                className="border-b border-border/50 py-3 text-sm font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground">
                {n.label}
              </Link>
            ))}
            <Link href="/login" className="mt-4 flex w-full items-center justify-center rounded-lg bg-primary px-4 py-3 text-sm font-bold text-primary-foreground">
              Start free trial
            </Link>
          </div>
        </div>
      )}
    </>
  );
}
