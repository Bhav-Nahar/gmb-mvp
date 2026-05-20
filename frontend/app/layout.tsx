import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'GMB Sync Engine',
  description: 'Manage and synchronize Google Business Profile locations instantly.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body className="antialiased min-h-screen bg-background text-foreground gradient-bg bg-no-repeat bg-cover">
        {children}
      </body>
    </html>
  )
}
