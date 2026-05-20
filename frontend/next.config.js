/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow importing SVGs as components easily if required
  images: {
    domains: ['lh3.googleusercontent.com'], // Google avatar domain
  },
}

module.exports = nextConfig
