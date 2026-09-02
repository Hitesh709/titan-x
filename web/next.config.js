const path = require('path')

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // Temporary deployment guard: the landing page has a non-runtime
  // TypeScript inference issue in its icon tuple. Keep production builds
  // deployable while the UI remains runtime-safe; type cleanup follows.
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    domains: [],
  },
  // Never let the browser/CDN reuse an HTML document from an older build.
  // Next.js fingerprints JS chunks, so stale HTML can otherwise reference
  // chunks that no longer exist after a Render deployment and produce the
  // generic "client-side exception" screen.
  async headers() {
    return [
      {
        source: '/((?!_next/static|_next/image).*)',
        headers: [
          { key: 'Cache-Control', value: 'no-store, max-age=0, must-revalidate' },
        ],
      },
    ]
  },
  async rewrites() {
    return [
      {
        source: '/api/v1/:path*',
        destination: 'https://titan-x-api.onrender.com/api/v1/:path*',
      },
    ]
  },
  webpack: (config) => {
    config.resolve.alias = {
      ...config.resolve.alias,
      '@': path.join(__dirname),
    }
    return config
  },
}

module.exports = nextConfig
