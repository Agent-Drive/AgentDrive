import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  async redirects() {
    return [
      {
        source: "/app",
        destination: "/dashboard",
        permanent: true,
      },
      {
        source: "/app/:path*",
        destination: "/dashboard/:path*",
        permanent: true,
      },
    ];
  },
};

export default nextConfig;
