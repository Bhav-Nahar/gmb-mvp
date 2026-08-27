# WhatsApp in Pinzo — Scope of Work

## The idea in one line

Today WhatsApp is buried inside Reviews as "Ask for Review". We pull it out into its
own menu and add two things customers keep asking for: an **Inbox** (see replies and
reply back) and **Templates** (create and manage WhatsApp message templates).

## Why

- When we send a review request, the customer often replies. Right now that reply
  lands in our webhook and gets thrown away. Nobody sees it. That looks broken.
- Retail/local businesses live on WhatsApp. Having it in the same panel as their
  Google listing is the reason to pay for Pro.
- It costs us almost nothing extra to sell: WhatsApp is already Pro-only.

## What already exists (we are not starting from zero)

- Connecting a WhatsApp number (embedded signup) — done and live.
- Sending template messages to customers — done and live.
- Receiving webhooks from Meta (verified, signature-checked) — done and live.
  Inbound customer messages arrive; we just don't save them.
- Creating a template via the API and checking its status — the backend functions
  exist, there is no screen for them yet.
- Pro-plan gating for WhatsApp — done. Nothing to change in pricing or billing.

So the new work is: **save the messages, show them, let the user type back, and put
a screen on the template functions.**

## What we are building

### Phase 1 — The menu (no backend work)

Turn the sidebar's flat "Reviews" entry into a proper WhatsApp section:

```
WhatsApp
  Ask for Review     (existing page, just moved)
  Inbox              (new)
  Templates          (new)
  Settings           (existing page, just moved)
```

Same collapsible style as the existing Insights and Settings groups. Mobile nav too.

Note: Settings already has a "Reply Templates" item — that is for **Google review
replies**, a different thing. The new one is called **Message Templates** so nobody
mixes them up.

### Phase 2 — Save incoming messages

- New table to store every message, in and out: which business, customer's phone,
  direction, the text, Meta's message id, timestamp, delivery status.
- The webhook stops discarding customer replies and saves them instead.
- Ignore duplicates. Meta re-sends the same message when it doesn't get a fast OK,
  and we don't want the same reply appearing three times.
- Keep the existing STOP / opt-out handling exactly as it is.

A "conversation" is simply one business + one customer phone number. We are not
building a contacts system.

### Phase 3 — Reply

- A function to send plain text (not a template). The code that talks to Meta is
  already written and tested — this reuses it.
- Two endpoints: list conversations and their messages, and send a reply.
- The inbox screen: conversation list on the left, messages on the right, a box to
  type in.

**The 24-hour rule.** WhatsApp only allows free typing for 24 hours after the
customer's last message. After that, Meta rejects it and only an approved template
can go out. So:

- Inside 24 hours: the typing box works.
- Outside 24 hours: the typing box is switched off, with a clear message and a
  button to send a template instead.

This is built in from day one. If we add it later, we ship a Send button that fails
for no visible reason.

### Phase 4 — Templates screen

- List the business's templates with their status (approved, pending, rejected).
- A form to create a new one.
- Delete.

Things Meta enforces that the screen has to respect:
- A new or edited template goes back to "pending" and has to be re-approved.
- Pending, disabled and under-appeal templates cannot be edited at all.
- Edits are capped (roughly 10 per 30 days, and once a day for approved ones).

## What we are NOT building

Our other product (wacrm) has a much bigger WhatsApp system. We are deliberately
leaving most of it out:

- Bulk broadcasts and campaigns
- Automation flows / chatbots
- AI auto-reply
- Multiple agents, assigning chats, seeing who is typing
- Sending images, files and voice notes
- Buttons and list menus inside messages
- Live updates (the inbox refreshes on a timer, not instantly)

Reason: reply + templates is what makes the Pro promise true. Everything above is
what turned wacrm into a very large codebase, and none of it is needed to answer a
customer.

## How we use wacrm

We read it, we don't copy it. It is a different language (TypeScript) on a
different database, so nothing pastes across. What we take from it is the hard-won
knowledge — how conversations are matched to a phone number, how phone numbers are
cleaned up, the template approval rules, and its test files, which are a free list
of the edge cases we would otherwise find in production.

## Open questions before coding

1. Should the inbox show review-request messages we already sent, mixed in with the
   conversation? (Nicer, and slightly more work: those live in a different table.)
2. How often should the inbox refresh? Suggest every 15 seconds while the tab is open.
3. Do we notify anyone when a customer replies — email, or just a badge in the sidebar?

## Order of work

Phase 1 and Phase 2 are independent, so either can go first. 3 needs 2. 4 stands alone.
