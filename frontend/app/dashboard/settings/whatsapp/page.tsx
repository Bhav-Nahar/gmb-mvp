'use client';

import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

type SignupConfig = { app_id: string; config_id: string; graph_version: string };

type FbLoginResponse = {
  status?: string;
  authResponse?: { code?: string } | null;
};

type FbSdk = {
  init: (opts: { appId: string; cookie?: boolean; xfbml?: boolean; version: string }) => void;
  login: (cb: (r: FbLoginResponse) => void, opts: Record<string, unknown>) => void;
};

declare global {
  interface Window {
    FB?: FbSdk;
    fbAsyncInit?: () => void;
  }
}

// Loaded on demand rather than in the app shell: this is the only page that
// needs Facebook's SDK, and every other page paying for a third-party script
// (and its cookies) would be a poor trade.
let sdkPromise: Promise<FbSdk> | null = null;

function loadFacebookSdk(appId: string, version: string): Promise<FbSdk> {
  if (window.FB) {
    window.FB.init({ appId, cookie: true, xfbml: false, version });
    return Promise.resolve(window.FB);
  }
  if (sdkPromise) return sdkPromise;

  sdkPromise = new Promise<FbSdk>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://connect.facebook.net/en_US/sdk.js';
    script.async = true;
    script.crossOrigin = 'anonymous';
    script.onerror = () => {
      sdkPromise = null;   // let a later attempt retry rather than fail forever
      reject(new Error('Could not load Facebook. Check for a blocker on this page.'));
    };
    window.fbAsyncInit = () => {
      window.FB!.init({ appId, cookie: true, xfbml: false, version });
      resolve(window.FB!);
    };
    document.body.appendChild(script);
  });
  return sdkPromise;
}

type WhatsAppStatus = {
  connected: boolean;
  status: string;
  status_detail: string | null;
  display_phone_number: string | null;
  verified_name: string | null;
  quality_rating: string | null;
  messaging_tier: string | null;
  template_status: string | null;
  can_send: boolean;
  can_test: boolean;
  webhooks_ok: boolean;
  test_send_done: boolean;
  // 'status' | 'webhooks' | 'test_send' | null — the one thing left to do.
  setup_blocker: string | null;
};

type LocationOption = { id: number; location_name: string };

// The onboarding state machine, in the words a customer needs.
//
// Every one of these is a state a tenant can genuinely get stuck in, and each
// needs a different action from THEM — which is exactly why the backend tracks
// a status rather than a boolean. "Not connected" and "your number is still in
// the WhatsApp app" are not the same problem.
const STATE_COPY: Record<string, {
  label: string; tone: 'ok' | 'waiting' | 'action'; help: string;
  // Where the tenant has to go to fix it. Only set for states that cannot be
  // resolved inside Pinzo — telling someone to add a payment method without
  // saying where is the same as not telling them.
  action?: { label: string; href: string };
}> = {
  not_connected: {
    label: 'Not connected',
    tone: 'action',
    help: 'Connect your WhatsApp Business Account to start asking customers for Google reviews.',
  },
  pending: {
    label: 'Setup started',
    tone: 'waiting',
    help: 'The connection was started but not finished. Connect again to complete it.',
  },
  connected: {
    label: 'Connected',
    tone: 'waiting',
    help: 'Your account is linked. Finishing the remaining setup steps with Meta.',
  },
  number_registered: {
    label: 'Number registered',
    tone: 'waiting',
    help: 'Your number is active. Waiting on the message template to be approved.',
  },
  payment_required: {
    label: 'Payment method needed',
    tone: 'action',
    help:
      'Meta needs a payment method on your WhatsApp Business Account before messages can be sent. ' +
      'You pay Meta directly for messages — Pinzo adds no markup.',
    action: {
      label: 'Add a payment method on Meta',
      href: 'https://business.facebook.com/settings/whatsapp-business-accounts',
    },
  },
  template_pending: {
    label: 'Template in review',
    tone: 'waiting',
    help: 'Meta is reviewing your review-request template. This is usually under an hour, and sending unlocks automatically.',
  },
  ready: {
    label: 'Ready',
    tone: 'ok',
    help: 'You can send review requests.',
  },
  disabled: {
    label: 'Paused',
    tone: 'action',
    help: 'Sending is paused. See the note below. Once Meta restores your number’s quality '
      + 'rating this clears on its own — or press “Check again”.',
  },
  reauth_required: {
    label: 'Reconnect needed',
    tone: 'action',
    help:
      'Pinzo’s access to your WhatsApp account has ended — this happens if the '
      + 'connection was removed in Meta Business Settings. Reconnect to start sending again. '
      + 'Your number, templates and history are untouched.',
  },
};

