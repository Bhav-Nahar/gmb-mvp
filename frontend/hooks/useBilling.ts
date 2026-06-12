import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

export interface BillingStatus {
  plan: string;
  subscription_status: string;
  monthly_ai_credits_balance: number;
  topup_ai_credits_balance: number;
  location_quota: number;
  active_location_count?: number;
  pending_location_count?: number;
  is_org_locked: boolean;
  current_period_end?: string;
  ai_credits_reset_date?: string;
  trial_ends_at?: string;
  grace_period_ends_at?: string;
  subscription_ends_at?: string;
  needs_remandate?: boolean;
  remandate_due_at?: string;
  paid_location_quota?: number;
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

export interface PendingLocation {
  id: number;
  location_name?: string;
  address?: string;
}

export interface UnlockQuote {
  location_ids: number[];
  added: number;
  interval: string;
  amount_paise: number;
  credits_granted: number;
}

export function usePendingLocations(enabled = true) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ['pending_locations'],
    queryFn: () =>
      api.get<{ pending_locations: PendingLocation[]; quote: UnlockQuote | null }>(
        '/billing/pending-locations'
      ),
    enabled: !!user && enabled,
  });
}

export function useUnlockLocations() {
  return useMutation({
    mutationFn: (data: { location_ids: number[] }) =>
      api.post<{ order: { id: string; amount: number; currency: string }; quote: UnlockQuote }>(
        '/billing/locations/unlock',
        data
      ),
  });
}

export function useStartRemandate() {
  return useMutation({
    mutationFn: () =>
      api.post<{ subscription: { id: string } }>('/billing/remandate', {}),
  });
}

export function useConfirmRemandate() {
  return useMutation({
    mutationFn: (data: {
      razorpay_payment_id: string;
      razorpay_subscription_id: string;
      razorpay_signature: string;
    }) => api.post<{ confirmed: boolean; activated: boolean }>('/billing/remandate/confirm', data),
  });
}

export function useQuote(locationCount: number, interval: 'monthly' | 'annual', enabled = true) {
  return useQuery({
    queryKey: ['billing_quote', locationCount, interval],
    queryFn: () => api.get<Quote>(`/billing/quote?location_count=${locationCount}&interval=${interval}`),
    enabled,
  });
}
