import type { Metadata } from "next"
import { AuthProvider } from "@/contexts/AuthContext"
import "./globals.css"
import "./titan-landing.css"

export const metadata: Metadata = {
  title: "TITAN X — XeCaps Intelligence Platform",
  description: "AI-powered financial analytics, market intelligence, and portfolio management platform by XeCaps.",
  keywords: ["trading", "finance", "AI", "portfolio management", "market analysis", "institutional trading", "XeCaps"],
  icons: {
    icon: "/xecaps-icon.svg",
    shortcut: "/xecaps-icon.svg",
    apple: "/xecaps-icon.svg",
  },
  openGraph: {
    title: "TITAN X — XeCaps Intelligence Platform",
    description: "AI-powered financial analytics and portfolio management by XeCaps.",
    type: "website",
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-titan-950">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  )
}
