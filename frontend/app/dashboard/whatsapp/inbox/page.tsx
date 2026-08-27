'use client';

// The WhatsApp inbox: customer replies on the left, the thread on the right.
//
// The one rule that shapes this whole screen is Meta's 24-hour window — free
// text is only legal for 24 hours after the customer's last message. So the
// composer is disabled with an explanation rather than present-and-failing, the
// header counts the window down while it is open, and `window_open` comes from
// the API rather than being recomputed here (the server enforces it anyway).
//
// ponytail: polls every 15s instead of websockets/SSE. Swap for a live channel
// when tenants start running the inbox as their main screen all day.
// ponytail: no unread counts — that needs per-message read state and a "mark
// read" call. Add when tenants ask "which of these have I already answered?".

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  Check, CheckCheck, Clock, XCircle, Search, MessageCircle, Star, Ban,
  AlertTriangle, ChevronLeft,
} from 'lucide-react';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';

const POLL_MS = 15_000;
const WINDOW_MS = 24 * 60 * 60 * 1000;

type WhatsAppStatus = {
  connected: boolean;
  status: string;
  status_detail: string | null;
  can_send: boolean;
};

type Conversation = {
  phone: string;
  customer_name: string | null;
  last_message: string | null;
  last_message_at: string | null;
  last_inbound_at: string | null;
  window_open: boolean;
  suppressed: boolean;
};

type Message = {
  id: string;
  direction: 'in' | 'out';
  body: string | null;
  message_type: string;
  status: string;
  created_at: string;
  kind: 'message' | 'review_request';
};

function displayPhone(phone: string): string {
  return phone.startsWith('+') ? phone : `+${phone}`;
}

function initial(c: Conversation): string {
  const name = c.customer_name?.trim();
  return (name ? name[0] : c.phone.slice(-2, -1)).toUpperCase();
}

/** Short relative age for the conversation list: now, 5m, 3h, then a date. */
function age(iso: string | null): string {
  if (!iso) return '';
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'now';
  if (mins < 60) return `${mins}m`;
  if (mins < 1440) return `${Math.floor(mins / 60)}h`;
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
}

function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** Day heading for the thread. Intl only — no date library for three cases. */
function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date(today.getTime() - 86_400_000);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  if (same(d, today)) return 'Today';
  if (same(d, yesterday)) return 'Yesterday';
  return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

/** How long is left to reply, or null once it has closed. */
function windowLeft(lastInboundAt: string | null): string | null {
  if (!lastInboundAt) return null;
  const ms = WINDOW_MS - (Date.now() - new Date(lastInboundAt).getTime());
  if (ms <= 0) return null;
  const hours = Math.floor(ms / 3_600_000);
  const mins = Math.floor((ms % 3_600_000) / 60_000);
  return hours > 0 ? `${hours}h ${mins}m` : `${mins}m`;
}

/** WhatsApp's own vocabulary: one tick sent, two delivered, blue read. */
function StatusTick({ status }: { status: string }) {
  if (status === 'failed') return <XCircle className="h-3 w-3 text-destructive" />;
  if (status === 'read' || status === 'clicked') return <CheckCheck className="h-3 w-3 text-sky-400" />;
  if (status === 'delivered') return <CheckCheck className="h-3 w-3 opacity-70" />;
  if (status === 'sent') return <Check className="h-3 w-3 opacity-70" />;
  return <Clock className="h-3 w-3 opacity-70" />;
}

