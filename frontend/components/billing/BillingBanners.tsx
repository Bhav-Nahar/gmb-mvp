'use client';

import { usePathname } from 'next/navigation';
import { useBillingStatus } from '@/hooks/useBilling';
import { useCountdown } from '@/hooks/useCountdown';
import { AlertCircle, Lock } from 'lucide-react';
import { CARD_REQUIRED_ONBOARDING } from '@/lib/onboarding';
import { OnboardingGate } from '@/components/onboarding/OnboardingGate';
import { OnboardingSyncing } from '@/components/onboarding/OnboardingSyncing';

export function BillingBanners() {
  const pathname = usePathname();
  const { data: billing, isLoading } = useBillingStatus();
  
  // Only calculate countdown for trial
  const trialCountdown = useCountdown(billing?.trial_ends_at || null);

  if (isLoading || !billing) return null;

  // Don't show fullscreen lock on settings/billing, login, or public pages
  const isWhitelisted = pathname?.startsWith('/dashboard/settings/billing') || pathname?.startsWith('/login') || pathname === '/';
  
  if (billing.is_org_locked && !isWhitelisted) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
        <div className="bg-card p-8 rounded-lg shadow-xl max-w-md w-full text-center space-y-4 border">
          <Lock className="w-12 h-12 mx-auto text-destructive" />
          <h2 className="text-2xl font-bold">Organization Locked</h2>
          <p className="text-muted-foreground">
            Your organization has been locked due to an expired subscription or payment failure.
          </p>
          <div className="pt-4">
            <a 
              href="/dashboard/settings/billing" 
              className="inline-flex items-center justify-center rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 w-full"
            >
              Go to Billing Settings
            </a>
          </div>
        </div>
      </div>
    );
  }

  // Pending/onboarding: status 'trial' but the clock hasn't started (no trial_ends_at).
  if (billing.subscription_status === 'trial' && !billing.trial_ends_at) {
    const activeLocations = billing.active_location_count ?? 0;
    const sync = billing.onboarding_sync_status ?? 'ready';
    // Card-required flow. Order matters: show the "analyzing…" screen until the audit is
    // actually READY, THEN the hard paywall gate — never a bare pay wall over a half-synced
    // (empty-FOMO) audit. A 0-location org has nothing to bill, so it isn't gated.
    if (CARD_REQUIRED_ONBOARDING && !isWhitelisted) {
      // Phone is collected inline on the gate now (fewer steps), so we no longer wait on it.
      if (sync === 'failed') return <OnboardingSyncing failed />;
      if (sync === 'syncing' || sync === 'idle') return <OnboardingSyncing />;
      // ready: the audit result + paywall (single "Start Free Trial" screen).
      if (activeLocations > 0) return <OnboardingGate locations={activeLocations} />;
    }
    return (
      <div className="bg-amber-100 dark:bg-amber-900/30 border-b border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200 px-4 py-3 flex items-center justify-center text-sm">
        <AlertCircle className="w-4 h-4 mr-2" />
        <p>
          {CARD_REQUIRED_ONBOARDING
            ? 'Connect a Google Business location to see your free audit.'
            : 'Sync your first location to activate your 7-day trial!'}
        </p>
      </div>
    );
  }

  if (billing.subscription_status === 'trial') {
    return (
      <div className="bg-blue-100 dark:bg-blue-900/30 border-b border-blue-200 dark:border-blue-800 text-blue-900 dark:text-blue-200 px-4 py-3 flex items-center justify-center text-sm">
        <p>
          <strong>Trial Period:</strong> {trialCountdown.days} days, {trialCountdown.hours} hours left.
          <a href="/dashboard/settings/billing" className="ml-2 underline font-medium">Upgrade now</a>
        </p>
      </div>
    );
  }

  if (billing.subscription_status === 'past_due') {
    return (
      <div className="bg-destructive/10 border-b border-destructive/20 text-destructive px-4 py-3 flex items-center justify-center text-sm">
        <AlertCircle className="w-4 h-4 mr-2" />
        <p>
          Payment failed. Your subscription will be locked soon.
          <a href="/dashboard/settings/billing" className="ml-2 underline font-medium">Update payment method</a>
        </p>
      </div>
    );
  }

  // Cancelled but still valid: status is 'active' with an end date set.
  if (billing.subscription_status === 'active' && billing.subscription_ends_at) {
    return (
      <div className="bg-muted border-b px-4 py-3 flex items-center justify-center text-sm">
        <p>
          Your subscription will end on {billing.subscription_ends_at ? new Date(billing.subscription_ends_at).toLocaleDateString() : 'soon'}.
          <a href="/dashboard/settings/billing" className="ml-2 underline font-medium">Reactivate</a>
        </p>
      </div>
    );
  }

  return null;
}
