'use client';

import { usePathname } from 'next/navigation';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import { useBillingStatus } from '@/hooks/useBilling';

// Route → the plan feature it requires. Direct navigation to one of these on a plan that
// doesn't include it shows a friendly upgrade screen instead of a raw 403. (The sidebar
// already hides these; this covers bookmarks / typed URLs.) Matched on a path boundary so
// /dashboard/compare (leaderboard) doesn't swallow /dashboard/comparison.
const GATED: { prefix: string; feature: string; name: string; anyTier?: boolean }[] = [
  { prefix: '/dashboard/aeo', feature: 'aeo', name: 'AI Visibility' },
  { prefix: '/dashboard/local-rank', feature: 'local_rank', name: 'Local Rank' },
  { prefix: '/dashboard/comparison', feature: 'comparison', name: 'Comparison' },
  { prefix: '/dashboard/compare', feature: 'leaderboard', name: 'Leaderboard' },
  { prefix: '/dashboard/settings/reply-templates', feature: 'reply_templates', name: 'Reply Templates' },
  { prefix: '/dashboard/team', feature: 'team', name: 'Team members' },
  // Newer features have no legacy Basic/Pro behaviour to preserve, so they are
  // gated on every tier that lacks them — not just Lite. `anyTier` is what says so.
  { prefix: '/dashboard/reviews/request', feature: 'review_requests',
    name: 'WhatsApp review requests', anyTier: true },
  { prefix: '/dashboard/settings/whatsapp', feature: 'review_requests',
    name: 'WhatsApp review requests', anyTier: true },
  { prefix: '/dashboard/whatsapp', feature: 'review_requests',
    name: 'WhatsApp inbox', anyTier: true },
];

function matches(pathname: string, prefix: string) {
  return pathname === prefix || pathname.startsWith(prefix + '/');
}

function UpgradeInterstitial({ name }: { name: string }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center p-6">
      <div className="max-w-md w-full text-center space-y-4 rounded-2xl border bg-card p-8 shadow-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Lock className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-bold">{name} is a premium feature</h2>
        <p className="text-sm text-muted-foreground">
          Your current plan doesn&apos;t include {name}. Upgrade to unlock it and more.
        </p>
        <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-center">
          <Link href="/dashboard/settings/billing"
            className="inline-flex items-center justify-center rounded-lg bg-primary px-5 py-2.5 text-sm font-bold text-primary-foreground hover:opacity-90">
            Upgrade plan
          </Link>
          <Link href="/pricing"
            className="inline-flex items-center justify-center rounded-lg border px-5 py-2.5 text-sm font-semibold hover:bg-muted/40">
            Compare plans
          </Link>
        </div>
      </div>
    </div>
  );
}

export function FeatureRouteGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const { data: billing, isLoading } = useBillingStatus();

  const match = GATED.find((g) => matches(pathname, g.prefix));
  if (!match) return <>{children}</>;
  // Don't block while billing loads (avoid a flash); the backend still enforces via 403.
  if (isLoading || !billing) return <>{children}</>;
  // Scope the interstitial to the Lite plan ONLY, so existing Basic/Pro orgs are never
  // affected (they keep their exact prior behavior — Local Rank etc. as before).
  if (billing.plan_tier !== 'lite' && !match.anyTier) return <>{children}</>;
  if (billing.features?.includes(match.feature)) return <>{children}</>;
  return <UpgradeInterstitial name={match.name} />;
}
