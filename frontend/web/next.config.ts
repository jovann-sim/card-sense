import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The dev overlay badge sits over the dashboard's bottom-left corner, which
  // is in shot for the demo recording. Errors still surface without it.
  devIndicators: false,
};

export default nextConfig;
