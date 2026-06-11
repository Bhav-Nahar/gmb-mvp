'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useBillingStatus } from '@/hooks/useBilling';
import { BillingSkeleton } from '@/components/billing/BillingSkeletons';
import { Button } from '@/components/ui/button';
import { UpgradeModal } from '@/components/modals/UpgradeModal';
import { TopUpModal } from '@/components/modals/TopUpModal';

export default function BillingPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const isAuthReady = !loading;
  const { data: billing, isLoading, error, refetch } = useBillingStatus(isAuthReady);
  
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showTopUpModal, setShowTopUpModal] = useState(false);

  // Poll for status updates after a payment modal is closed or during a locked state
  useEffect(() => {
    if (!billing) return;
    
    // Poll every 3 seconds if we are in a pending activation or locked state, as webhook might fix it
    if ((billing.subscription_status === 'trial' && !billing.trial_ends_at) || billing.is_org_locked) {
      const interval = setInterval(() => {
        refetch();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [billing, refetch]);

  useEffect(() => {
    if (isAuthReady && user) {
      if (user.role !== 'Owner' && user.role !== 'Admin') {
        router.push('/dashboard');
      }
    }
  }, [user, isAuthReady, router]);

  if (!isAuthReady || isLoading) {
    return (
      <div className="p-6">
        <BillingSkeleton />
      </div>
    );
  }

  if (error || !billing) {
    return (
      <div className="p-6 text-destructive flex flex-col items-center justify-center space-y-4">
        <p>Failed to load billing information.</p>
        <Button onClick={() => refetch()}>Retry</Button>
      </div>
    );
  }

  const planName = billing.plan || 'Free Tier';
  
  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <h1 className="text-3xl font-bold">Billing & Plans</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Plan Card */}
        <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm">
          <h2 className="text-xl font-semibold mb-4">Current Plan</h2>
          <div className="space-y-4">
            <div className="flex justify-between items-center pb-4 border-b">
              <span className="text-muted-foreground">Plan</span>
              <span className="font-medium capitalize">{planName}</span>
            </div>
            <div className="flex justify-between items-center pb-4 border-b">
              <span className="text-muted-foreground">Status</span>
              <span className="font-medium capitalize">{billing.subscription_status.replace(/_/g, ' ')}</span>
            </div>
            {billing.current_period_end && (
              <div className="flex justify-between items-center pb-4 border-b">
                <span className="text-muted-foreground">Renewal Date</span>
                <span className="font-medium">{new Date(billing.current_period_end).toLocaleDateString()}</span>
              </div>
            )}
            
            <div className="pt-2">
              <Button onClick={() => setShowUpgradeModal(true)} className="w-full">
                Upgrade Plan
              </Button>
            </div>
          </div>
        </div>

        {/* Quota & Credits Card */}
        <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm flex flex-col space-y-6">
          <h2 className="text-xl font-semibold">Usage & Limits</h2>
          
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span className="font-medium">Location Quota</span>
              <span className="text-muted-foreground">{billing.location_quota} Allowed</span>
            </div>
          </div>

          <div className="space-y-4 flex-1">
            <div className="flex justify-between items-center p-3 bg-secondary/50 rounded-lg">
              <div>
                <p className="text-sm font-medium">Monthly AI Credits</p>
                <p className="text-2xl font-bold">{billing.monthly_ai_credits_balance}</p>
              </div>
            </div>
            
            <div className="flex justify-between items-center p-3 bg-secondary/50 rounded-lg">
              <div>
                <p className="text-sm font-medium">Top-up AI Credits</p>
                <p className="text-2xl font-bold">{billing.topup_ai_credits_balance}</p>
              </div>
              <Button variant="outline" size="sm" onClick={() => setShowTopUpModal(true)}>
                Buy More
              </Button>
            </div>
          </div>
        </div>
      </div>

      <UpgradeModal open={showUpgradeModal} onOpenChange={setShowUpgradeModal} />
      <TopUpModal open={showTopUpModal} onOpenChange={setShowTopUpModal} />
    </div>
  );
}