export default function WhatsAppInboxPage() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [thread, setThread] = useState<Message[]>([]);
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [account, setAccount] = useState<WhatsAppStatus | null>(null);
  // Mobile is one pane at a time: the list, or the thread you tapped into.
  const [mobileThread, setMobileThread] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const active = conversations.find((c) => c.phone === selected) || null;

  const loadConversations = useCallback(async () => {
    try {
      const data = await api.get<Conversation[]>('/whatsapp/inbox/conversations');
      setConversations(data);
      setSelected((cur) => cur ?? data[0]?.phone ?? null);
    } catch {
      // A failed poll is not worth a banner — the next one is 15s away.
    } finally {
      setLoading(false);
    }
  }, []);

  const loadThread = useCallback(async (phone: string) => {
    try {
      setThread(await api.get<Message[]>(`/whatsapp/inbox/conversations/${phone}`));
    } catch {
      /* same: transient */
    }
  }, []);

  // Fetched once, not polled: a blocked account is fixed on Meta's side over
  // minutes, and the tenant lands back here through Settings anyway.
  useEffect(() => {
    api.get<WhatsAppStatus>('/whatsapp/status')
      .then(setAccount)
      .catch(() => setAccount(null));
  }, []);

  // Polling pauses while the tab is hidden. A tenant who leaves the inbox open
  // in a background tab all day would otherwise cost ~5,700 requests a day
  // doing nothing, and the first poll on return refreshes it anyway.
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const onChange = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', onChange);
    return () => document.removeEventListener('visibilitychange', onChange);
  }, []);

  useEffect(() => {
    loadConversations();
    if (!visible) return;
    const t = setInterval(loadConversations, POLL_MS);
    return () => clearInterval(t);
  }, [loadConversations, visible]);

  useEffect(() => {
    if (!selected) return;
    loadThread(selected);
    if (!visible) return;
    const t = setInterval(() => loadThread(selected), POLL_MS);
    return () => clearInterval(t);
  }, [selected, loadThread, visible]);

  // The header countdown ticks on its own, so an open tab does not sit showing
  // "3h 12m left" for a quarter of an hour.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!visible) return;
    const t = setInterval(() => tick((n) => n + 1), 60_000);
    return () => clearInterval(t);
  }, [visible]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thread.length, selected]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter(
      (c) => c.phone.includes(q) || (c.customer_name || '').toLowerCase().includes(q),
    );
  }, [conversations, query]);

  // Day headings are a render concern, so they are derived here rather than
  // stored on the message.
  const grouped = useMemo(() => {
    const out: { day: string; items: Message[] }[] = [];
    for (const m of thread) {
      const day = dayLabel(m.created_at);
      if (out.length === 0 || out[out.length - 1].day !== day) out.push({ day, items: [m] });
      else out[out.length - 1].items.push(m);
    }
    return out;
  }, [thread]);

  const send = async () => {
    if (!selected || !draft.trim() || sending) return;
    setSending(true);
    setError(null);
    try {
      const sent = await api.post<Message>(
        `/whatsapp/inbox/conversations/${selected}/reply`,
        { body: draft.trim() },
      );
      setThread((t) => [...t, sent]);
      setDraft('');
      loadConversations();
    } catch (err: any) {
      setError(err?.message || 'Could not send. Please try again.');
    } finally {
      setSending(false);
    }
  };

  const left = active ? windowLeft(active.last_inbound_at) : null;

  return (
    <div className="flex h-[calc(100vh-7rem)] flex-col gap-3">
      {/* Sending is blocked at the account level — say so here rather than
          letting the tenant discover it as a failed reply. Reading the inbox
          still works, so this is a banner, not a takeover. */}
      {account && account.connected && !account.can_send && (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm">
          <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600" />
          <span className="font-semibold">You cannot send WhatsApp messages right now.</span>
          <span className="text-muted-foreground">
            {account.status_detail || 'Your WhatsApp account needs attention.'}
          </span>
          <Link href="/dashboard/settings/whatsapp" className="font-semibold text-primary">
            Fix in settings →
          </Link>
        </div>
      )}

      <div className="flex min-h-0 flex-1 overflow-hidden rounded-xl border border-border bg-card">
      {/* ── Conversation list ─────────────────────────────────────────── */}
      {/* Below md only one pane shows at a time: the list, or the thread. */}
      <aside className={`${mobileThread ? 'hidden' : 'flex'} w-full shrink-0 flex-col border-r border-border md:flex md:w-80`}>
        <div className="space-y-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-primary" />
            <h1 className="text-sm font-bold uppercase tracking-wider">Inbox</h1>
            {conversations.length > 0 && (
              <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">
                {conversations.length}
              </span>
            )}
          </div>
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search name or number"
              className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-xs outline-none focus:border-primary/50"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading…</p>}

          {!loading && conversations.length === 0 && (
            <div className="space-y-2 p-4">
              <p className="text-sm text-muted-foreground">
                No conversations yet. Replies to your review requests land here.
              </p>
              <Link href="/dashboard/reviews/request" className="text-sm font-semibold text-primary">
                Ask for a review →
              </Link>
            </div>
          )}

          {!loading && conversations.length > 0 && filtered.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No match for “{query}”.</p>
          )}

          {filtered.map((c) => {
            const isActive = c.phone === selected;
            return (
              <button
                key={c.phone}
                onClick={() => { setSelected(c.phone); setMobileThread(true); }}
                className={`flex w-full items-start gap-3 border-b border-border/50 px-4 py-3 text-left transition-colors ${
                  isActive ? 'bg-primary/10' : 'hover:bg-muted/40'
                }`}
              >
                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                    isActive ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'
                  }`}
                >
                  {initial(c)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm font-semibold">
                      {c.customer_name || displayPhone(c.phone)}
                    </span>
                    <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground">
                      {age(c.last_message_at)}
                    </span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5">
                    <span className="truncate text-xs text-muted-foreground">
                      {c.last_message || 'Review request sent'}
                    </span>
                  </span>
                  {/* Only the states that change what the tenant can do. */}
                  {c.suppressed ? (
                    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-destructive/10 px-1.5 py-px text-[10px] font-bold uppercase text-destructive">
                      <Ban className="h-2.5 w-2.5" /> Opted out
                    </span>
                  ) : c.window_open ? (
                    <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-1.5 py-px text-[10px] font-bold uppercase text-emerald-600">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Can reply
                    </span>
                  ) : null}
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      {/* ── Thread ────────────────────────────────────────────────────── */}
      <section className={`${mobileThread ? 'flex' : 'hidden'} min-w-0 flex-1 flex-col md:flex`}>
        {!active && (
          <p className="m-auto text-sm text-muted-foreground">Select a conversation</p>
        )}

        {active && (
          <>
            <header className="flex items-center gap-3 border-b border-border px-5 py-3">
              <button
                onClick={() => setMobileThread(false)}
                className="-ml-2 rounded-lg p-1.5 text-muted-foreground hover:bg-muted/50 hover:text-foreground md:hidden"
                aria-label="Back to conversations"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-bold">
                {initial(active)}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-bold">
                  {active.customer_name || displayPhone(active.phone)}
                </p>
                <p className="text-xs text-muted-foreground">{displayPhone(active.phone)}</p>
              </div>
              {/* The countdown is the honest version of "can I still type?" —
                  a tenant who sees 40m left knows to answer now. */}
              {left && (
                <span className="ml-auto shrink-0 rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-600">
                  Reply window: {left} left
                </span>
              )}
            </header>

            <div className="flex-1 space-y-4 overflow-y-auto bg-muted/20 p-5">
              {thread.length === 0 && (
                <p className="text-center text-xs text-muted-foreground">No messages yet.</p>
              )}

              {grouped.map((group) => (
                <div key={group.day} className="space-y-2">
                  <div className="flex justify-center">
                    <span className="rounded-full bg-background px-3 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground shadow-sm">
                      {group.day}
                    </span>
                  </div>

                  {group.items.map((m) => {
                    const out = m.direction === 'out';
                    return (
                      <div key={m.id} className={`flex ${out ? 'justify-end' : 'justify-start'}`}>
                        <div
                          className={`max-w-[75%] rounded-2xl px-3.5 py-2 shadow-sm ${
                            out
                              ? 'rounded-br-md bg-primary text-primary-foreground'
                              : 'rounded-bl-md bg-background text-foreground'
                          }`}
                        >
                          {m.kind === 'review_request' ? (
                            <span className="flex items-center gap-1.5 text-sm italic opacity-90">
                              <Star className="h-3.5 w-3.5 shrink-0" />
                              Review request sent
                            </span>
                          ) : (
                            <p className="whitespace-pre-wrap break-words text-sm">{m.body}</p>
                          )}
                          <span
                            className={`mt-1 flex items-center gap-1 ${out ? 'justify-end' : 'justify-start'}`}
                          >
                            <span
                              className={`text-[10px] tabular-nums ${
                                out ? 'text-primary-foreground/70' : 'text-muted-foreground'
                              }`}
                            >
                              {clockTime(m.created_at)}
                            </span>
                            {out && <StatusTick status={m.status} />}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            <footer className="border-t border-border p-4">
              {error && <p className="mb-2 text-xs text-destructive">{error}</p>}

              {active.suppressed ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Ban className="h-4 w-4 shrink-0 text-destructive" />
                  This customer has opted out. You cannot message them.
                </p>
              ) : active.window_open ? (
                <div className="flex items-end gap-2">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    rows={2}
                    maxLength={4096}
                    placeholder="Type a reply…  (Enter to send, Shift+Enter for a new line)"
                    className="flex-1 resize-none rounded-xl border border-border bg-background px-3.5 py-2.5 text-sm outline-none focus:border-primary/50"
                  />
                  <Button onClick={send} disabled={sending || !draft.trim()} className="mb-0.5">
                    {sending ? 'Sending…' : 'Send'}
                  </Button>
                </div>
              ) : (
                /* Meta rejects free text more than 24h after the customer's last
                   message. Saying so beats a Send button that fails. */
                <div className="rounded-xl border border-border bg-muted/30 p-3">
                  <p className="text-sm font-semibold">The 24-hour reply window has closed</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    WhatsApp only allows a free reply within 24 hours of the customer&apos;s last
                    message. To reach them now, send an approved template.
                  </p>
                  <Link
                    href="/dashboard/reviews/request"
                    className="mt-1.5 inline-block text-sm font-semibold text-primary"
                  >
                    Send a template →
                  </Link>
                </div>
              )}
            </footer>
          </>
        )}
      </section>
      </div>
    </div>
  );
}