function toneVariant(tone: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (tone === 'ok') return 'default';
  if (tone === 'waiting') return 'secondary';
  return 'destructive';
}

// Meta reports quality as a colour. Say what it means for the tenant, because
// "YELLOW" on its own reads as decoration rather than a warning.
const QUALITY_COPY: Record<string, string> = {
  GREEN: 'Good — recipients are engaging with your messages.',
  YELLOW: 'Declining — some recipients are blocking or reporting. Send to fewer, warmer contacts.',
  RED: 'Low — sending is paused to protect your number. It recovers with a period of good sending.',
};

export default function WhatsAppSettingsPage() {
  const params = useSearchParams();
  const [status, setStatus] = useState<WhatsAppStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [templateMsg, setTemplateMsg] = useState('');
  const [locations, setLocations] = useState<LocationOption[]>([]);
  const [testPhone, setTestPhone] = useState('');
  const [testLocationId, setTestLocationId] = useState<string>('');
  const [testMsg, setTestMsg] = useState('');

  const load = useCallback(async () => {
    try {
      setStatus(await api.get<WhatsAppStatus>('/whatsapp/status'));
      setError('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not load WhatsApp status.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // The test message needs a location, because the review link it carries is a
  // real one — the admin taps it and lands on that location's Google review page,
  // which is the only way to confirm the whole chain works end to end.
  useEffect(() => {
    api.get<LocationOption[]>('/locations/')
      .then((rows) => {
        setLocations(rows);
        if (rows.length) setTestLocationId(String(rows[0].id));
      })
      .catch(() => { /* the test-send box just stays hidden */ });
  }, []);

  // Template approval and quality changes arrive on Meta's webhook, so the
  // status can change without the user doing anything. Poll while the account
  // is in a waiting state rather than making them refresh to find out.
  useEffect(() => {
    if (!status) return;
    const waiting = ['connected', 'number_registered', 'template_pending'].includes(status.status);
    if (!waiting) return;
    const id = setInterval(load, 20_000);
    return () => clearInterval(id);
  }, [status, load]);

  // Embedded Signup runs in Meta's own popup via the Facebook JS SDK. The
  // hosted-landing URL is NOT a supported entry point — it answers "Sorry,
  // something went wrong" — so the SDK is the flow, and the /connect-url
  // endpoint now just hands over the two public ids it needs.
  //
  // The popup also means no redirect URI is involved: the code comes back to
  // this page, so localhost works and no tunnel is needed to test.
  const connect = async () => {
    setBusy(true);
    setError('');

    // Meta postMessages the progress of its own popup. The WABA and phone ids
    // in it are deliberately IGNORED — the backend asks Meta which WABA the
    // token actually grants, because anything arriving from a browser can be
    // edited, and trusting it would let one tenant attach another's account.
    // What is worth keeping is the step a user dropped out on: otherwise a
    // failed signup is indistinguishable from a closed window.
    const onSignupMessage = (event: MessageEvent) => {
      if (event.origin !== 'https://www.facebook.com'
          && event.origin !== 'https://web.facebook.com') return;
      try {
        const data = JSON.parse(event.data);
        if (data?.type !== 'WA_EMBEDDED_SIGNUP') return;
        if (data.event === 'CANCEL') {
          setError(data.data?.current_step
            ? `WhatsApp signup was cancelled at: ${String(data.data.current_step)
                .toLowerCase().replace(/_/g, ' ')}.`
            : 'WhatsApp signup was cancelled.');
        } else if (data.event === 'ERROR') {
          setError(data.data?.error_message || 'Meta reported an error during signup.');
        }
      } catch {
        /* not our message — Meta's SDK chatters on this channel */
      }
    };
    window.addEventListener('message', onSignupMessage);
    const stopListening = () => window.removeEventListener('message', onSignupMessage);

    try {
      const cfg = await api.get<SignupConfig>('/whatsapp/connect-url');
      const FB = await loadFacebookSdk(cfg.app_id, cfg.graph_version);

      FB.login(
        (response) => {
          const code = response?.authResponse?.code;
          stopListening();
          if (!code) {
            // Closing the popup is a normal thing to do, not an error worth shouting about.
            setError(response?.status === 'unknown'
              ? ''
              : 'The WhatsApp signup was cancelled before it finished.');
            setBusy(false);
            return;
          }
          (async () => {
            try {
              await api.post('/whatsapp/connect', { code, source: 'sdk' });
              await load();
            } catch (err) {
              setError(err instanceof Error ? err.message : 'Could not finish connecting.');
            } finally {
              setBusy(false);
            }
          })();
        },
        {
          config_id: cfg.config_id,
          // Ask for a CODE, not a browser access token: the token must be
          // exchanged server-side with the app secret, which never leaves the
          // backend. override_default_response_type is what makes that stick.
          response_type: 'code',
          override_default_response_type: true,
          // Copied from the snippet Meta generates for this configuration —
          // extras is an opaque config blob and a hand-written one gets rejected.
          // sessionInfoVersion is added so the postMessage payload arrives as
          // JSON v3, which is what the listener below parses.
          extras: { version: 'v4', sessionInfoVersion: '3' },
        },
      );
    } catch (err) {
      stopListening();
      setError(err instanceof Error ? err.message : 'Could not start the connection.');
      setBusy(false);
    }
  };

  // Creates the Pinzo-authored template on this org's WABA. Not an editor:
  // the copy is a policy surface and the structure (2 variables + the token
  // button) is what makes the review link work at all.
  const createTemplate = async () => {
    setBusy(true);
    setTemplateMsg('');
    setError('');
    try {
      const res = await api.post<{ template_name: string; template_status: string; created: boolean; message: string }>(
        '/whatsapp/template',
      );
      setTemplateMsg(res.message);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the template.');
    } finally {
      setBusy(false);
    }
  };

  // The way out of every blocked state. Whether a Meta payment method works is
  // not something any API will tell us, so a tenant who says they have added one
  // is believed: the account unparks, and the next send either works or parks it
  // again with the same explanation. Without this button, "payment needed" and
  // "quality too low" were one-way doors that needed a database edit to open.
  const recheck = async () => {
    setBusy(true);
    setError('');
    setTemplateMsg('');
    try {
      const next = await api.post<WhatsAppStatus>('/whatsapp/recheck');
      setStatus(next);
      setTemplateMsg(
        next.can_send
          ? 'All clear — you can send review requests.'
          : next.status === 'ready'
            ? 'Meta setup looks good. Finish the steps below to unlock sending.'
            : 'Still blocked at Meta. The note above says what is outstanding.',
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not re-check with Meta.');
    } finally {
      setBusy(false);
    }
  };

  // One real message to the admin's own phone, before any customer sees anything.
  // Three failures are invisible until a live send: no payment method on the
  // tenant's WhatsApp account, a template approved in our records but not at
  // Meta, and a number that never finished registering. One message here or 300
  // failures in front of their customers — this is the cheap version.
  const sendTest = async () => {
    if (!testPhone.trim() || !testLocationId) return;
    setBusy(true);
    setError('');
    setTestMsg('');
    try {
      const res = await api.post<{ ok: boolean; message: string; status: WhatsAppStatus }>(
        '/whatsapp/test-send',
        { phone: testPhone.trim(), location_id: Number(testLocationId) },
      );
      setTestMsg(res.message);
      setStatus(res.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not send the test message.');
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    if (!confirm('Disconnect WhatsApp? Your WhatsApp account, number and templates stay with Meta — only Pinzo forgets them.')) {
      return;
    }
    setBusy(true);
    try {
      await api.delete('/whatsapp/disconnect');
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not disconnect.');
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading WhatsApp settings…</div>;
  }

  const key = status?.connected ? status.status : 'not_connected';
  const copy = STATE_COPY[key] ?? {
    label: key,
    tone: 'waiting' as const,
    help: 'Setup is in progress.',
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">WhatsApp</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Ask your customers for Google reviews over WhatsApp. Messages are sent from your own
          WhatsApp Business number and billed by Meta directly to you — Pinzo adds no markup.
        </p>
      </div>

      {params.get('connected') === '1' && (
        <div className="rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-900">
          WhatsApp connected. Any remaining setup steps are shown below.
        </div>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</div>
      )}

      <div className="rounded-lg border p-5">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="font-medium">Status</span>
              <Badge variant={toneVariant(copy.tone)}>{copy.label}</Badge>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{copy.help}</p>
            {copy.action && (
              <a
                href={copy.action.href}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-sm font-medium underline"
              >
                {copy.action.label} →
              </a>
            )}
            {status?.status_detail && (
              <p className="mt-2 text-sm text-amber-700">{status.status_detail}</p>
            )}
          </div>

          <div className="flex shrink-0 flex-col items-end gap-2">
            {status?.connected ? (
              <>
                {/* Every blocked state has to have a way out that the tenant can
                    press themselves, or "payment needed" becomes a support
                    ticket and a database edit. */}
                <Button variant="outline" onClick={recheck} disabled={busy}>
                  {busy ? 'Checking…' : 'Check again'}
                </Button>
                {status.status === 'reauth_required' && (
                  <Button onClick={connect} disabled={busy}>Reconnect</Button>
                )}
                <Button variant="ghost" onClick={disconnect} disabled={busy}>
                  Disconnect
                </Button>
              </>
            ) : (
              <Button onClick={connect} disabled={busy}>
                {busy ? 'Opening…' : 'Connect WhatsApp'}
              </Button>
            )}
          </div>
        </div>

        {status?.connected && (
          <dl className="mt-5 grid grid-cols-2 gap-4 border-t pt-5 text-sm">
            <div>
              <dt className="text-muted-foreground">Number</dt>
              <dd className="mt-0.5 font-medium">{status.display_phone_number || '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Display name</dt>
              <dd className="mt-0.5 font-medium">{status.verified_name || '—'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Message template</dt>
              <dd className="mt-0.5 font-medium">{status.template_status || 'Not created yet'}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">Daily send tier</dt>
              {/* Meta raises this as your number earns trust — worth showing so a
                  capped campaign explains itself instead of looking broken. */}
              <dd className="mt-0.5 font-medium">
                {status.messaging_tier?.replace('TIER_', '') || '—'}
              </dd>
            </div>
            {status.quality_rating && (
              <div className="col-span-2">
                <dt className="text-muted-foreground">Quality rating</dt>
                <dd className="mt-0.5">
                  <span className="font-medium">{status.quality_rating}</span>
                  <span className="ml-2 text-muted-foreground">
                    {QUALITY_COPY[status.quality_rating] || ''}
                  </span>
                </dd>
              </div>
            )}
          </dl>
        )}
      </div>

      {/* The three facts behind "you can run a campaign". Shown as a checklist
          because a tenant staring at a disabled Send button deserves to know
          which step is outstanding, not just that something is. */}
      {status?.connected && !status.can_send && (
        <div className="rounded-lg border p-5">
          <h2 className="text-sm font-medium">Before your first campaign</h2>
          <ul className="mt-3 space-y-2 text-sm">
            <li className="flex gap-2">
              <span>{status.status === 'ready' ? '✅' : '⬜'}</span>
              <span>
                WhatsApp setup finished with Meta
                {status.status !== 'ready' && (
                  <span className="text-muted-foreground"> — see the status above.</span>
                )}
              </span>
            </li>
            <li className="flex gap-2">
              <span>{status.webhooks_ok ? '✅' : '⬜'}</span>
              <span>
                Pinzo receives updates from your account
                {!status.webhooks_ok && (
                  <span className="text-muted-foreground">
                    {' '}— without this, a customer replying STOP would never be recorded, so
                    sending stays locked. Press “Check again”.
                  </span>
                )}
              </span>
            </li>
            <li className="flex gap-2">
              <span>{status.test_send_done ? '✅' : '⬜'}</span>
              <span>
                One test message delivered
                {!status.test_send_done && (
                  <span className="text-muted-foreground">
                    {' '}— proves your Meta payment method and template actually work.
                  </span>
                )}
              </span>
            </li>
          </ul>
        </div>
      )}

      {status?.connected && status.can_test && !status.test_send_done && locations.length > 0 && (
        <div className="rounded-lg border p-5">
          <h2 className="text-sm font-medium">Send yourself a test message</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Your own WhatsApp number. Tap the button in the message to check the review link
            lands on the right Google page. This is one real message billed by Meta at their
            normal rate — the only way to prove your payment method works before your customers
            are involved.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <input
              value={testPhone}
              onChange={(e) => setTestPhone(e.target.value)}
              placeholder="98765 43210"
              inputMode="tel"
              className="h-9 w-44 rounded-md border px-3 text-sm"
            />
            <select
              value={testLocationId}
              onChange={(e) => setTestLocationId(e.target.value)}
              className="h-9 rounded-md border px-2 text-sm"
            >
              {locations.map((l) => (
                <option key={l.id} value={l.id}>{l.location_name}</option>
              ))}
            </select>
            <Button onClick={sendTest} disabled={busy || !testPhone.trim()}>
              {busy ? 'Sending…' : 'Send test'}
            </Button>
          </div>
          {testMsg && <p className="mt-3 text-sm text-amber-700">{testMsg}</p>}
        </div>
      )}

      {status?.connected && (
        <div className="rounded-lg border p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-sm font-medium">Message template</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                The approved message your customers receive. Pinzo writes and maintains this —
                it has to follow WhatsApp&apos;s marketing rules and Google&apos;s review policy,
                and the review button only works with the exact structure below.
              </p>
              <div className="mt-3 rounded-md bg-muted/40 p-3 text-sm">
                <p>
                  Hi <span className="text-muted-foreground">[customer name]</span>, thank you for
                  choosing <span className="text-muted-foreground">[your business]</span>! If we
                  looked after you well, would you mind leaving us a quick Google review?
                </p>
                <p className="mt-2 text-xs text-muted-foreground">Reply STOP to opt out.</p>
                <p className="mt-2 inline-block rounded border px-2 py-1 text-xs font-medium">
                  Leave a review →
                </p>
              </div>
              {templateMsg && <p className="mt-3 text-sm text-amber-700">{templateMsg}</p>}
            </div>
            <div className="shrink-0 text-right">
              <Badge variant={status.template_status === 'APPROVED' ? 'default' : 'secondary'}>
                {status.template_status || 'Not created'}
              </Badge>
              <div className="mt-2">
                <Button variant="outline" onClick={createTemplate} disabled={busy}>
                  {busy ? 'Working…' : status.template_status ? 'Re-create' : 'Create template'}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {!status?.connected && (
        <div className="rounded-lg border p-5 text-sm">
          <h2 className="font-medium">Before you connect</h2>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-muted-foreground">
            <li>
              Use a number that is <strong>not</strong> currently in the WhatsApp or WhatsApp
              Business app. If it is, delete the account there first — otherwise registration
              fails. A landline works and avoids this entirely.
            </li>
            <li>You&apos;ll need admin access to your business&apos;s Meta account.</li>
            <li>
              Meta will ask for a payment method. Messages are billed to you at Meta&apos;s rates;
              Pinzo never marks them up.
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
