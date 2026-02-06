import type { Metadata, Viewport } from 'next'
import { Sora, JetBrains_Mono } from 'next/font/google'
import { Providers } from '@/providers'
import { ErrorBoundary } from '@/components/error-boundary'
import './globals.css'

// Font configurations - Sora for UI, JetBrains Mono for code
const sora = Sora({
  subsets: ['latin'],
  variable: '--font-sora',
  display: 'swap',
  weight: ['400', '500', '600', '700'],
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
  display: 'swap',
  weight: ['400', '500'],
})

// Metadata configuration
export const metadata: Metadata = {
  title: {
    default: 'AG3NT',
    template: '%s | AG3NT',
  },
  description: 'AG3NT',
  keywords: ['React', 'Next.js', 'TypeScript', 'AI', 'Component Generator', 'AG3NT'],
  authors: [{ name: 'AG3NT Team' }],
  creator: 'AG3NT',
  metadataBase: new URL('https://v0.dev'),
  openGraph: {
    type: 'website',
    locale: 'en_US',
    title: 'AG3NT',
    description: 'AG3NT',
    siteName: 'AG3NT',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'AG3NT',
    description: 'AG3NT',
  },
  robots: {
    index: true,
    follow: true,
  },
  icons: {
    icon: '/images/logo.png',
    apple: '/images/logo.png',
  },
    generator: 'AG3NT'
}

// Viewport configuration
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: [
    { media: '(prefers-color-scheme: light)', color: 'white' },
    { media: '(prefers-color-scheme: dark)', color: '#0a0a0a' },
  ],
}

// Root layout component
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" className={`${sora.variable} ${jetbrainsMono.variable}`} suppressHydrationWarning>
      <head>
      </head>
      <body className="font-sans antialiased" suppressHydrationWarning>
        <ErrorBoundary>
          <Providers>
            {children}
          </Providers>
        </ErrorBoundary>
      </body>
    </html>
  )
}
