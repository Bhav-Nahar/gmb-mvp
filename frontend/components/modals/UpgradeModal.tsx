import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import {
  useCheckoutSubscription,
  useConfirmPayment,
  useQuote,
  useBillingStatus,
  usePendingLocations,
  useUnlockLocations,
} from '@/hooks/useBilling';
import { useQueryClient } from '@tanstack/react-query';
import { useRazorpay } from '@/hooks/useRazorpay';
import { toast } from 'sonner';
import { useState } from 'react';
import { isPaymentVerificationError, PAYMENT_VERIFICATION_FAILED_MSG } from '@/lib/payment';
import { trackSelectPlan, trackPurchase } from '@/lib/analytics';
import { useAuth } from '@/hooks/useAuth';

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UpgradeModal({ open, onOpenChange }: UpgradeModalProps) {
  const { user } = useAuth();
  const { mutateAsync: checkoutSubscription, isPending } = useCheckoutSubscription();
  const { mutateAsync: confirmPayment } = useConfirmPayment();
  const { mutateAsync: unlockLocations, isPending: unlockPending } = useUnlockLocations();
  const { openRazorpay } = useRazorpay();
  const queryClient = useQueryClient();
  const [paymentTerm, setPaymentTerm] = useState<'monthly' | 'annual'>('monthly');
  const [locationCount, setLocationCount] = useState<number>(1);
  const [planTier, setPlanTier] = useState<'basic' | 'pro'>('pro');
  // Held true across the whole Razorpay flow so a second click can't create a second
  // subscription/order (the backend overwrites razorpay_subscription_id each call).
  const [submitting, setSubmitting] = useState(false);

  // An org that already has an active subscription doesn't re-subscribe to unlock a
  // newly-added location — it pays a prorated add-on whose order carries the
  // `location_addon` notes the backend needs to flip the location to active.
  // Re-running subscription checkout (the old behaviour) charged money but never
  // unlocked the location, because no add-on order/notes were ever created.
  const { data: billing } = useBillingStatus(open);
  const isUnlockMode =
    billing?.subscription_status === 'active' && (billing?.pending_location_count ?? 0) > 0;
  const { data: pending, isLoading: pendingLoading } = usePendingLocations(open && isUnlockMode);

  // Price is computed server-side (graduated per-location tiers) so the UI and
  // the charge can never drift apart.
  const { data: quote, isLoading: quoteLoading } = useQuote(
    locationCount,
    paymentTerm,
    planTier,
    open && !isUnlockMode
  );
  // Headline shows the BASE price per the agreed convention (₹X/- with + GST beneath).
  const baseRupees = quote ? Math.round(quote.price_paise / 100) : null;
  const gstRupees = quote ? Math.round(quote.gst_paise / 100) : null;
  const totalRupees = quote ? Math.round(quote.total_paise / 100) : null;
  const gstPct = quote ? Math.round(quote.gst_rate * 100) : 18;
  const unlockRupees = pending?.quote ? Math.round(pending.quote.amount_paise / 100) : null; // GST-incl total
  const unlockBaseRupees = pending?.quote?.base_paise != null ? Math.round(pending.quote.base_paise / 100) : null;
  const unlockGstRupees = pending?.quote?.gst_paise != null ? Math.round(pending.quote.gst_paise / 100) : null;

  const handleUnlock = async () => {
    if (submitting) return;
    const razorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY;
    if (!razorpayKey) {
      toast.error('Payments are not configured (missing key). Please contact support.');
      return;
    }
    const ids = (pending?.pending_locations ?? []).map((l) => l.id);
    if (ids.length === 0) {
      toast.error('No locked locations to unlock.');
      return;
    }
    setSubmitting(true);
    try {
      const { order } = await unlockLocations({ location_ids: ids });
      await openRazorpay({
        key: razorpayKey,
        order_id: order.id,
        amount: order.amount,
        currency: order.currency,
        name: 'Pinzo',
        description: `Unlock ${ids.length} location${ids.length === 1 ? '' : 's'}`,
        handler: async function (res: any) {
          // Confirm via the ORDER path so the backend reconciles the add-on and
          // flips the locations to active. The webhook is the backstop.
          try {
            const result = await confirmPayment({
              razorpay_payment_id: res.razorpay_payment_id,
              razorpay_signature: res.razorpay_signature,
              razorpay_order_id: res.razorpay_order_id,
            });
            if (result?.activated) {
              toast.success(`${ids.length} location${ids.length === 1 ? '' : 's'} unlocked!`);
            } else {
              toast.info('Payment received! Unlocking shortly...');
            }
          } catch (err) {
            if (isPaymentVerificationError(err)) {
              toast.error(PAYMENT_VERIFICATION_FAILED_MSG);
            } else {
              toast.info('Payment received! Unlocking shortly...');
            }
          } finally {
            setSubmitting(false);
            queryClient.invalidateQueries({ queryKey: ['billing_status'] });
            queryClient.invalidateQueries({ queryKey: ['pending_locations'] });
            window.dispatchEvent(new Event('billing:refresh'));
            onOpenChange(false);
          }
        },
        onFailure: (err: any) => {
          setSubmitting(false);
          toast.error(err?.description || 'Payment failed. No locations were unlocked.');
        },
        modal: {
          ondismiss: function () {
            setSubmitting(false);
            toast.info('Checkout closed. No payment was made.');
          },
        },
      } as any);
    } catch (error: any) {
      setSubmitting(false);
      toast.error(error.message || 'Failed to start unlock');
    }
  };

  const handleUpgrade = async () => {
    if (submitting) return;
    const razorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY;
    if (!razorpayKey) {
      toast.error('Payments are not configured (missing key). Please contact support.');
      return;
    }
    setSubmitting(true);
    const planName = planTier === 'pro' ? 'Pro' : 'Basic';
    trackSelectPlan({
      plan_name: planName,
      paymentTerm,
      value: baseRupees ?? 0,
      locations_included: locationCount,
      user_id: user?.id,
      email: user?.email,
    });
    try {
      const response = await checkoutSubscription({
        location_count: locationCount,
        interval: paymentTerm,
        plan_tier: planTier,
      });

      const options = {
        key: razorpayKey,
        subscription_id: response.subscription.id,
        name: 'Pinzo',
        description: `Subscription for ${locationCount} Locations`,
        handler: async function (res: any) {
          // Verify the payment server-side and activate immediately, rather than
          // waiting on the webhook. If confirm fails, the webhook / periodic
          // reconcile is still the backstop.
          try {
            const result = await confirmPayment({
              razorpay_payment_id: res.razorpay_payment_id,
              razorpay_signature: res.razorpay_signature,
              razorpay_subscription_id: res.razorpay_subscription_id,
            });
            if (result?.activated) {
              trackPurchase({
                transaction_id: res.razorpay_payment_id,
                plan_name: planName,
                paymentTerm,
                value: totalRupees ?? baseRupees ?? 0, // amount actually charged (incl. GST)
                locations_included: locationCount,
                user_id: user?.id,
                email: user?.email,
              });
              toast.success('Subscription activated!');
            } else {
              toast.info('Payment received! Confirming activation shortly...');
            }
          } catch (err) {
            if (isPaymentVerificationError(err)) {
              toast.error(PAYMENT_VERIFICATION_FAILED_MSG);
            } else {
              toast.info('Payment received! Confirming activation shortly...');
            }
          } finally {
            setSubmitting(false);
            queryClient.invalidateQueries({ queryKey: ['billing_status'] });
            window.dispatchEvent(new Event('billing:refresh'));
            onOpenChange(false);
          }
        },
        onFailure: (err: any) => {
          setSubmitting(false);
          toast.error(err?.description || 'Payment failed. Subscription not activated.');
        },
        modal: {
          ondismiss: function () {
            setSubmitting(false);
            toast.info('Checkout closed. No payment was made.');
          },
        },
      };

      await openRazorpay(options as any);
    } catch (error: any) {
      setSubmitting(false);
      toast.error(error.message || 'Failed to initialize checkout');
    }
  };

  if (isUnlockMode) {
    const count = pending?.pending_locations?.length ?? billing?.pending_location_count ?? 0;
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[450px] bg-background z-50">
          <DialogHeader>
            <DialogTitle>Unlock Location{count === 1 ? '' : 's'}</DialogTitle>
            <DialogDescription>
              You&apos;re on an active plan. Pay the prorated charge for the rest of this
              billing cycle to unlock {count === 1 ? 'this location' : 'these locations'}.
            </DialogDescription>
          </DialogHeader>

          <div className="border rounded-lg p-6 space-y-5 mt-2">
            <div className="space-y-2">
              <label className="text-sm font-medium">Locked locations</label>
              <ul className="space-y-1.5">
                {(pending?.pending_locations ?? []).map((loc) => (
                  <li key={loc.id} className="text-sm text-muted-foreground truncate">
                    • {loc.location_name || `Location #${loc.id}`}
                  </li>
                ))}
                {(pending?.pending_locations?.length ?? 0) === 0 && (
                  <li className="text-sm text-muted-foreground">
                    {pendingLoading ? 'Loading…' : 'No locked locations.'}
                  </li>
                )}
              </ul>
            </div>

            <div className="pt-4 border-t flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Prorated charge</p>
                <p className="text-3xl font-bold">
                  {unlockBaseRupees !== null
                    ? `₹${unlockBaseRupees.toLocaleString('en-IN')}/-`
                    : unlockRupees !== null ? `₹${unlockRupees.toLocaleString('en-IN')}` : '—'}
                </p>
                {unlockGstRupees !== null && unlockRupees !== null && (
                  <p className="text-xs text-muted-foreground mt-0.5">
                    + 18% GST (₹{unlockGstRupees.toLocaleString('en-IN')}) ={' '}
                    <span className="font-medium text-foreground">₹{unlockRupees.toLocaleString('en-IN')}</span> total
                  </p>
                )}
              </div>
              <Button
                className="w-full sm:w-auto"
                onClick={handleUnlock}
                disabled={unlockPending || submitting || pendingLoading || (pending?.pending_locations?.length ?? 0) === 0}
              >
                {unlockPending || submitting ? 'Starting…' : 'Pay & Unlock'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[450px] bg-background z-50">
        <DialogHeader>
          <DialogTitle>Upgrade Your Subscription</DialogTitle>
          <DialogDescription>
            Select how many locations you manage to calculate your customized plan.
          </DialogDescription>
        </DialogHeader>

        {/* Plan tier picker */}
        <div className="grid grid-cols-2 gap-2 mt-2">
          {([
            { key: 'basic', name: 'Basic', note: 'Core GBP tools' },
            { key: 'pro', name: 'Pro', note: 'Adds Local Rank + more credits' },
          ] as const).map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setPlanTier(t.key)}
              className={`text-left rounded-lg border p-3 transition-colors ${
                planTier === t.key ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted/40'
              }`}
            >
              <div className="text-sm font-semibold flex items-center gap-1.5">
                {t.name}
                {t.key === 'pro' && (
                  <span className="text-[10px] bg-primary/15 text-primary px-1.5 py-0.5 rounded">Recommended</span>
                )}
              </div>
              <div className="text-xs text-muted-foreground mt-0.5">{t.note}</div>
            </button>
          ))}
        </div>

        <div className="flex justify-center my-4 gap-2 sm:space-x-2">
          <Button
            variant={paymentTerm === 'monthly' ? 'default' : 'outline'}
            onClick={() => setPaymentTerm('monthly')}
            size="sm"
            className="flex-1 min-h-[44px] sm:flex-none sm:min-h-0"
          >
            Monthly
          </Button>
          <Button
            variant={paymentTerm === 'annual' ? 'default' : 'outline'}
            onClick={() => setPaymentTerm('annual')}
            size="sm"
            className="flex-1 min-h-[44px] sm:flex-none sm:min-h-0"
          >
            Yearly (Save 20%)
          </Button>
        </div>

        <div className="border rounded-lg p-6 space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-medium">Number of Locations</label>
            <div className="flex items-center space-x-4">
              <Button
                variant="outline"
                size="sm"
                className="min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 text-lg sm:text-[0.8rem]"
                onClick={() => setLocationCount(Math.max(1, locationCount - 1))}
              >
                -
              </Button>
              <span className="text-xl font-bold w-12 text-center">{locationCount}</span>
              <Button
                variant="outline"
                size="sm"
                className="min-h-[44px] min-w-[44px] sm:min-h-0 sm:min-w-0 text-lg sm:text-[0.8rem]"
                onClick={() => setLocationCount(locationCount + 1)}
              >
                +
              </Button>
            </div>
          </div>

          <div className="pt-4 border-t flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Price</p>
              <p className="text-3xl font-bold">
                {baseRupees !== null ? `₹${baseRupees.toLocaleString('en-IN')}/-` : '—'}{' '}
                <span className="text-sm font-normal text-muted-foreground">/{paymentTerm === 'monthly' ? 'mo' : 'yr'}</span>
              </p>
              {gstRupees !== null && totalRupees !== null && (
                <p className="text-xs text-muted-foreground mt-0.5">
                  + {gstPct}% GST (₹{gstRupees.toLocaleString('en-IN')}) ={' '}
                  <span className="font-medium text-foreground">₹{totalRupees.toLocaleString('en-IN')}</span> total
                </p>
              )}
            </div>
            <Button
              className="w-full sm:w-auto"
              onClick={handleUpgrade}
              disabled={isPending || submitting || quoteLoading || totalRupees === null}
            >
              {isPending || submitting ? 'Starting…' : 'Checkout'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
