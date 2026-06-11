import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useBuyCredits, useConfirmPayment } from '@/hooks/useBilling';
import { useRazorpay } from '@/hooks/useRazorpay';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

interface TopUpModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TopUpModal({ open, onOpenChange }: TopUpModalProps) {
  const { mutateAsync: buyCredits, isPending } = useBuyCredits();
  const { mutateAsync: confirmPayment } = useConfirmPayment();
  const { openRazorpay } = useRazorpay();
  const queryClient = useQueryClient();

  const handleBuyCredits = async (pack: 'small' | 'large', credits: number) => {
    const razorpayKey = process.env.NEXT_PUBLIC_RAZORPAY_KEY;
    if (!razorpayKey) {
      toast.error('Payments are not configured (missing key). Please contact support.');
      return;
    }
    try {
      const response = await buyCredits({ pack });

      const options = {
        key: razorpayKey,
        order_id: response.order.id,
        name: 'GMB MVP',
        description: `Buy ${credits} AI Credits`,
        handler: async function (res: any) {
          try {
            await confirmPayment({
              razorpay_payment_id: res.razorpay_payment_id,
              razorpay_signature: res.razorpay_signature,
              razorpay_order_id: res.razorpay_order_id,
            });
            toast.success('Credits added to your balance!');
          } catch {
            toast.success('Payment received! Credits will appear shortly...');
          } finally {
            queryClient.invalidateQueries({ queryKey: ['billing_status'] });
            onOpenChange(false);
          }
        },
        modal: {
          ondismiss: function () {
            toast.info('Checkout closed. No payment was made.');
          },
        },
      };

      openRazorpay(options as any);
    } catch (error: any) {
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
          <div className="border rounded-lg p-4 flex items-center justify-between">
            <div>
              <p className="font-bold">500 Credits Pack</p>
              <p className="text-sm text-muted-foreground">₹499 one-time</p>
            </div>
            <Button onClick={() => handleBuyCredits('small', 500)} disabled={isPending}>
              Buy Now
            </Button>
          </div>

          <div className="border rounded-lg p-4 flex items-center justify-between">
            <div>
              <p className="font-bold">2000 Credits Pack</p>
              <p className="text-sm text-muted-foreground">₹1,799 one-time</p>
            </div>
            <Button onClick={() => handleBuyCredits('large', 2000)} disabled={isPending}>
              Buy Now
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
