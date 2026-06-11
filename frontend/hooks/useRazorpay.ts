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
      console.error('Razorpay SDK failed to load');
      return;
    }

    const rzp = new (window as any).Razorpay(options);
    rzp.open();
  }, [loadScript]);

  return { openRazorpay };
}
