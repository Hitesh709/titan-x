const path = require('path')

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  eslint: { ignoreDuringBuilds: true },
  typescript: { ignoreBuildErrors: true },
  images: {
    domains: [],
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
