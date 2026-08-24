/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  images: {
    domains: ['lh3.googleusercontent.com'], // Google avatar domain
  },
  async redirects() {
    return [
      // The static file is reachable at its own path too, which would be a second
      // URL for the same page. Redirects run before rewrites, so this only catches
      // real visitors; the internal rewrite below still resolves the file.
      { source: '/local-seo-services.html', destination: '/local-seo-services', permanent: true },
    ]
  },
  async rewrites() {
    return {
      // The global Local SEO pillar is the approved page itself, served verbatim from
      // public/local-seo-services.html instead of being rebuilt from a CSV import.
      // beforeFiles so this wins over the app router: the old cseo-driven route is
      // deleted, and this URL has exactly one source.
      // Locale pillars (/en-in/local-seo-services) are untouched and still come from
      // cseo_pages, so the country tier keeps its admin workflow.
      beforeFiles: [
        { source: '/local-seo-services', destination: '/local-seo-services.html' },
      ],
    }
  },
}

module.exports = nextConfig
