import type { Metadata } from 'next'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Terms of Service — GBP Manager Pro',
  description: 'The terms governing your use of GBP Manager Pro.',
}

// NOTE: This is a starting template. Have it reviewed by legal counsel before launch.
export default function TermsPage() {
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

        <h1 className="mt-8 text-2xl font-extrabold tracking-tight sm:text-4xl">Terms of Service</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated: {updated}</p>

        <div className="mt-10 space-y-8 text-[15px] leading-relaxed sm:text-sm text-muted-foreground">
          <section className="space-y-3">
            <p>
              These Terms of Service (&ldquo;Terms&rdquo;) govern your access to and use of GBP Manager Pro (the
              &ldquo;Service&rdquo;). By creating an account or using the Service, you agree to these Terms.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">The service</h2>
            <p>
              GBP Manager Pro is a platform that helps you manage Google Business Profile locations &mdash; including
              reviews, AI-assisted replies, posts, analytics, audits, and team access. We connect to Google on your behalf
              via Google OAuth and act only within the permissions you grant.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Your responsibilities</h2>
            <ul className="list-disc space-y-2 pl-5">
              <li>You must own or be authorized to manage the Google Business Profiles you connect.</li>
              <li>You are responsible for the content you publish through the Service, including review replies and posts.</li>
              <li>You agree to comply with Google&apos;s Business Profile policies and applicable laws.</li>
              <li>You are responsible for maintaining the security of your account and team access.</li>
            </ul>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Billing &amp; trials</h2>
            <p>
              Paid plans are billed per location on a monthly or annual basis. The free trial requires no credit card. You
              may cancel at any time from your billing settings; cancellation stops future charges and takes effect at the
              end of the current billing period. Fees already paid are non-refundable except where required by law.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">AI-generated content</h2>
            <p>
              AI-assisted replies and drafts are suggestions. You are responsible for reviewing and approving content
              before it is published to Google. We do not guarantee that AI output is accurate or appropriate for every
              context.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Availability &amp; third parties</h2>
            <p>
              The Service depends on third-party APIs, including Google&apos;s, which may impose rate limits or change
              behavior. We aim for high availability but do not guarantee uninterrupted service.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Limitation of liability</h2>
            <p>
              The Service is provided &ldquo;as is.&rdquo; To the maximum extent permitted by law, we are not liable for
              indirect, incidental, or consequential damages arising from your use of the Service.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Changes &amp; contact</h2>
            <p>
              We may update these Terms from time to time. Continued use after changes constitutes acceptance. Questions?
              Reach us on{' '}
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

          <section className="space-y-3 border-t border-border pt-6">
            <p className="text-xs">
              GBP Manager Pro is not affiliated with or endorsed by Google LLC. Google and Google Business Profile are
              trademarks of Google LLC.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
