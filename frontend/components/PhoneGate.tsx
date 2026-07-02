'use client';

import { useState } from 'react';
import { Phone } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

/**
 * Required onboarding gate: a signed-in user with no phone on file sees a blocking
 * overlay before the dashboard/audit. Captured for sales follow-up (surfaced in the
 * super-admin panel). Mounted in the dashboard layout so it catches every entry until
 * the number is provided — that's what makes it "required".
 *
 * No OTP: we enforce a well-FORMED Indian number (fixed +91, exactly 10 digits,
 * digits-only) rather than verifying ownership. Stored E.164 as "+91XXXXXXXXXX".
 */
export function PhoneGate() {
  const { user, refresh } = useAuth();
  const [digits, setDigits] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Nothing to gate until we know who they are and that a number is missing.
  if (!user || user.phone) return null;

  const valid = digits.length === 10;

  const submit = async () => {
    setError(null);
    if (!valid) {
      setError('Enter a 10-digit mobile number.');
      return;
    }
    setSubmitting(true);
    try {
      await api.post('/users/me/phone', { phone: `+91${digits}` });
      await refresh(); // re-fetch /users/me → user.phone set → gate disappears
    } catch (e: any) {
      setError(e?.message || 'Could not save your number. Please try again.');
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm p-4">
      <div className="bg-card p-8 rounded-2xl shadow-xl max-w-md w-full text-center space-y-4 border">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Phone className="h-6 w-6 text-primary" />
        </div>
        <h2 className="text-xl font-bold">One last step</h2>
        <p className="text-sm text-muted-foreground">
          Enter your mobile number to view your Google Business audit. Our team may reach
          out to help you improve your score.
        </p>
        <div className="flex items-stretch rounded-lg border border-border overflow-hidden focus-within:ring-2 focus-within:ring-ring">
          <span className="flex items-center px-3 bg-muted text-sm font-semibold text-muted-foreground select-none">
            +91
          </span>
          <input
            type="tel"
            inputMode="numeric"
            autoFocus
            value={digits}
            // Strip everything that isn't a digit and cap at 10 — so letters/spaces/symbols
            // simply can't be entered, and the length is guaranteed.
            onChange={(e) => setDigits(e.target.value.replace(/\D/g, '').slice(0, 10))}
            onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
            placeholder="98765 43210"
            className="flex-1 bg-background px-4 py-2.5 text-sm focus:outline-none"
          />
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
        <button
          onClick={submit}
          disabled={submitting || !valid}
          className="w-full rounded-lg bg-primary px-4 py-2.5 text-sm font-bold text-primary-foreground hover:opacity-90 disabled:opacity-50"
        >
          {submitting ? 'Saving…' : 'Verify & Continue'}
        </button>
      </div>
    </div>
  );
}
