import type { Metadata } from 'next'
import Link from 'next/link'
import { ArrowLeft, Mail, Phone, MapPin } from 'lucide-react'

export const metadata: Metadata = {
  title: 'Contact Us — Pinzo',
  description: 'Get in touch with the Pinzo support team.',
}

export default function ContactPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-3xl px-4 py-16 sm:px-6 lg:px-8">
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" /> Back to home
        </Link>

        <h1 className="mt-8 text-2xl font-extrabold tracking-tight sm:text-4xl">Contact Us</h1>
        <p className="mt-2 text-sm text-muted-foreground">We are here to help you. Reach out to us with any questions or support requests.</p>

        <div className="mt-10 space-y-8 text-[15px] leading-relaxed sm:text-sm text-muted-foreground">
          <section className="space-y-4">
            <h2 className="text-lg font-bold text-foreground">Support &amp; General Inquiries</h2>
            <p>
              For support, billing issues, integration questions, or general inquiries, please email us directly:
            </p>
            <div className="flex items-center gap-3 mt-4 text-foreground">
              <Mail className="h-5 w-5 text-indigo-500" />
              <a href="mailto:bhav.nahar@gmail.com" className="hover:underline">
                bhav.nahar@gmail.com
              </a>
            </div>
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-bold text-foreground">Instant Messaging</h2>
            <p>
              You can also reach out to our team on WhatsApp for quick assistance:
            </p>
            <div className="flex items-center gap-3 mt-2 text-foreground">
              <span className="text-indigo-500 font-bold">WhatsApp:</span>
              <a
                href="https://wa.me/917021052482"
                target="_blank"
                rel="noopener noreferrer"
                className="underline decoration-indigo-500/40 underline-offset-4 hover:decoration-indigo-500"
              >
                +91 7021052482
              </a>
            </div>
          </section>

          <section className="space-y-4">
            <h2 className="text-lg font-bold text-foreground">Business Details</h2>
            <p>
              Pinzo is owned and operated by SBN Creations.
            </p>
            <div className="flex items-start gap-3 mt-2">
              <MapPin className="h-5 w-5 text-indigo-500 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-foreground">SBN Creations</p>
                <p className="text-xs">Mumbai, India</p>
              </div>
            </div>
          </section>

          <section className="space-y-3 border-t border-border pt-6">
            <p className="text-xs">
              Pinzo is not affiliated with or endorsed by Google LLC. Google and Google Business Profile are
              trademarks of Google LLC.
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
