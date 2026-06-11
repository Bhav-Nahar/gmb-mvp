import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useCheckoutSubscription, useQuote } from '@/hooks/useBilling';
import { useRazorpay } from '@/hooks/useRazorpay';
import { toast } from 'sonner';
import { useState } from 'react';

interface UpgradeModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function UpgradeModal({ open, onOpenChange }: UpgradeModalProps) {
  const { mutateAsync: checkoutSubscription, isPending } = useCheckoutSubscription();
  const { openRazorpay } = useRazorpay();
  const [paymentTerm, setPaymentTerm] = useState<'monthly' | 'annual'>('monthly');
  const [locationCount, setLocationCount] = useState<number>(1);

  // Price is computed server-side (graduated per-location tiers) so the UI and
  // the charge can never drift apart.
  const { data: quote, isLoading: quoteLoading } = useQuote(locationCount, paymentTerm, open);
  const totalRupees = quote ? Math.round(quote.price_paise / 100) : null;

  const handleUpgrade = async () => {
    try {
      const response = await checkoutSubscription({
        location_count: locationCount,
        interval: paymentTerm,
      });
      
      const options = {
        key: response.subscription.razorpay_key || process.env.NEXT_PUBLIC_RAZORPAY_KEY || '',
        subscription_id: response.subscription.id,
        name: 'GMB MVP',
        description: `Subscription for ${locationCount} Locations`,
        handler: function (res: any) {
          toast.success('Subscription activated! Confirming status...');
          onOpenChange(false);
        },
      };

      openRazorpay(options as any);
    } catch (error: any) {
      toast.error(error.message || 'Failed to initialize checkout');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[450px] bg-background z-50">
        <DialogHeader>
          <DialogTitle>Upgrade Your Subscription</DialogTitle>
          <DialogDescription>
            Select how many locations you manage to calculate your customized plan.
          </DialogDescription>
        </DialogHeader>

        <div className="flex justify-center my-4 space-x-2">
          <Button
            variant={paymentTerm === 'monthly' ? 'default' : 'outline'}
            onClick={() => setPaymentTerm('monthly')}
            size="sm"
          >
            Monthly
          </Button>
          <Button
            variant={paymentTerm === 'annual' ? 'default' : 'outline'}
            onClick={() => setPaymentTerm('annual')}
            size="sm"
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
                onClick={() => setLocationCount(Math.max(1, locationCount - 1))}
              >
                -
              </Button>
              <span className="text-xl font-bold w-12 text-center">{locationCount}</span>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setLocationCount(locationCount + 1)}
              >
                +
              </Button>
            </div>
          </div>

          <div className="pt-4 border-t flex items-end justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Total Price</p>
              <p className="text-3xl font-bold">
                {totalRupees !== null ? `₹${totalRupees.toLocaleString('en-IN')}` : '—'}{' '}
                <span className="text-sm font-normal text-muted-foreground">/{paymentTerm === 'monthly' ? 'mo' : 'yr'}</span>
              </p>
            </div>
            <Button onClick={handleUpgrade} disabled={isPending || quoteLoading}>
              Checkout
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
