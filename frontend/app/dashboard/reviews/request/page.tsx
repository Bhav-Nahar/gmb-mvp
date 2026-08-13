'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

type Location = { id: number; location_name: string; city?: string | null };

type WhatsAppStatus = {
  connected: boolean;
  status: string;
  status_detail: string | null;
  can_send: boolean;
  messaging_tier: string | null;
};

type Usage = {
  month: string;
  billable_messages: number;
  billed_by: string;
  note: string;
};

type Stats = {
  total: number; sent: number; delivered: number; read: number;
  clicked: number; failed: number; skipped: number; click_rate: number;
  reviews_in_period?: number | null;
};

type Accepted = { batch_id: string; queued: number };

type PreflightRow = { phone: string; name?: string | null; will_send: boolean; reason?: string | null };
type Preflight = { will_send: number; will_skip: number; rows: PreflightRow[] };

type HistoryRow = {
  id: number; phone: string; customer_name?: string | null; status: string;
  error_detail?: string | null; created_at: string; clicked_at?: string | null;
};

type Suppression = { id: number; phone: string; reason: string; note?: string | null };

// Accepts what people actually paste: one per line, comma separated, or
// "Name, 98765 43210". Anything without digits is dropped rather than sent
// somewhere unintended — the server normalises and validates again.
type Row = { name: string; phone: string };
type ParsedRecipient = { phone: string; name?: string };

const digitsOf = (v: string) => (v.match(/\d/g) || []).join('');

function parsePasted(raw: string): ParsedRecipient[] {
  const out: ParsedRecipient[] = [];
  for (const line of raw.split(/[\n\r]+/)) {
    const parts = line.trim().split(/[,;\t]/).map((p) => p.trim()).filter(Boolean);
    if (parts.length === 0) continue;
    const phone = parts.find((p) => (p.match(/\d/g) || []).length >= 8);
    if (!phone) continue;
    const name = parts.find((p) => p !== phone && /[a-zA-Z]/.test(p));
    out.push(name ? { phone, name } : { phone });
  }
  return out;
}

