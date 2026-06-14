import type { Metadata } from 'next'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Privacy Policy — GBP Manager Pro',
  description: 'How GBP Manager Pro collects, uses, stores, and protects your data, including Google user data accessed via Google OAuth.',
}

// NOTE: This is a starting template. Have it reviewed by legal counsel and
// confirm it accurately reflects your production data practices before launch.
// Google API Services User Data Policy compliance is required for OAuth verification.
export default function PrivacyPage() {
  const updated = 'June 11, 2026'

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>

        <h1 className="mt-8 text-2xl font-extrabold tracking-tight sm:text-4xl">Privacy Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated: {updated}</p>

        <div className="mt-10 space-y-8 text-[15px] leading-relaxed sm:text-sm text-muted-foreground">
          <section className="space-y-3">
            <p>
              This Privacy Policy explains how GBP Manager Pro (&ldquo;we&rdquo;, &ldquo;us&rdquo;) collects, uses, and
              protects information when you use our platform to manage your Google Business Profile locations.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Information we collect</h2>
            <ul className="list-disc space-y-2 pl-5">
              <li><strong className="text-foreground">Account information:</strong> your name and email address, obtained when you sign in with Google.</li>
              <li><strong className="text-foreground">Google Business Profile data:</strong> your locations, reviews, ratings, posts, performance insights, and business attributes, accessed through the Google Business Profile API on your behalf.</li>
              <li><strong className="text-foreground">Usage data:</strong> basic logs needed to operate the service, troubleshoot issues, and prevent abuse.</li>
            </ul>
          </section>

          <section id="oauth" className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Google user data &amp; OAuth</h2>
            <p>
              We access Google user data only after you explicitly grant permission through Google OAuth. We request the
              minimum scopes required to manage your Business Profiles. We never receive or store your Google password.
            </p>
            <p>
              GBP Manager Pro&apos;s use of information received from Google APIs adheres to the{' '}
              <a
                href="https://developers.google.com/terms/api-services-user-data-policy"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary"
              >
                Google API Services User Data Policy
              </a>
              , including the Limited Use requirements. We do not use Google user data for advertising, and we do not sell it.
            </p>
            <p>
              You can revoke our access at any time from your{' '}
              <a
                href="https://myaccount.google.com/permissions"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary"
              >
                Google Account permissions
              </a>{' '}
              page.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">How we use your data</h2>
            <p>
              We use your data solely to provide the service: syncing locations and reviews, generating AI-assisted reply
              drafts, scheduling posts, producing analytics and audits, and enforcing role-based access within your
              organization.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">How we store and protect your data</h2>
            <p>
              OAuth tokens are encrypted at rest. Access to your locations is scoped per user through role-based access
              control. We retain data only for as long as your account is active or as needed to provide the service.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Data sharing</h2>
            <p>
              We do not sell your data. We share data only with infrastructure and AI sub-processors strictly necessary to
              run the service, and only to the extent required to deliver the features you use.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Your rights</h2>
            <p>
              You can request access to, correction of, or deletion of your data, and you can revoke Google access or
              cancel your account at any time. To make a request, contact us using the details below.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Contact</h2>
            <p>
              Questions about this policy? Reach us on{' '}
              <a
                href="https://wa.me/917021052482"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline decoration-primary/40 underline-offset-4 hover:decoration-primary"
              >
                WhatsApp
              </a>
              .
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
