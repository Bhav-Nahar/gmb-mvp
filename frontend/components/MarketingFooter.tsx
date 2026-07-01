import Link from 'next/link';

/** Shared marketing footer (matches the homepage). Used on standalone marketing pages. */
export function MarketingFooter() {
  return (
    <footer className="border-t border-border/80 py-12">
      <div className="mx-auto grid max-w-7xl grid-cols-2 gap-8 px-4 sm:px-6 md:grid-cols-4 lg:px-8">
        <div className="col-span-2 space-y-4 md:col-span-1">
          <img src="/logo-horizontal-3.png" alt="Pinzo" className="h-8 shrink-0 object-contain" />
          <p className="max-w-xs text-[11px] leading-relaxed text-muted-foreground">
            Synchronize, automate, and schedule locations under Google Business Profile.
            Dominating the local maps pack made simple.
          </p>
        </div>
        <div className="space-y-3">
          <span className="text-[10px] font-bold uppercase tracking-widest text-foreground">Product</span>
          <ul className="space-y-1.5 text-xs font-semibold text-muted-foreground">
            <li><Link href="/#features" className="transition-colors hover:text-foreground">Features</Link></li>
            <li><Link href="/#rank" className="transition-colors hover:text-foreground">Local Rank</Link></li>
            <li><Link href="/pricing" className="transition-colors hover:text-foreground">Pricing</Link></li>
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
          <p className="text-[10px] leading-normal text-muted-foreground">
            Pinzo is a management platform. Google and Google Business Profile are trademarks of
            Google LLC. We interact with official Google API channels.
          </p>
        </div>
      </div>
      <div className="mx-auto mt-12 flex max-w-7xl flex-col items-center justify-between gap-4 border-t border-border/50 px-4 pt-6 text-[10px] font-semibold text-muted-foreground/60 sm:flex-row sm:px-6 lg:px-8">
        <span>&copy; {new Date().getFullYear()} Pinzo. All rights reserved.</span>
        <span>Not affiliated with or endorsed by Google LLC.</span>
      </div>
    </footer>
  );
}