export default function RequestReviewsPage() {
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [waStatus, setWaStatus] = useState<WhatsAppStatus | null>(null);
  const [rows, setRows] = useState<Row[]>([{ name: '', phone: '' }]);
  const [showPaste, setShowPaste] = useState(false);
  const [pasted, setPasted] = useState('');
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Accepted | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [error, setError] = useState('');
  // The dry run. Held in state because the Send button turns into "confirm"
  // once it exists — a tenant should never learn about 40 skipped numbers after
  // the fact.
  const [preview, setPreview] = useState<Preflight | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [suppressions, setSuppressions] = useState<Suppression[]>([]);
  const [showOptOuts, setShowOptOuts] = useState(false);
  const [newOptOut, setNewOptOut] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);

  // Only rows with a plausible number are sent. The server normalises and
  // validates again — this is just so the button count matches reality.
  const recipients = useMemo(
    () =>
      rows
        .filter((r) => digitsOf(r.phone).length >= 10)
        .map((r) => ({ phone: r.phone.trim(), name: r.name.trim() || undefined })),
    [rows],
  );

  const updateRow = (i: number, field: keyof Row, value: string) => {
    setPreview(null);   // the list changed, so the dry run no longer describes it
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, [field]: value } : r)));
  };

  const removeRow = (i: number) =>
    setRows((prev) => (prev.length === 1 ? prev : prev.filter((_, idx) => idx !== i)));

  // Bulk paste appends to the rows rather than replacing them, so a pasted list
  // and a hand-typed one can coexist. The empty starter row is dropped.
  const addPastedRows = () => {
    const parsed = parsePasted(pasted).map((r) => ({ name: r.name ?? '', phone: r.phone }));
    if (parsed.length === 0) return;
    setRows((prev) => {
      const kept = prev.filter((r) => r.name.trim() !== '' || r.phone.trim() !== '');
      return [...kept, ...parsed];
    });
    setPasted('');
    setShowPaste(false);
  };

  useEffect(() => {
    api.get<Location[]>('/locations/').then((rows) => {
      setLocations(rows);
      if (rows.length === 1) setLocationId(rows[0].id);
    }).catch(() => setError('Could not load your locations.'));
    api.get<WhatsAppStatus>('/whatsapp/status').then(setWaStatus).catch(() => undefined);
  }, []);

  const loadStats = useCallback(async (batchId?: string) => {
    if (!locationId && !batchId) return;
    const params: Record<string, string> = batchId
      ? { batch_id: batchId }
      : { location_id: String(locationId) };
    try {
      setStats(await api.get<Stats>('/review-requests/stats', params));
    } catch {
      /* stats are informational — never block the page on them */
    }
  }, [locationId]);

  const loadHistory = useCallback(async (batchId?: string) => {
    const params: Record<string, string> = batchId
      ? { batch_id: batchId }
      : locationId ? { location_id: String(locationId) } : {};
    try {
      setHistory(await api.get<HistoryRow[]>('/review-requests/history', params));
    } catch {
      /* informational */
    }
  }, [locationId]);

  const loadSuppressions = useCallback(async () => {
    try {
      setSuppressions(await api.get<Suppression[]>('/review-requests/suppressions'));
    } catch {
      /* informational */
    }
  }, []);

  useEffect(() => { loadStats(); loadHistory(); }, [loadStats, loadHistory]);
  useEffect(() => { loadSuppressions(); }, [loadSuppressions]);

  // Who charges for what. A tenant who does not know Meta bills them directly
  // finds out from a Meta invoice, which is the worst possible way to learn it.
  useEffect(() => {
    api.get<Usage>('/review-requests/usage').then(setUsage).catch(() => {});
  }, []);

  // A batch is paced at a couple of seconds per message, so results arrive over
  // minutes. Polling while one is running means the operator watches it happen
  // instead of wondering whether it worked.
  useEffect(() => {
    if (!result) return;
    const id = setInterval(() => {
      loadStats(result.batch_id);
      loadHistory(result.batch_id);
    }, 5000);
    return () => clearInterval(id);
  }, [result, loadStats, loadHistory]);

  // Two-step send: check, then confirm. The check is the same three rules the
  // sender applies, so the numbers shown are the numbers that happen.
  const check = async () => {
    if (!locationId || recipients.length === 0) return;
    setBusy(true);
    setError('');
    try {
      setPreview(await api.post<Preflight>('/review-requests/preflight', { recipients }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not check that list.');
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!locationId || recipients.length === 0) return;
    setBusy(true);
    setError('');
    try {
      const accepted = await api.post<Accepted>('/review-requests/send', {
        location_id: locationId,
        recipients,
        consent_confirmed: consent,
      });
      setResult(accepted);
      setRows([{ name: '', phone: '' }]);
      setPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the campaign.');
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File) => {
    if (!locationId) return;
    setBusy(true);
    setError('');
    try {
      const form = new FormData();
      form.append('location_id', String(locationId));
      form.append('consent_confirmed', String(consent));
      form.append('file', file);
      // FormData must NOT carry a JSON content-type — the browser sets the
      // multipart boundary itself, and overriding it makes the upload unparseable.
      const accepted = await api.post<Accepted>('/review-requests/upload', form);
      setResult(accepted);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not read that file.');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const blocked = !waStatus?.can_send;

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold">Ask for Google reviews</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sends a WhatsApp message from your own number with a one-tap link to this
          location&apos;s Google review page.
        </p>
      </div>

      {blocked && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-medium">WhatsApp isn&apos;t ready yet</p>
          <p className="mt-1">{waStatus?.status_detail || 'Connect your WhatsApp Business Account to start sending.'}</p>
          <Link href="/dashboard/settings/whatsapp" className="mt-2 inline-block font-medium underline">
            Go to WhatsApp settings
          </Link>
        </div>
      )}

      {error && <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-900">{error}</div>}

      <div className="space-y-4 rounded-lg border p-5">
        <div>
          <label className="block text-sm font-medium">Location</label>
          <select
            className="mt-1 w-full rounded-md border px-3 py-2 text-sm"
            value={locationId ?? ''}
            onChange={(e) => setLocationId(Number(e.target.value) || null)}
            disabled={blocked}
          >
            <option value="">Select a location…</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.location_name}{l.city ? ` — ${l.city}` : ''}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            The review link points at this location&apos;s Google listing.
          </p>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <label className="block text-sm font-medium">Customers</label>
            <button
              type="button"
              className="text-xs font-medium underline"
              onClick={() => setShowPaste((v) => !v)}
              disabled={blocked}
            >
              {showPaste ? 'Hide bulk paste' : 'Paste a list instead'}
            </button>
          </div>

          {/* One row per customer. A single textarea made the operator guess at
              the format and hid mistakes until after sending; separate fields
              make a wrong number visible while it can still be corrected. */}
          <div className="mt-2 space-y-2">
            {rows.map((row, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  className="w-1/3 rounded-md border px-3 py-2 text-sm"
                  placeholder="Name (optional)"
                  value={row.name}
                  onChange={(e) => updateRow(i, 'name', e.target.value)}
                  disabled={blocked}
                />
                <input
                  className="flex-1 rounded-md border px-3 py-2 text-sm"
                  placeholder="Phone number"
                  inputMode="tel"
                  value={row.phone}
                  onChange={(e) => updateRow(i, 'phone', e.target.value)}
                  disabled={blocked}
                />
                <span className="w-24 shrink-0 text-xs text-muted-foreground">
                  {row.phone.trim() === ''
                    ? ''
                    : digitsOf(row.phone).length >= 10
                      ? '✓ looks right'
                      : 'too short'}
                </span>
                <button
                  type="button"
                  className="px-2 text-muted-foreground hover:text-foreground"
                  onClick={() => removeRow(i)}
                  disabled={blocked || rows.length === 1}
                  aria-label="Remove"
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <button
            type="button"
            className="mt-2 text-sm font-medium underline"
            onClick={() => setRows((r) => [...r, { name: '', phone: '' }])}
            disabled={blocked}
          >
            + Add another
          </button>

          {showPaste && (
            <div className="mt-3 rounded-md border bg-muted/30 p-3">
              <textarea
                className="h-24 w-full rounded-md border px-3 py-2 font-mono text-sm"
                placeholder={'9876543210\nPriya, 9123456789\n+91 98765 43210'}
                value={pasted}
                onChange={(e) => setPasted(e.target.value)}
                disabled={blocked}
              />
              <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>One per line, optionally &ldquo;Name, number&rdquo;.</span>
                <button
                  type="button"
                  className="font-medium underline"
                  onClick={addPastedRows}
                  disabled={blocked || parsePasted(pasted).length === 0}
                >
                  Add {parsePasted(pasted).length || ''} to the list
                </button>
              </div>
            </div>
          )}

          <p className="mt-2 text-xs text-muted-foreground">
            {recipients.length} customer{recipients.length === 1 ? '' : 's'} ready to message
          </p>
        </div>

        <div className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">or</span>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="text-sm"
            disabled={blocked || !locationId || !consent}
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
          />
          <span className="text-xs text-muted-foreground">CSV with a phone column</span>
        </div>

        {/* Not a formality. WhatsApp requires opt-in, and a bought list gets the
            tenant's own number restricted — which is why this is theirs to
            affirm, recorded against their user id. */}
        <label className="flex items-start gap-2 rounded-md bg-muted/40 p-3 text-sm">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            disabled={blocked}
          />
          <span>
            These are my own customers and they agreed to be contacted. I understand that
            messaging people who didn&apos;t opt in can get my WhatsApp number restricted by Meta.
          </span>
        </label>

        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">
            Sent at a steady pace to protect your number&apos;s quality rating
            {waStatus?.messaging_tier ? ` · daily limit ${waStatus.messaging_tier.replace('TIER_', '')}` : ''}.
          </p>
          <Button
            onClick={preview ? send : check}
            disabled={blocked || busy || !locationId || !consent || recipients.length === 0
              || (preview !== null && preview.will_send === 0)}
          >
            {busy
              ? (preview ? 'Starting…' : 'Checking…')
              : preview
                ? `Send ${preview.will_send} message${preview.will_send === 1 ? '' : 's'}`
                : `Check ${recipients.length || ''} number${recipients.length === 1 ? '' : 's'}`}
          </Button>
        </div>

        {preview && (
          <div className="rounded-md border bg-muted/40 p-4 text-sm">
            <p className="font-medium">
              {preview.will_send} will be sent
              {preview.will_skip > 0 && ` · ${preview.will_skip} will be skipped`}
            </p>
            {preview.will_skip > 0 && (
              <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
                {preview.rows.filter((r) => !r.will_send).map((r) => (
                  <li key={r.phone + (r.reason ?? '')}>
                    {r.phone} — {r.reason}
                  </li>
                ))}
              </ul>
            )}
            {preview.will_send === 0 && (
              <p className="mt-2 text-xs">
                Nothing to send. Edit the list above and check again.
              </p>
            )}
          </div>
        )}
      </div>

      {result && (
        <div className="rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-900">
          Campaign started — {result.queued} queued. Messages go out over the next few minutes.
        </div>
      )}

      {usage && (
        <div className="rounded-lg border p-5">
          <div className="flex items-baseline justify-between gap-4">
            <div>
              <h2 className="text-sm font-medium">Message costs — {usage.month}</h2>
              <p className="mt-0.5 text-2xl font-semibold">
                {usage.billable_messages}
                <span className="ml-2 text-sm font-normal text-muted-foreground">
                  billable messages
                </span>
              </p>
            </div>
            <a
              href="https://business.facebook.com/wa/manage/insights/"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs underline text-muted-foreground hover:text-foreground"
            >
              View charges in WhatsApp Manager
            </a>
          </div>
          <p className="mt-2 text-xs text-muted-foreground">{usage.note}</p>
        </div>
      )}

      {stats && stats.total > 0 && (
        <div className="rounded-lg border p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-medium">
              {result ? 'This campaign' : 'Last 30 days'}
            </h2>
            <Badge variant="secondary">{stats.click_rate}% clicked</Badge>
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-4 text-sm sm:grid-cols-6">
            {([
              ['Total', stats.total], ['Sent', stats.sent], ['Delivered', stats.delivered],
              ['Read', stats.read], ['Clicked', stats.clicked], ['Failed', stats.failed],
            ] as const).map(([label, value]) => (
              <div key={label}>
                <dt className="text-muted-foreground">{label}</dt>
                <dd className="mt-0.5 text-lg font-semibold">{value}</dd>
              </div>
            ))}
          </dl>
          {stats.skipped > 0 && (
            <p className="mt-3 text-xs text-muted-foreground">
              {stats.skipped} skipped — already asked recently, opted out, or not a usable number.
            </p>
          )}
          {/* Not per-customer attribution — Google never says who left a review.
              This is the location's total over the same window, labelled as such. */}
          {typeof stats.reviews_in_period === 'number' && (
            <p className="mt-3 text-xs text-muted-foreground">
              {stats.reviews_in_period} Google review
              {stats.reviews_in_period === 1 ? '' : 's'} arrived at this location in the same
              period. Google doesn&apos;t say who left them, so this is the outcome to
              watch rather than a per-customer score.
            </p>
          )}
        </div>
      )}
      {history.length > 0 && (
        <div className="rounded-lg border p-5">
          <h2 className="text-sm font-medium">
            {result ? 'This campaign, message by message' : 'Recent requests'}
          </h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className="border-b last:border-0">
                    <td className="py-2 pr-3">{h.customer_name || '—'}</td>
                    <td className="py-2 pr-3 tabular-nums text-muted-foreground">{h.phone}</td>
                    <td className="py-2 pr-3">
                      <Badge variant={h.status === 'clicked' ? 'default' : 'secondary'}>
                        {h.status}
                      </Badge>
                    </td>
                    {/* The reason lives next to the row it explains. A tenant
                        asking "why didn't she get it" should not have to ask us. */}
                    <td className="py-2 text-xs text-muted-foreground">{h.error_detail || ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="rounded-lg border p-5">
        <button
          type="button"
          onClick={() => setShowOptOuts((v) => !v)}
          className="text-sm font-medium"
        >
          Do-not-contact list ({suppressions.length}) {showOptOuts ? '▲' : '▼'}
        </button>
        {showOptOuts && (
          <div className="mt-3 space-y-3">
            <p className="text-xs text-muted-foreground">
              These numbers are never messaged. Customers who reply STOP are added
              automatically and can&apos;t be removed — that&apos;s their choice, and ignoring
              it is what gets a WhatsApp number restricted.
            </p>
            <div className="flex gap-2">
              <input
                value={newOptOut}
                onChange={(e) => setNewOptOut(e.target.value)}
                placeholder="Add a number"
                className="w-56 rounded-md border px-3 py-1.5 text-sm"
              />
              <Button
                variant="secondary"
                disabled={!newOptOut.trim()}
                onClick={async () => {
                  try {
                    await api.post('/review-requests/suppressions', { phone: newOptOut.trim() });
                    setNewOptOut('');
                    loadSuppressions();
                  } catch (err) {
                    setError(err instanceof Error ? err.message : 'Could not add that number.');
                  }
                }}
              >
                Add
              </Button>
            </div>
            <ul className="space-y-1 text-sm">
              {suppressions.map((sup) => (
                <li key={sup.id} className="flex items-center justify-between border-b py-1.5 last:border-0">
                  <span className="tabular-nums">{sup.phone}</span>
                  <span className="flex items-center gap-3 text-xs text-muted-foreground">
                    {sup.reason === 'opt_out' ? 'replied STOP' : sup.reason}
                    {sup.reason !== 'opt_out' && (
                      <button
                        type="button"
                        className="underline"
                        onClick={async () => {
                          try {
                            await api.delete(`/review-requests/suppressions/${sup.id}`);
                            loadSuppressions();
                          } catch (err) {
                            setError(err instanceof Error ? err.message : 'Could not remove it.');
                          }
                        }}
                      >
                        remove
                      </button>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
