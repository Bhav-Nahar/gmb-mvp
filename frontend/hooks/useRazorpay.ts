import { useCallback, useRef } from 'react';

export interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description?: string;
  order_id?: string;
  subscription_id?: string;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  handler?: (response: any) => void;
  onFailure?: (error: any) => void;
  modal?: {
    ondismiss?: () => void;
  };
}

export function useRazorpay() {
  const isLoaded = useRef(false);

  const loadScript = useCallback(() => {
    return new Promise((resolve) => {
      if (isLoaded.current) {
        resolve(true);
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://checkout.razorpay.com/v1/checkout.js';
      script.onload = () => {
        isLoaded.current = true;
        resolve(true);
      };
      script.onerror = () => {
        resolve(false);
      };
      document.body.appendChild(script);
    });
  }, []);

  const openRazorpay = useCallback(async (options: RazorpayOptions) => {
    const res = await loadScript();

    if (!res) {
      // Throw so the caller's try/catch surfaces a toast instead of silently doing nothing.
      throw new Error('Razorpay checkout failed to load. Check your connection and try again.');
    }

    const rzp = new (window as any).Razorpay(options);
    // Surface in-checkout payment failures (card declined, UPI timeout) — without this
    // a failed payment leaves the UI looking as if nothing happened.
    if (options.onFailure) {
      rzp.on('payment.failed', (resp: any) => options.onFailure!(resp?.error ?? resp));
    }
    rzp.open();
  }, [loadScript]);

  return { openRazorpay };
}
