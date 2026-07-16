/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // The AWS SDK and the k8s client are server-only; keep them external so
  // Next does not try to bundle their optional/native deps into the server
  // runtime graph.
  experimental: {
    serverComponentsExternalPackages: [
      "@aws-sdk/client-dynamodb",
      "@aws-sdk/lib-dynamodb",
      "@kubernetes/client-node",
    ],
  },
};

export default nextConfig;
