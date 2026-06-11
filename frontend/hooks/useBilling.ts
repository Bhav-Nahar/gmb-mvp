import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

export interface BillingStatus {
  plan: string;
  subscription_status: string;
  monthly_ai_credits_balance: number;
  topup_ai_credits_balance: number;
  location_quota: number;
  is_org_locked: boolean;
  current_period_end?: string;
  ai_credits_reset_date?: string;
  trial_ends_at?: string;
  grace_period_ends_at?: string;
  subscription_ends_at?: string;
}

export interface Quote {
  location_count: number;
  interval: string;
  price_paise: number;
  monthly_ai_credits: number;
}

export function useBillingStatus(enabled = true) {
  const { user } = useAuth();
  
  return useQuery({
    queryKey: ['billing_status'],
    queryFn: () => api.get<BillingStatus>('/billing/status'),
    enabled: !!user && enabled,
    retry: false,
  });
}

export function useCheckoutSubscription() {
  return useMutation({
    mutationFn: (data: { location_count: number; interval: 'monthly' | 'annual' }) =>
      api.post<{ subscription: { id: string; razorpay_key?: string } }>('/billing/checkout-subscription', {
        location_count: data.location_count,
        interval: data.interval,
      })
  });
}

export function useBuyCredits() {
  return useMutation({
    mutationFn: (data: { pack: 'small' | 'large' }) =>
      api.post<{ order: { id: string; razorpay_key?: string } }>('/billing/buy-credits', data)
  });
}

export function useConfirmPayment() {
  return useMutation({
    mutationFn: (data: {
      razorpay_payment_id: string;
      razorpay_signature: string;
      razorpay_subscription_id?: string;
      razorpay_order_id?: string;
    }) =>
      api.post<{ confirmed: boolean; activated: boolean }>('/billing/confirm', data),
  });
}

export function useQuote(locationCount: number, interval: 'monthly' | 'annual', enabled = true) {
  return useQuery({
    queryKey: ['billing_quote', locationCount, interval],
    queryFn: () => api.get<Quote>(`/billing/quote?location_count=${locationCount}&interval=${interval}`),
    enabled,
  });
}
