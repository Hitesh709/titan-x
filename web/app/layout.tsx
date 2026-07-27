import type { Metadata } from "next"
import { AuthProvider } from "@/contexts/AuthContext"
import "./globals.css"

export const metadata: Metadata = {
  title: "TITAN X — Enterprise Intelligence Platform",
  description: "AI-powered financial analytics, market intelligence, and portfolio management platform for institutional investors and enterprise trading desks.",
  keywords: ["trading", "finance", "AI", "portfolio management", "market analysis", "institutional trading"],
  openGraph: {
    title: "TITAN X — Enterprise Intelligence Platform",
    description: "AI-powered financial analytics and portfolio management.",
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
