'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BillingBanners } from './BillingBanners';
import { ProUpsellBanner } from './ProUpsellBanner';
import { UpgradeModal } from '../modals/UpgradeModal';
import { TopUpModal } from '../modals/TopUpModal';

export function BillingProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showTopUpModal, setShowTopUpModal] = useState(false);

  useEffect(() => {
    const handleBillingError = (event: Event) => {
      const customEvent = event as CustomEvent;
      const detail = customEvent.detail?.detail || '';

      // Card-required onboarding: every pre-trial 402 carries 'trial_required'. The
      // full-screen OnboardingGate already handles this state — do NOT pop the generic
      // "Upgrade your subscription" modal on top of it.
      if (detail.includes('trial_required')) {
        return;
      }

      if (detail.includes('location_quota_exceeded') || detail.includes('location quota')) {
        setShowUpgradeModal(true);
      } else if (detail.includes('insufficient_credits') || detail.includes('credit')) {
        setShowTopUpModal(true);
      } else if (detail.includes('locked')) {
        router.push('/dashboard/settings/billing');
      } else {
        // Fallback for generic 402 if it doesn't match above strings
        setShowUpgradeModal(true);
      }
    };

    // Pro upsell CTA (ProUpsellBanner) opens the same UpgradeModal.
    const openUpgrade = () => setShowUpgradeModal(true);

    window.addEventListener('billing-error-402', handleBillingError);
    window.addEventListener('open-upgrade-modal', openUpgrade);

    return () => {
      window.removeEventListener('billing-error-402', handleBillingError);
      window.removeEventListener('open-upgrade-modal', openUpgrade);
    };
  }, [router]);

  return (
    <>
      <BillingBanners />
      <ProUpsellBanner />
      {children}
      <UpgradeModal open={showUpgradeModal} onOpenChange={setShowUpgradeModal} />
      <TopUpModal open={showTopUpModal} onOpenChange={setShowTopUpModal} />
    </>
  );
}
