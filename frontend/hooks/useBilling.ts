import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

export interface BillingStatus {
  plan: string;
  plan_tier?: string;
  features?: string[];
  subscription_status: string;
  monthly_ai_credits_balance: number;
  monthly_ai_credits_allowance?: number;
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
  plan_tier: string;
  price_paise: number;   // base (ex-GST)
  gst_paise: number;
  total_paise: number;   // base + GST — charged
  gst_rate: number;
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

export interface BillingTransactionRow {
  id: number;
  type: string;
  credits?: number | null;
  amount_paise?: number | null;
  currency: string;
  status?: string | null;
  invoice_url?: string | null;
  created_at: string;
}

export interface BillingTransactionsPage {
  total: number;
  limit: number;
  offset: number;
  transactions: BillingTransactionRow[];
}

export function useBillingTransactions(page = 0, pageSize = 10, enabled = true) {
  const { user } = useAuth();
  const offset = page * pageSize;

  return useQuery({
    queryKey: ['billing_transactions', pageSize, offset],
    queryFn: () =>
      api.get<BillingTransactionsPage>(
        `/billing/transactions?limit=${pageSize}&offset=${offset}`
      ),
    enabled: !!user && enabled,
    retry: false,
    placeholderData: (prev) => prev,
  });
}

export function useCheckoutSubscription() {
  return useMutation({
    mutationFn: (data: { location_count: number; interval: 'monthly' | 'annual'; plan_tier?: string }) =>
      api.post<{ subscription: { id: string; razorpay_key?: string } }>('/billing/checkout-subscription', {
        location_count: data.location_count,
        interval: data.interval,
        plan_tier: data.plan_tier ?? 'basic',
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
  amount_paise: number;   // GST-inclusive — what is charged
  base_paise?: number;
  gst_paise?: number;
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

export function useQuote(locationCount: number, interval: 'monthly' | 'annual', planTier: string = 'basic', enabled = true) {
  return useQuery({
    queryKey: ['billing_quote', locationCount, interval, planTier],
    queryFn: () => api.get<Quote>(`/billing/quote?location_count=${locationCount}&interval=${interval}&plan_tier=${planTier}`),
    enabled,
  });
}
