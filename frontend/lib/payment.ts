/**
 * Shared helpers for the Razorpay confirm flow.
 *
 * After a Razorpay checkout succeeds in the browser, the client calls the backend
 * `/billing/confirm` to verify the signature server-side. If that call THROWS we must
 * not blindly tell the user "Payment received!" — a thrown error can be a genuine
 * verification failure (bad/forged signature, or a subscription/order that doesn't
 * belong to this org), which means nothing was granted.
 */

/** True when a confirm error indicates a real verification/authorization failure
 * rather than a transient network blip. Used to pick an honest toast. */
export function isPaymentVerificationError(err: unknown): boolean {
  const msg = (err as { message?: string } | null)?.message ?? String(err ?? '');
  return /signature|verif|does not belong|invalid|forbidden|unauthor|400/i.test(msg);
}

/** Message shown when confirm failed verification — never implies success. */
export const PAYMENT_VERIFICATION_FAILED_MSG =
  'We could not verify this payment. If you were charged, it will be reconciled automatically — contact support if credits/locations do not appear.';
