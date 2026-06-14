'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import {
  useBillingStatus,
  useBillingTransactions,
  type BillingStatus,
  type BillingTransactionRow,
} from '@/hooks/useBilling';
import { BillingSkeleton } from '@/components/billing/BillingSkeletons';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { UpgradeModal } from '@/components/modals/UpgradeModal';
import { TopUpModal } from '@/components/modals/TopUpModal';

type BadgeVariant = 'default' | 'secondary' | 'destructive' | 'outline';

function statusPresentation(status: string): { label: string; variant: BadgeVariant } {
  const normalized = (status || '').toLowerCase();
  switch (normalized) {
    case 'active':
      return { label: 'Active', variant: 'default' };
    case 'trial':
      return { label: 'Trial', variant: 'secondary' };
    case 'past_due':
      return { label: 'Past due', variant: 'destructive' };
    case 'cancelled':
    case 'canceled':
      return { label: 'Cancelled', variant: 'outline' };
    default:
      return { label: status.replace(/_/g, ' ') || 'Unknown', variant: 'outline' };
  }
}

function formatDate(value?: string): string {
  if (!value) return '—';
  return new Date(value).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function formatAmount(paise?: number | null, currency = 'INR'): string {
  if (paise == null) return '—';
  const amount = paise / 100;
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `₹${amount.toLocaleString()}`;
  }
}

function transactionLabel(type: string): string {
  switch (type) {
    case 'subscription_charge':
      return 'Subscription charge';
    case 'topup_charge':
      return 'AI credits top-up';
    case 'location_addon':
      return 'Location add-on';
    default:
      return type.replace(/_/g, ' ');
  }
}

