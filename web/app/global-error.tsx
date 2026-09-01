'use client'

import { useEffect } from 'react'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  useEffect(() => {
    console.error('TITAN X global client error', error)
  }, [error])

  return (
    <html lang="en" className="dark">
      <body style={{ margin: 0, minHeight: '100vh', background: '#020713', color: '#e8f1ff', fontFamily: 'system-ui, sans-serif' }}>
        <main style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
          <section style={{ width: 'min(560px, 100%)', border: '1px solid rgba(100,160,220,.25)', borderRadius: 18, padding: 28, background: '#07101f', boxShadow: '0 20px 80px rgba(0,0,0,.45)' }}>
            <div style={{ fontSize: 12, letterSpacing: '.14em', color: '#6f9dcc', fontWeight: 700 }}>TITAN X</div>
            <h1 style={{ margin: '12px 0 8px', fontSize: 24 }}>The application encountered an error</h1>
            <p style={{ margin: 0, color: '#8ea5bf', lineHeight: 1.6 }}>
              The page failed to initialize. Your account, trading data and paper portfolio are stored on the server and are not deleted by this error.
            </p>
            <button
              onClick={() => reset()}
              style={{ marginTop: 22, border: 0, borderRadius: 10, padding: '11px 18px', background: '#1677ff', color: '#fff', fontWeight: 700, cursor: 'pointer' }}
            >
              Try again
            </button>
            <button
              onClick={() => window.location.reload()}
              style={{ marginTop: 22, marginLeft: 10, border: '1px solid rgba(100,160,220,.35)', borderRadius: 10, padding: '10px 18px', background: 'transparent', color: '#c8d8ea', fontWeight: 600, cursor: 'pointer' }}
            >
              Reload app
            </button>
          </section>
        </main>
      </body>
    </html>
  )
}
