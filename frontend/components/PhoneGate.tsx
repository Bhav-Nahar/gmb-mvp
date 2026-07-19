'use client';

import { useState } from 'react';
import { Phone, ShieldCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import { CARD_REQUIRED_ONBOARDING } from '@/lib/onboarding';
import { COUNTRY_CODES, parsePhoneState } from '@/lib/phone';

/**
 * Required onboarding gate: a signed-in user with no phone on file sees a blocking
 * overlay before the dashboard/audit. Captured for sales follow-up (surfaced in the
 * super-admin panel). Mounted in the dashboard layout so it catches every entry until
 * the number is provided, which is what makes it "required".
 *
 * No OTP: we enforce a well-formed international number (selectable country code,
 * 7–15 local digits) rather than verifying ownership. Stored in E.164 format (e.g. "+91XXXXXXXXXX").
 */
export function PhoneGate() {
  const { user, refresh } = useAuth();
  
  // Initialize from user.phone if they have one, else detect from timezone
  const [countryCode, setCountryCode] = useState(() => parsePhoneState(user?.phone).code);
  const [digits, setDigits] = useState(() => parsePhoneState(user?.phone).digits);
  
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // In the card-required flow the OnboardingGate collects the phone inline (one screen,
  // one click), so this separate step is suppressed to avoid a redundant gate.
  if (CARD_REQUIRED_ONBOARDING) return null;

  // Nothing to gate until we know who they are and that a number is missing.
  if (!user || user.phone) return null;

  const valid = digits.length >= 7 && digits.length <= 15;

  const submit = async () => {
    setError(null);
    if (!valid) {
      setError('Please enter a valid mobile number.');
      return;
    }
    setSubmitting(true);
    try {
      await api.post('/users/me/phone', { phone: `${countryCode}${digits}` });
      await refresh(); // re-fetch /users/me, user.phone set, gate disappears
    } catch (e: any) {
      setError(e?.message || 'We could not save your number. Please try again.');
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="w-full max-w-md space-y-5 rounded-2xl border bg-card p-8 shadow-2xl">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
          <Phone className="h-6 w-6 text-primary" />
        </div>

        <div className="space-y-1 text-center">
          <h2 className="text-xl font-bold">Almost there</h2>
          <p className="text-sm text-muted-foreground">
            Add your mobile number to unlock your Google Business audit. Our team may reach
            out to help you improve your score.
          </p>
        </div>

        <div>
          <div className="flex items-stretch overflow-hidden rounded-xl border focus-within:ring-2 focus-within:ring-ring">
            <select
              value={countryCode}
              onChange={(e) => setCountryCode(e.target.value)}
              className="bg-muted px-2 py-2.5 text-sm font-semibold text-muted-foreground outline-none border-r border-border hover:bg-muted/80 cursor-pointer"
            >
              {COUNTRY_CODES.map(c => (
                <option key={c.code} value={c.code}>{c.label}</option>
              ))}
            </select>
            <input
              type="tel"
              inputMode="numeric"
              autoFocus
              value={digits}
              // Strip anything that isn't a digit and cap at 15 for max international length
              onChange={(e) => setDigits(e.target.value.replace(/\D/g, '').slice(0, 15))}
              onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
              placeholder="98765 43210"
              className="flex-1 bg-background px-4 py-2.5 text-sm focus:outline-none"
            />
          </div>
          {error && <p className="mt-1.5 text-xs text-destructive">{error}</p>}
        </div>

        <button
          onClick={submit}
          disabled={submitting || !valid}
          className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground shadow-sm transition hover:bg-primary/90 disabled:opacity-50"
        >
          {submitting ? 'Saving...' : 'Continue to my audit'}
        </button>

        <p className="flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5" />
          We never share your number. No spam.
        </p>
      </div>
    </div>
  );
}
