// Public prices are hidden across the marketing site for now: plans still list what
// is included, but the number is replaced by a "Contact us" call to action.
// Flip this to true to bring the published prices back — nothing else needs changing.
export const SHOW_PRICES = false;

// Shown in place of the amount on plan cards.
export const PRICE_CTA = 'Contact us';
export const PRICE_CTA_NOTE = 'Custom quote for your locations · GST invoice included';

// The sales/WhatsApp number every CTA routes to — marketing pages and the in-app
// floating widget. Hardcoded on purpose: one place to change it, no env var to keep
// in sync across environments.
export const WHATSAPP_NUMBER = '919869855079';
export const WHATSAPP_BASE = `https://wa.me/${WHATSAPP_NUMBER}`;
