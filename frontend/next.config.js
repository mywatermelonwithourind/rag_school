/** @type {import('next').NextConfig} */
const backendApiBase = process.env.BACKEND_API_BASE || "";

const nextConfig = {
  reactStrictMode: true,
  output: "export",
  async rewrites() {
    if (!backendApiBase) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${backendApiBase}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
