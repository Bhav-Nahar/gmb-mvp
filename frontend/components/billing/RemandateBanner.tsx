'use client';

import { useBillingStatus, useStartRemandate, useConfirmRemandate } from '@/hooks/useBilling';
import { useRazorpay } from '@/hooks/useRazorpay';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle } from 'lucide-react';
import { useState } from 'react';
import { isPaymentVerificationError, PAYMENT_VERIFICATION_FAILED_MSG } from '@/lib/payment';

/**
 * Shown when a UPI subscription's recurring amount needs to rise (after a location
 * add-on) but Razorpay can't update a UPI mandate. The user must approve a new
 * mandate before `remandate_due_at`, or the surplus locations get re-locked.
 */
export function RemandateBanner() {
  const { data: billing } = useBillingStatus();
  const { mutateAsync: startRemandate, isPending: starting } = useStartRemandate();
  const { mutateAsync: confirmRemandate } = useConfirmRemandate();
  const { openRazorpay } = useRazorpay();
  const queryClient = useQueryClient();
  const [submitting, setSubmitting] = useState(false);

  if (!billing?.needs_remandate) return null;

  const due = billing.remandate_due_at ? new Date(billing.remandate_due_at) : null;
  const dueLabel = due
    ? due.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
    : null;
  const quota = billing.location_quota ?? 0;

  const handleApprove = async () => {
    if (submitting) return;
    const razorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY;
    if (!razorpayKey) {
      toast.error('Payments are not configured (missing key). Please contact support.');
      return;
    }
    setSubmitting(true);
    try {
      const { subscription } = await startRemandate();
      await openRazorpay({
        key: razorpayKey,
        subscription_id: subscription.id,
        name: 'Pinzo',
        description: `Updated AutoPay for ${quota} location${quota === 1 ? '' : 's'}`,
        handler: async function (res: any) {
          try {
            const result = await confirmRemandate({
              razorpay_payment_id: res.razorpay_payment_id,
              razorpay_subscription_id: res.razorpay_subscription_id,
              razorpay_signature: res.razorpay_signature,
            });
            if (result?.activated) {
              toast.success('AutoPay updated — all locations stay active.');
            } else {
              toast.info('Mandate approved! Finalizing — this updates shortly.');
            }
          } catch (err) {
            if (isPaymentVerificationError(err)) {
              toast.error(PAYMENT_VERIFICATION_FAILED_MSG);
            } else {
              toast.info('Mandate approved! Finalizing shortly...');
            }
          } finally {
            setSubmitting(false);
            queryClient.invalidateQueries({ queryKey: ['billing_status'] });
            window.dispatchEvent(new Event('billing:refresh'));
          }
        },
        onFailure: (err: any) => {
          setSubmitting(false);
          toast.error(err?.description || 'Payment failed. Your AutoPay was not updated.');
        },
        modal: {
          ondismiss: function () {
            setSubmitting(false);
            toast.info('AutoPay not updated yet. Approve before the deadline to keep all locations.');
          },
        },
      } as any);
    } catch (error: any) {
      setSubmitting(false);
      toast.error(error?.message || 'Failed to start AutoPay update');
    }
  };

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl bg-amber-500/5 border border-amber-500/30 px-4 py-3">
      <div className="flex items-start gap-2 text-sm font-medium text-amber-500">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>
          Your plan now covers {quota} location{quota === 1 ? '' : 's'}, but your UPI AutoPay
          still bills the old amount. Approve the updated AutoPay
          {dueLabel ? <> by <span className="font-bold">{dueLabel}</span></> : null} to keep all
          locations active — after that, the extra location{quota === 1 ? '' : 's'} will be locked.
        </span>
      </div>
      <button
        onClick={handleApprove}
        disabled={starting || submitting}
        className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-xs font-bold uppercase tracking-widest bg-amber-500 text-white hover:bg-amber-600 shadow-sm cursor-pointer transition-colors shrink-0 disabled:opacity-60"
      >
        {starting || submitting ? 'Starting…' : 'Approve updated AutoPay'}
      </button>
    </div>
  );
}