function UsageBar({
  label,
  used,
  total,
  hint,
}: {
  label: string;
  used: number;
  total: number;
  hint?: string;
}) {
  const safeTotal = total > 0 ? total : 0;
  const pct = safeTotal > 0 ? Math.min(100, Math.round((used / safeTotal) * 100)) : 0;
  const low = safeTotal > 0 && used / safeTotal <= 0.15;

  return (
    <div className="space-y-2">
      <div className="flex justify-between items-baseline text-sm">
        <span className="font-medium">{label}</span>
        <span className="text-muted-foreground">
          {used}
          {safeTotal > 0 ? ` / ${safeTotal}` : ''}
        </span>
      </div>
      <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${low ? 'bg-destructive' : 'bg-primary'}`}
          style={{ width: `${safeTotal > 0 ? pct : 100}%` }}
        />
      </div>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function resetHint(billing: BillingStatus): string | undefined {
  const date = billing.ai_credits_reset_date || billing.current_period_end;
  if (!date) return undefined;
  return `Resets ${formatDate(date)}`;
}

function TransactionsTable({ rows }: { rows: BillingTransactionRow[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-6 text-center">
        No payments yet. Charges will appear here once your subscription bills.
      </p>
    );
  }

  return (
    <>
      {/* Mobile stacked cards */}
      <div className="space-y-3 sm:hidden">
        {rows.map((t) => {
          const success = (t.status || '').toLowerCase() === 'success';
          return (
            <div key={t.id} className="rounded-lg border p-4 text-sm space-y-2">
              <div className="flex items-start justify-between gap-3">
                <span className="font-medium">
                  {transactionLabel(t.type)}
                  {t.credits ? (
                    <span className="text-muted-foreground"> · {t.credits} credits</span>
                  ) : null}
                </span>
                <span className="font-semibold whitespace-nowrap">
                  {formatAmount(t.amount_paise, t.currency)}
                </span>
              </div>
              <div className="flex items-center justify-between gap-3 text-muted-foreground">
                <span>{formatDate(t.created_at)}</span>
                <Badge variant={success ? 'secondary' : 'outline'}>
                  {t.status ? t.status.replace(/_/g, ' ') : '—'}
                </Badge>
              </div>
              <div className="text-right">
                {t.invoice_url ? (
                  <a
                    href={t.invoice_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    Download invoice
                  </a>
                ) : (
                  <span className="text-muted-foreground">No invoice</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Desktop table */}
      <div className="hidden sm:block overflow-x-auto -mx-4 px-4 sm:mx-0 sm:px-0">
        <table className="hidden sm:table w-full text-sm">
          <thead>
            <tr className="border-b text-muted-foreground text-left">
              <th className="py-2 pr-4 font-medium">Date</th>
              <th className="py-2 pr-4 font-medium">Description</th>
              <th className="py-2 pr-4 font-medium text-right">Amount</th>
              <th className="py-2 pr-4 font-medium text-right">Status</th>
              <th className="py-2 font-medium text-right">Invoice</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => {
              const success = (t.status || '').toLowerCase() === 'success';
              return (
                <tr key={t.id} className="border-b last:border-0">
                  <td className="py-3 pr-4 whitespace-nowrap">{formatDate(t.created_at)}</td>
                  <td className="py-3 pr-4">
                    {transactionLabel(t.type)}
                    {t.credits ? (
                      <span className="text-muted-foreground"> · {t.credits} credits</span>
                    ) : null}
                  </td>
                  <td className="py-3 pr-4 text-right whitespace-nowrap">
                    {formatAmount(t.amount_paise, t.currency)}
                  </td>
                  <td className="py-3 pr-4 text-right">
                    <Badge variant={success ? 'secondary' : 'outline'}>
                      {t.status ? t.status.replace(/_/g, ' ') : '—'}
                    </Badge>
                  </td>
                  <td className="py-3 text-right whitespace-nowrap">
                    {t.invoice_url ? (
                      <a
                        href={t.invoice_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-primary underline-offset-4 hover:underline"
                      >
                        Download
                      </a>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function BillingPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const isAuthReady = !loading;
  const { data: billing, isLoading, error, refetch } = useBillingStatus(isAuthReady);

  const PAGE_SIZE = 10;
  const [txPage, setTxPage] = useState(0);
  const { data: txData, isFetching: txFetching } = useBillingTransactions(
    txPage,
    PAGE_SIZE,
    isAuthReady
  );

  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [showTopUpModal, setShowTopUpModal] = useState(false);

  // Poll for status updates after a payment modal is closed or during a locked state
  useEffect(() => {
    if (!billing) return;

    // Poll every 3 seconds if we are in a pending activation or locked state, as webhook might fix it
    if ((billing.subscription_status === 'trial' && !billing.trial_ends_at) || billing.is_org_locked) {
      const interval = setInterval(() => {
        refetch();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [billing, refetch]);

  useEffect(() => {
    if (isAuthReady && user) {
      if (user.role !== 'Owner' && user.role !== 'Admin') {
        router.push('/dashboard');
      }
    }
  }, [user, isAuthReady, router]);

  if (!isAuthReady || isLoading) {
    return (
      <div className="p-6">
        <BillingSkeleton />
      </div>
    );
  }

  if (error || !billing) {
    return (
      <div className="p-6 text-destructive flex flex-col items-center justify-center space-y-4">
        <p>Failed to load billing information.</p>
        <Button onClick={() => refetch()}>Retry</Button>
      </div>
    );
  }

  const planName = billing.plan === 'active' ? 'Paid Plan' : billing.plan || 'Free Tier';
  const status = statusPresentation(billing.subscription_status);
  const transactions = txData?.transactions ?? [];
  const txTotal = txData?.total ?? 0;
  const txPageCount = Math.max(1, Math.ceil(txTotal / PAGE_SIZE));
  const txRangeStart = txTotal === 0 ? 0 : txPage * PAGE_SIZE + 1;
  const txRangeEnd = Math.min(txTotal, txPage * PAGE_SIZE + transactions.length);

  const activeLocations = billing.active_location_count ?? 0;
  const locationQuota = billing.location_quota ?? 0;
  const monthlyAllowance = billing.monthly_ai_credits_allowance ?? 0;
  const monthlyBalance = billing.monthly_ai_credits_balance ?? 0;

  const renewalDate = billing.subscription_ends_at
    ? `Cancels ${formatDate(billing.subscription_ends_at)}`
    : billing.current_period_end
      ? `Renews ${formatDate(billing.current_period_end)}`
      : null;

  return (
    <div className="p-4 sm:p-6 space-y-6 max-w-5xl mx-auto">
      <h1 className="text-2xl sm:text-3xl font-bold">Billing &amp; Plans</h1>

      {/* Status hero strip */}
      <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div className="space-y-1">
            <div className="flex items-center gap-3">
              <span className="text-xl font-semibold capitalize">{planName}</span>
              <Badge variant={status.variant}>{status.label}</Badge>
            </div>
            <p className="text-sm text-muted-foreground">
              {renewalDate ?? 'No active subscription'}
              {billing.pending_location_count
                ? ` · ${billing.pending_location_count} location(s) pending payment`
                : ''}
            </p>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="outline" className="w-full h-11 sm:w-auto sm:h-8" onClick={() => setShowTopUpModal(true)}>
              Buy Credits
            </Button>
            <Button className="w-full h-11 sm:w-auto sm:h-8" onClick={() => setShowUpgradeModal(true)}>Upgrade Plan</Button>
          </div>
        </div>
      </div>

      {/* Usage */}
      <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm space-y-6">
        <h2 className="text-xl font-semibold">Usage &amp; Limits</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <UsageBar
            label="Locations"
            used={activeLocations}
            total={locationQuota}
            hint={`${locationQuota} included in your plan`}
          />
          <UsageBar
            label="Monthly AI Credits"
            used={monthlyBalance}
            total={monthlyAllowance}
            hint={resetHint(billing)}
          />
          <div className="space-y-2">
            <div className="flex justify-between items-baseline text-sm">
              <span className="font-medium">Top-up Credits</span>
              <span className="text-muted-foreground">{billing.topup_ai_credits_balance}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-secondary overflow-hidden">
              <div className="h-full rounded-full bg-primary" style={{ width: '100%' }} />
            </div>
            <p className="text-xs text-muted-foreground">Never expire · top up anytime</p>
          </div>
        </div>
      </div>

      {/* Billing history */}
      <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm space-y-4">
        <h2 className="text-xl font-semibold">Billing History</h2>
        <TransactionsTable rows={transactions} />
        {txTotal > 0 && (
          <div className="flex items-center justify-between pt-2 text-sm">
            <span className="text-muted-foreground">
              Showing {txRangeStart}–{txRangeEnd} of {txTotal}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-10 px-4 sm:h-7 sm:px-2.5"
                disabled={txPage === 0 || txFetching}
                onClick={() => setTxPage((p) => Math.max(0, p - 1))}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="h-10 px-4 sm:h-7 sm:px-2.5"
                disabled={txPage >= txPageCount - 1 || txFetching}
                onClick={() => setTxPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </div>

      <UpgradeModal open={showUpgradeModal} onOpenChange={setShowUpgradeModal} />
      <TopUpModal open={showTopUpModal} onOpenChange={setShowTopUpModal} />
    </div>
  );
}
