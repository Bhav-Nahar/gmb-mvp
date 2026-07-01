'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

// Overridable per-environment; falls back to the number used on the marketing homepage.
const NUMBER = process.env.NEXT_PUBLIC_WHATSAPP_NUMBER || '917021052482';
const HREF = `https://wa.me/${NUMBER}?text=${encodeURIComponent("Hi, I have a question about Pinzo.")}`;
const NUDGE_DELAY_MS = 10_000;
const DISMISS_KEY = 'wa_nudge_dismissed';

/**
 * Floating WhatsApp button (matches the homepage FAB) for the authenticated app.
 * After the user has stayed ~10s, a small "Have a question? Let's talk" bubble pops up
 * once; dismissing it (or opening the chat) hides it for the rest of the session.
 * Mounted in the dashboard layout, so it appears everywhere EXCEPT the public microsite.
 */
export function WhatsAppWidget() {
  const [showBubble, setShowBubble] = useState(false);

  useEffect(() => {
    try {
      if (sessionStorage.getItem(DISMISS_KEY)) return;
    } catch { /* sessionStorage may be unavailable */ }
    const t = setTimeout(() => setShowBubble(true), NUDGE_DELAY_MS);
    return () => clearTimeout(t);
  }, []);

  const dismiss = () => {
    setShowBubble(false);
    try { sessionStorage.setItem(DISMISS_KEY, '1'); } catch { /* ignore */ }
  };

  return (
    <div className="fixed bottom-5 right-5 z-50 flex flex-col items-end gap-3 sm:bottom-6 sm:right-6">
      {showBubble && (
        <div className="flex items-center gap-2 rounded-2xl border border-border bg-card px-4 py-2.5 shadow-lg transition-opacity">
          <span className="text-sm font-medium whitespace-nowrap">Have a question? Let&apos;s talk 👋</span>
          <button onClick={dismiss} aria-label="Dismiss" className="text-muted-foreground hover:text-foreground">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      <a
        href={HREF}
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Chat with us on WhatsApp"
        onClick={dismiss}
        className="group relative flex h-14 w-14 items-center justify-center rounded-full bg-[#25D366] text-white shadow-lg shadow-black/20 transition-transform hover:scale-105 active:scale-95 self-end"
      >
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#25D366] opacity-30" />
        <svg viewBox="0 0 24 24" className="relative h-7 w-7 fill-current" aria-hidden>
          <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51l-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.999-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413Z" />
        </svg>
      </a>
    </div>
  );
}
