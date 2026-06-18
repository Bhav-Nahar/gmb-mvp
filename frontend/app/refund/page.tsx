import type { Metadata } from 'next'
import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Cancellation and Refund Policy — Pinzo',
  description: 'The cancellation and refund policy for Pinzo services.',
}

export default function RefundPage() {
  const updated = 'June 17, 2026'

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>

        <h1 className="mt-8 text-2xl font-extrabold tracking-tight sm:text-4xl">Cancellation &amp; Refund Policy</h1>
        <p className="mt-2 text-sm text-muted-foreground">Last updated: {updated}</p>

        <div className="mt-10 space-y-8 text-[15px] leading-relaxed sm:text-sm text-muted-foreground">
          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Subscription Cancellation</h2>
            <p>
              You can cancel your subscription at any time. To cancel, navigate to the <strong>Billing</strong> section within your account settings on Pinzo and click &ldquo;Cancel Subscription&rdquo;.
            </p>
            <p>
              Upon cancellation, your subscription will remain active until the end of your current paid billing cycle, and you will not be charged again. 
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Refund Policy</h2>
            <p>
              We offer a free trial plan to allow you to experience Pinzo before committing to a paid plan.
            </p>
            <p>
              Since we provide digital subscription services and API access, <strong>all payments made to Pinzo are non-refundable</strong>, except as required by applicable law or in case of duplicate billing errors.
            </p>
            <p>
              If you believe you have been billed in error or experienced a duplicate transaction charge, please reach out to us at <a href="mailto:bhav.nahar@gmail.com" className="text-indigo-500 underline">bhav.nahar@gmail.com</a> within 7 days of the transaction.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Refund Processing</h2>
            <p>
              In approved cases of duplicate billing or system error, refunds will be initiated via the original payment method through our payment gateway (Razorpay). 
            </p>
            <p>
              Approved refunds will be processed and credited to your original payment account within 5 to 7 working days.
            </p>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-bold text-foreground">Contact Us</h2>
            <p>
              If you have any questions about this policy or your billing statement, please contact us at:
            </p>
            <p className="font-semibold text-foreground">
              Email: <a href="mailto:bhav.nahar@gmail.com" className="hover:underline">bhav.nahar@gmail.com</a>
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
