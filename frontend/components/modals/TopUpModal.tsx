import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useBuyCredits, useConfirmPayment } from '@/hooks/useBilling';
import { useRazorpay } from '@/hooks/useRazorpay';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useState } from 'react';
import { isPaymentVerificationError, PAYMENT_VERIFICATION_FAILED_MSG } from '@/lib/payment';

interface TopUpModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TopUpModal({ open, onOpenChange }: TopUpModalProps) {
  const { mutateAsync: buyCredits, isPending } = useBuyCredits();
  const { mutateAsync: confirmPayment } = useConfirmPayment();
  const { openRazorpay } = useRazorpay();
  const queryClient = useQueryClient();
  // Held true from the click until the Razorpay flow resolves (success/failure/dismiss),
  // so a second click can't create a duplicate order while checkout is opening/open.
  const [submitting, setSubmitting] = useState(false);

  const handleBuyCredits = async (pack: 'small' | 'large', credits: number) => {
    if (submitting) return;
    const razorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY;
    if (!razorpayKey) {
      toast.error('Payments are not configured (missing key). Please contact support.');
      return;
    }
    setSubmitting(true);
    try {
      const response = await buyCredits({ pack });

      const options = {
        key: razorpayKey,
        order_id: response.order.id,
        name: 'Pinzo',
        description: `Buy ${credits} AI Credits`,
        handler: async function (res: any) {
          try {
            const result = await confirmPayment({
              razorpay_payment_id: res.razorpay_payment_id,
              razorpay_signature: res.razorpay_signature,
              razorpay_order_id: res.razorpay_order_id,
            });
            if (result?.activated) {
              toast.success('Credits added to your balance!');
            } else {
              toast.info('Payment received! Credits will appear shortly...');
            }
          } catch (err) {
            if (isPaymentVerificationError(err)) {
              toast.error(PAYMENT_VERIFICATION_FAILED_MSG);
            } else {
              toast.info('Payment received! Credits will appear shortly...');
            }
          } finally {
            setSubmitting(false);
            queryClient.invalidateQueries({ queryKey: ['billing_status'] });
            onOpenChange(false);
          }
        },
        onFailure: (err: any) => {
          setSubmitting(false);
          toast.error(err?.description || 'Payment failed. No credits were added.');
        },
        modal: {
          ondismiss: function () {
            setSubmitting(false);
            toast.info('Checkout closed. No payment was made.');
          },
        },
      };

      // Awaited so a script-load failure (openRazorpay throws) is caught below and
      // surfaced, instead of escaping as an unhandled rejection.
      await openRazorpay(options as any);
    } catch (error: any) {
      setSubmitting(false);
      toast.error(error.message || 'Failed to initialize top-up');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>Top Up AI Credits</DialogTitle>
          <DialogDescription>
            You&apos;ve run out of monthly AI credits. Purchase a top-up pack to continue generating AI responses.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 pt-4">
          <div className="border rounded-lg p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-bold">500 Credits Pack</p>
              <p className="text-sm text-muted-foreground">₹499/- incl. GST · one-time</p>
            </div>
            <Button
              className="w-full sm:w-auto"
              onClick={() => handleBuyCredits('small', 500)}
              disabled={isPending || submitting}
            >
              Buy Now
            </Button>
          </div>

          <div className="border rounded-lg p-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="font-bold">2000 Credits Pack</p>
              <p className="text-sm text-muted-foreground">₹1,799/- incl. GST · one-time</p>
            </div>
            <Button
              className="w-full sm:w-auto"
              onClick={() => handleBuyCredits('large', 2000)}
              disabled={isPending || submitting}
            >
              Buy Now
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
