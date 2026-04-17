/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080",
    NEXT_PUBLIC_COLLAB_WS_URL: process.env.NEXT_PUBLIC_COLLAB_WS_URL || "ws://localhost:8084",
  },
};

module.exports = nextConfig;
