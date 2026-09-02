const path = require('path')

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Render runs the normal Next.js production server. Do not use standalone
  // output here; `next start` is the correct runtime for this service.
  // This also prevents the standalone/next-start mismatch seen in Render logs.
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    domains: [],
  },
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
