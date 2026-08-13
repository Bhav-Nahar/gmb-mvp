'use client';

import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

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
};

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
    help: 'Sending is paused. See the note below.',
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

  const connect = async () => {
    setBusy(true);
    setError('');
    try {
      const { url } = await api.get<{ url: string }>('/whatsapp/connect-url');
      window.location.href = url;
    } catch (err) {
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

          {status?.connected ? (
            <Button variant="outline" onClick={disconnect} disabled={busy}>
              Disconnect
            </Button>
          ) : (
            <Button onClick={connect} disabled={busy}>
              {busy ? 'Opening…' : 'Connect WhatsApp'}
            </Button>
          )}
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
