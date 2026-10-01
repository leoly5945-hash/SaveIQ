import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = dirname(fileURLToPath(import.meta.url));

const SECURITY_HEADERS = [
  // HTTPS is already enforced by Render/Cloudflare, but pin it for browsers too.
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  // No legitimate reason for this app to be framed by another site.
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Camera (barcode scan) and microphone (voice search) for our own pages
  // only — still denied to anything embedded from another origin.
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      // Next.js needs inline script/style for hydration without a nonce setup.
      // static.cloudflareinsights.com serves the cookie-free Web Analytics beacon.
      "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com",
      "style-src 'self' 'unsafe-inline'",
      // Product photos come straight from Amazon's CDN (Creators API URLs).
      "img-src 'self' data: https://m.media-amazon.com https://images-na.ssl-images-amazon.com",
      // All API calls go through this app's own /api/* proxy routes (same-origin).
      "connect-src 'self' https://cloudflareinsights.com",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; "),
  },
];

const nextConfig = {
  reactStrictMode: true,
  turbopack: {
    root: join(appDir, "../.."),
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default nextConfig;
