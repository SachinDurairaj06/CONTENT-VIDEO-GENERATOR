import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Disable image optimization because static exports cannot use the default Next.js Image loader
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
