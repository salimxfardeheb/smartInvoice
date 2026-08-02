/** @type {import("next").NextConfig} */
const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Les appels /api/* du navigateur sont proxifiés vers le backend FastAPI.
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE_URL}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
