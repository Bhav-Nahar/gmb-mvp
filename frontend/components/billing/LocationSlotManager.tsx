'use client';

import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { useBillingStatus, useSetActiveLocations } from '@/hooks/useBilling';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { Check, Lock } from 'lucide-react';

interface Loc {
  id: number;
  location_name?: string;
  address?: string;
  billing_status?: string;
}

/**
 * Lets the owner choose WHICH locations occupy their paid slots when they have more
 * locations than their plan covers — instead of the system silently keeping the
 * oldest by id. Free: it only reassigns within quota (going above quota still needs
 * the paid add-on flow). Shown only when there's an actual choice to make
 * (locations > quota).
 */
export function LocationSlotManager() {
  const { data: billing } = useBillingStatus();
  const queryClient = useQueryClient();
  const { mutateAsync: setActive, isPending: saving } = useSetActiveLocations();

  const { data: locations } = useQuery({
    queryKey: ['locations'],
    queryFn: () => api.get<Loc[]>('/locations/'),
    enabled: !!billing,
  });

  const quota = billing?.location_quota ?? 0;
  const activeIds = useMemo(
    () => (locations ?? []).filter((l) => l.billing_status === 'active').map((l) => l.id),
    [locations]
  );
  const [selected, setSelected] = useState<Set<number> | null>(null);
  // Initialise the selection from the server's current active set once loaded.
  const sel = selected ?? new Set(activeIds);

  // Only surface the picker when the owner actually has to choose.
  if (!billing || !locations || locations.length <= quota) return null;

  const toggle = (id: number) => {
    const next = new Set(sel);
    if (next.has(id)) {
      next.delete(id);
    } else {
      if (next.size >= quota) {
        toast.info(`Your plan covers ${quota} location${quota === 1 ? '' : 's'}. Unselect one first, or add more from Upgrade Plan.`);
        return;
      }
      next.add(id);
    }
    setSelected(next);
  };

  const changed =
    sel.size !== activeIds.length || activeIds.some((id) => !sel.has(id));

  // Free reassignment is rate-limited; the server tells us when the next change is allowed.
  const availableAt = billing.location_reassign_available_at
    ? new Date(billing.location_reassign_available_at)
    : null;
  const cooldownActive = !!availableAt && availableAt.getTime() > Date.now();

  const save = async () => {
    try {
      const res = await setActive(Array.from(sel));
      toast.success(`${res.active_location_count} location${res.active_location_count === 1 ? '' : 's'} active.`);
      setSelected(null); // re-sync from server on next render
      queryClient.invalidateQueries({ queryKey: ['locations'] });
      queryClient.invalidateQueries({ queryKey: ['billing_status'] });
      queryClient.invalidateQueries({ queryKey: ['pending_locations'] });
      window.dispatchEvent(new Event('billing:refresh'));
    } catch (e: any) {
      toast.error(e?.message || 'Could not update active locations.');
    }
  };

  return (
    <div className="border rounded-xl p-6 bg-card text-card-foreground shadow-sm space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-xl font-semibold">Active Locations</h2>
        <span className="text-sm text-muted-foreground">{sel.size} / {quota} slots</span>
      </div>
      <p className="text-sm text-muted-foreground">
        You have {locations.length} locations but your plan covers {quota}. Choose which to keep
        active — the rest are locked until you activate them or add more slots.
      </p>

      <ul className="space-y-2">
        {locations.map((loc) => {
          const on = sel.has(loc.id);
          const atCap = !on && sel.size >= quota;
          return (
            <li key={loc.id}>
              <button
                type="button"
                onClick={() => toggle(loc.id)}
                disabled={atCap}
                className={`w-full flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                  on ? 'border-primary bg-primary/10' : 'border-border hover:bg-muted/40'
                } ${atCap ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              >
                <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded border ${
                  on ? 'bg-primary border-primary text-primary-foreground' : 'border-muted-foreground/40'
                }`}>
                  {on ? <Check className="h-3.5 w-3.5" /> : <Lock className="h-3 w-3 text-muted-foreground" />}
                </span>
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {loc.location_name || `Location #${loc.id}`}
                  </span>
                  {loc.address && (
                    <span className="block truncate text-xs text-muted-foreground">{loc.address}</span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="flex items-center justify-end gap-3">
        {cooldownActive && (
          <span className="text-xs text-muted-foreground">
            Next change available {availableAt!.toLocaleDateString()}
          </span>
        )}
        <Button onClick={save} disabled={!changed || saving || sel.size === 0 || cooldownActive}>
          {saving ? 'Saving…' : 'Save active locations'}
        </Button>
      </div>
    </div>
  );
}
