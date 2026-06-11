import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useBuyCredits } from '@/hooks/useBilling';
import { useRazorpay } from '@/hooks/useRazorpay';
import { toast } from 'sonner';

interface TopUpModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TopUpModal({ open, onOpenChange }: TopUpModalProps) {
  const { mutateAsync: buyCredits, isPending } = useBuyCredits();
  const { openRazorpay } = useRazorpay();

  const handleBuyCredits = async (pack: 'small' | 'large', credits: number) => {
    try {
      const response = await buyCredits({ pack });

      const options = {
        key: response.order.razorpay_key || process.env.NEXT_PUBLIC_RAZORPAY_KEY || '',
        order_id: response.order.id,
        name: 'GMB MVP',
        description: `Buy ${credits} AI Credits`,
        handler: function (res: any) {
          toast.success('Credits purchased! Confirming status...');
          onOpenChange(false);
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
