'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';

// Meta redirects here after the client finishes Embedded Signup, with ?code=.
//
// This URL is registered on the Meta app and must match EXACTLY, trailing slash
// included — a mismatch fails the token exchange with an error that names
// neither side. Changing this path means changing it in the Meta app too.
//
// The code is posted straight to the backend and never stored: it is
// single-use, short-lived, and the exchange needs the app secret, which only
// the server has.

type Phase = 'working' | 'error';

// useSearchParams() opts a client component out of prerendering, so Next
// requires a Suspense boundary above it or the production build fails. The
// exported page is therefore a thin wrapper; the work lives in the inner
// component.
function WhatsAppCallback() {
  const router = useRouter();
  const params = useSearchParams();
  const [phase, setPhase] = useState<Phase>('working');
  const [error, setError] = useState<string>('');
  // React runs effects twice in development. The code is single-use, so a
  // second exchange always fails — and would show the user an error on a
  // connection that actually succeeded.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    const code = params.get('code');
    const state = params.get('state');
    const denied = params.get('error_description') || params.get('error');

    if (denied) {
      setPhase('error');
      setError(denied);
      return;
    }
    if (!code) {
      setPhase('error');
      setError('Meta did not return a connection code. Please start the connection again.');
      return;
    }

    api
      .post('/whatsapp/connect', { code, state })
      .then(() => router.replace('/dashboard/settings/whatsapp?connected=1'))
      .catch((err: unknown) => {
        setPhase('error');
        setError(err instanceof Error ? err.message : 'The connection could not be completed.');
      });
  }, [params, router]);

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-lg border p-6 text-center">
        {phase === 'working' ? (
          <>
            <h1 className="text-lg font-semibold">Connecting WhatsApp…</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Setting up your account with Meta. This takes a few seconds.
            </p>
          </>
        ) : (
          <>
            <h1 className="text-lg font-semibold">We couldn&apos;t finish connecting</h1>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
            <button
              onClick={() => router.replace('/dashboard/settings/whatsapp')}
              className="mt-4 text-sm font-medium underline"
            >
              Back to WhatsApp settings
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function WhatsAppCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center p-6">
          <div className="w-full max-w-md rounded-lg border p-6 text-center">
            <h1 className="text-lg font-semibold">Connecting WhatsApp…</h1>
          </div>
        </div>
      }
    >
      <WhatsAppCallback />
    </Suspense>
  );
}
