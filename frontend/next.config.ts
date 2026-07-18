import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{
      source: "/forge-api/:path*",
      destination: `${process.env.FORGE_BACKEND_URL || "http://127.0.0.1:8000"}/:path*`,
    }];
  },
};

export default nextConfig;
