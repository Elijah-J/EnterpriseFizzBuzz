import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: 'export',
  basePath: '/EnterpriseFizzBuzz',
  assetPrefix: '/EnterpriseFizzBuzz/',
  env: {
    NEXT_PUBLIC_BASE_PATH: '/EnterpriseFizzBuzz',
  },
  typescript: {
    ignoreBuildErrors: false,
  },
};

export default nextConfig;
