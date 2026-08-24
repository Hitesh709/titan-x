import type { Metadata } from "next"
import { AuthProvider } from "@/contexts/AuthContext"
import "./globals.css"
import "./titan-landing.css"
import "./titan-premium.css"
import "./brand.css"
import "./reference-polish.css"
import "./titan-command.css"

export const metadata: Metadata = {
  title: "TITAN X — AI Market Intelligence",
  description: "TITAN X is a high-performance financial intelligence platform for live index intelligence, AI analytics, trading and risk.",
  keywords: ["TITAN X", "AI trading", "market intelligence", "global indices", "financial analytics", "risk engine"],
  icons: {
    icon: "/titan-x-logo.svg",
    shortcut: "/titan-x-logo.svg",
    apple: "/titan-x-logo.svg",
  },
  openGraph: {
    title: "TITAN X — AI Market Intelligence",
    description: "Live index intelligence, AI analytics, trading and risk in one high-performance platform.",
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