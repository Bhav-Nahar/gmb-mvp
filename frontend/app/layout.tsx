import type { Metadata, Viewport } from 'next'
import './globals.css'
import { Inter } from "next/font/google";
import { cn } from "@/lib/utils";
import QueryProvider from "@/components/QueryProvider";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider } from "@/hooks/useAuth";
import Script from "next/script";
import Attribution from "@/components/Attribution";

const inter = Inter({subsets:['latin'],variable:'--font-sans'});

import { BillingProvider } from "@/components/billing/BillingProvider";

export const metadata: Metadata = {
  title: 'Pinzo — Manage every Google Business Profile from one dashboard',
  description: 'Centralize reviews, AI-assisted replies, multi-location Google Posts, analytics, audits, and team roles for all your Google Business Profile locations. Secure Google OAuth. 7-day free trial, no card required.',
  applicationName: 'Pinzo',
  keywords: ['Google Business Profile', 'GBP management', 'local SEO', 'review management', 'multi-location', 'Google Posts'],
  icons: {
    icon: '/icon.jpg',
  },
  openGraph: {
    title: 'Pinzo — Manage every Google Business Profile from one dashboard',
    description: 'Reviews, AI replies, Google Posts, analytics, audits and team roles for every location. Secure Google OAuth. 7-day free trial.',
    siteName: 'Pinzo',
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Pinzo',
    description: 'Manage every Google Business Profile from one dashboard. Secure Google OAuth. 7-day free trial.',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={cn("font-sans", inter.variable)}>
      <Script id="gtm" strategy="afterInteractive">{`
        (function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':
        new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],
        j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
        'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
        })(window,document,'script','dataLayer','GTM-TNXZ837G');
      `}</Script>
      <body className="antialiased min-h-screen bg-background text-foreground">
        <noscript>
          <iframe src="https://www.googletagmanager.com/ns.html?id=GTM-TNXZ837G"
            height="0" width="0" style={{ display: "none", visibility: "hidden" }} />
        </noscript>
        <Attribution />
        <QueryProvider>
          <TooltipProvider>
            <AuthProvider>
              <BillingProvider>
                {children}
              </BillingProvider>
              <Toaster />
            </AuthProvider>
          </TooltipProvider>
        </QueryProvider>
      </body>
    </html>
  )
}
