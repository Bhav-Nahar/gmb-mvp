'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { BillingBanners } from './BillingBanners';
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

    window.addEventListener('billing-error-402', handleBillingError);

    return () => {
      window.removeEventListener('billing-error-402', handleBillingError);
    };
  }, [router]);

  return (
    <>
      <BillingBanners />
      {children}
      <UpgradeModal open={showUpgradeModal} onOpenChange={setShowUpgradeModal} />
      <TopUpModal open={showTopUpModal} onOpenChange={setShowTopUpModal} />
    </>
  );
}
