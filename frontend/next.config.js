/** @type {import('next').NextConfig} */
const nextConfig = {
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**.onhockey.tv" },
    ],
  },
  turbopack: {
    root: "..",
  },
};

module.exports = nextConfig;
